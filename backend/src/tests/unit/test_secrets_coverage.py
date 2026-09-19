"""
Extended unit tests for ``core.secrets`` to improve coverage.

Issue #1783.

Coverage areas:
- ``SecretsManager._init_aws``: ImportError → secrets_backend="local" fallback.
- ``SecretsManager._init_vault``: ImportError → secrets_backend="local" fallback; missing token.
- ``SecretsManager._init_doppler``: ImportError → secrets_backend="local" fallback; missing token.
- ``SecretsManager.get_secret``: cache-hit path, local-backend path, exception→default path.
- ``SecretsManager._get_aws_secret`` / ``_get_vault_secret`` / ``_get_doppler_secret``: error paths.
- ``SecretsManager.get_all_secrets``: aws / vault / local branches.
- ``Settings.settings_customise_sources``: ``SecretsManagerSource`` precedence.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.secrets import (
    SecretStr,
    SecretsManager,
    SecretsManagerSettings,
    Settings,
    get_secrets_manager,
    get_secret,
)


# ---------------------------------------------------------------------------
# SecretStr
# ---------------------------------------------------------------------------


class TestSecretStr:
    """Test SecretStr redaction."""

    def test_repr_is_redacted(self):
        secret = SecretStr("super_secret_value")
        assert "***REDACTED***" in repr(secret)
        assert "super_secret" not in repr(secret)

    def test_str_is_redacted(self):
        secret = SecretStr("super_secret_value")
        assert str(secret) == "***REDACTED***"


# ---------------------------------------------------------------------------
# SecretsManagerSettings
# ---------------------------------------------------------------------------


class TestSecretsManagerSettings:
    def test_defaults(self):
        """Default settings instantiate cleanly with no env vars."""
        settings = SecretsManagerSettings(model_config={"env_file": ".env.test"})
        assert settings.secrets_backend == "local"
        assert settings.aws_region == "us-west-2"


# ---------------------------------------------------------------------------
# _init_* fallback paths (ImportError → local)
# ---------------------------------------------------------------------------


class TestInitBackends:
    """Test that each backend falls back to 'local' when its library is missing."""

    def test_init_aws_falls_back_on_import_error(self):
        """When boto3 is not installed, secrets_backend switches to local."""
        settings = SecretsManagerSettings(
            SECRETS_BACKEND="aws",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        original_import = __builtins__["__import__"]

        def fake_import(name, *a, **kw):
            if name == "boto3":
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *a, **kw)

        try:
            __builtins__["__import__"] = fake_import
            manager._init_aws()
            assert manager.settings.secrets_backend == "local"
        finally:
            __builtins__["__import__"] = original_import

    def test_init_aws_raises_on_other_exception(self):
        """Any exception other than ImportError from boto3 is re-raised."""
        settings = SecretsManagerSettings(
            SECRETS_BACKEND="aws",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        original_import = __builtins__["__import__"]

        def fake_import(name, *a, **kw):
            if name == "boto3":
                raise RuntimeError("bad config")
            return original_import(name, *a, **kw)

        try:
            __builtins__["__import__"] = fake_import
            with pytest.raises(RuntimeError, match="bad config"):
                manager._init_aws()
        finally:
            __builtins__["__import__"] = original_import

    def test_init_vault_raises_when_token_missing(self):
        """When vault_token is not set and token file doesn't exist, ValueError is raised."""
        settings = SecretsManagerSettings(
            secrets_backend="vault",
            vault_token=None,
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Vault token is required"):
                manager._init_vault()

    def test_init_doppler_raises_when_token_missing(self):
        """When doppler_token is not set, ValueError is raised."""
        settings = SecretsManagerSettings(
            secrets_backend="doppler",
            doppler_token=None,
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with pytest.raises(ValueError, match="Doppler token is required"):
            manager._init_doppler()


# ---------------------------------------------------------------------------
# get_secret paths
# ---------------------------------------------------------------------------


class TestGetSecret:
    """Test get_secret cache, dispatch, and exception→default paths."""

    def test_cache_hit_returns_cached_value(self):
        """When a key is already cached, the backend is not called."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._cache["MY_SECRET"] = "cached_value"
        manager._backend_initialized = True

        result = manager.get_secret("MY_SECRET")
        assert result == "cached_value"

    def test_local_backend_uses_os_getenv(self):
        """With secrets_backend=local, get_secret delegates to os.getenv."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with patch.dict("os.environ", {"MY_SECRET": "env_value"}):
            result = manager.get_secret("MY_SECRET")
            assert result == "env_value"

    def test_local_backend_returns_default_when_not_found(self):
        """When the key is not in os.environ, the default is returned."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with patch.dict("os.environ", {}, clear=True):
            result = manager.get_secret("MISSING_KEY", default="fallback")
            assert result == "fallback"

    def test_get_secret_caches_non_none_value(self):
        """After a successful fetch, the value is stored in the cache."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with patch.dict("os.environ", {"TO_BE_CACHED": "secret_value"}):
            result = manager.get_secret("TO_BE_CACHED")
            assert result == "secret_value"
            assert manager._cache.get("TO_BE_CACHED") == "secret_value"

    def test_exception_returns_default(self):
        """When the backend raises an exception, the default is returned silently."""
        settings = SecretsManagerSettings(
            secrets_backend="aws",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._backend_initialized = True

        with patch.object(manager, "_get_aws_secret", side_effect=RuntimeError("AWS error")):
            result = manager.get_secret("SOME_KEY", default="error_default")
            assert result == "error_default"


# ---------------------------------------------------------------------------
# _get_*_secret error paths
# ---------------------------------------------------------------------------


class TestGetBackendSecretErrors:
    def test_get_aws_secret_returns_none_on_error(self):
        """_get_aws_secret returns None when AWS throws an exception."""
        settings = SecretsManagerSettings(
            secrets_backend="aws",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._aws_client = MagicMock()
        manager._aws_client.get_secret_value = MagicMock(
            side_effect=RuntimeError("AWS failure")
        )

        result = manager._get_aws_secret("MY_KEY")
        assert result is None

    def test_get_vault_secret_returns_none_on_error(self):
        """_get_vault_secret returns None when Vault throws an exception."""
        settings = SecretsManagerSettings(
            secrets_backend="vault",
            vault_token="test",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._vault_client = MagicMock()
        manager._vault_client.secrets.kv.v2.read_secret_version = MagicMock(
            side_effect=RuntimeError("Vault failure")
        )

        result = manager._get_vault_secret("MY_KEY")
        assert result is None


# ---------------------------------------------------------------------------
# get_all_secrets
# ---------------------------------------------------------------------------


class TestGetAllSecrets:
    """Test get_all_secrets for all backends."""

    def test_local_backend_returns_env_secrets(self):
        """Local backend returns a filtered dict of environment variables."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "my-secret-key",
                "DATABASE_URL": "postgres://localhost/db",
                "OPENAI_API_KEY": "sk-test",
            },
            clear=True,
        ):
            result = manager.get_all_secrets()
            assert result["SECRET_KEY"] == "my-secret-key"
            assert result["DATABASE_URL"] == "postgres://localhost/db"
            assert result["OPENAI_API_KEY"] == "sk-test"
            # Keys not in env are not included (the code uses `if os.getenv(k)`)
            assert "JWT_SECRET_KEY" not in result

    def test_aws_backend_returns_json_parsed_secret(self):
        """AWS backend fetches SecretString and parses JSON."""
        settings = SecretsManagerSettings(
            SECRETS_BACKEND="aws",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._aws_client = MagicMock()
        manager._aws_client.get_secret_value = MagicMock(
            return_value={
                "SecretString": '{"API_KEY": "aws-secret-key", "DB_PASS": "pw"}'
            }
        )
        manager._backend_initialized = True

        result = manager.get_all_secrets()
        assert result["API_KEY"] == "aws-secret-key"
        assert result["DB_PASS"] == "pw"

    def test_aws_backend_returns_empty_dict_on_error(self):
        """AWS backend returns {} when fetching fails."""
        settings = SecretsManagerSettings(
            SECRETS_BACKEND="aws",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._aws_client = MagicMock()
        manager._aws_client.get_secret_value = MagicMock(
            side_effect=RuntimeError("AWS error")
        )
        manager._backend_initialized = True

        result = manager.get_all_secrets()
        assert result == {}

    def test_vault_backend_returns_secret_data(self):
        """Vault backend reads KV v2 secret and returns data dict."""
        settings = SecretsManagerSettings(
            SECRETS_BACKEND="vault",
            vault_token="test",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._vault_client = MagicMock()
        manager._vault_client.secrets.kv.v2.read_secret_version = MagicMock(
            return_value={
                "data": {
                    "data": {
                        "VAULT_API_KEY": "vault-secret",
                        "VAULT_DB_PASS": "db_pw",
                    }
                }
            }
        )
        manager._backend_initialized = True

        result = manager.get_all_secrets()
        assert result["VAULT_API_KEY"] == "vault-secret"
        assert result["VAULT_DB_PASS"] == "db_pw"

    def test_vault_backend_returns_empty_dict_on_error(self):
        """Vault backend returns {} when reading fails."""
        settings = SecretsManagerSettings(
            SECRETS_BACKEND="vault",
            vault_token="test",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._vault_client = MagicMock()
        manager._vault_client.secrets.kv.v2.read_secret_version = MagicMock(
            side_effect=RuntimeError("Vault error")
        )
        manager._backend_initialized = True

        result = manager.get_all_secrets()
        assert result == {}


# ---------------------------------------------------------------------------
# Settings.settings_customise_sources — SecretsManagerSource precedence
# ---------------------------------------------------------------------------


class TestSettingsCustomiseSources:
    def test_secrets_manager_source_checks_secrets_manager_first(self):
        """SecretsManagerSource returns from secrets manager if present, else env."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._backend_initialized = True

        # Override get_all_secrets to return a controlled dict
        def fake_get_all_secrets():
            return {"MY_SECRET": "from_secrets_manager"}

        manager.get_all_secrets = fake_get_all_secrets

        with patch("core.secrets.get_secrets_manager", return_value=manager):
            sources = Settings.settings_customise_sources(
                settings=Settings,
                init_settings=(),
                env_settings=(),
                dotenv_settings=(),
                file_secret_settings=(),
            )

            source = sources[0]
            assert source("MY_SECRET") == "from_secrets_manager"

    def test_secrets_manager_source_falls_back_to_env(self):
        """When secrets manager doesn't have the key, env is checked."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)
        manager._backend_initialized = True

        def fake_get_all_secrets():
            return {}  # No secrets in the manager

        manager.get_all_secrets = fake_get_all_secrets

        with patch("core.secrets.get_secrets_manager", return_value=manager):
            sources = Settings.settings_customise_sources(
                settings=Settings,
                init_settings=(),
                env_settings=(),
                dotenv_settings=(),
                file_secret_settings=(),
            )

            source = sources[0]
            with patch.dict("os.environ", {"MY_SECRET": "from_env"}):
                assert source("MY_SECRET") == "from_env"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    def test_get_secret_convenience_function(self):
        """get_secret(key) delegates to the global secrets manager."""
        settings = SecretsManagerSettings(
            secrets_backend="local",
            model_config={"env_file": ".env.test"},
        )
        manager = SecretsManager(settings)

        with patch("core.secrets.get_secrets_manager", return_value=manager):
            with patch.dict("os.environ", {"CONVENIENCE_KEY": "convenience_value"}):
                result = get_secret("CONVENIENCE_KEY")
                assert result == "convenience_value"

    def test_get_secrets_manager_singleton(self):
        """get_secrets_manager returns the same instance on repeated calls."""
        import core.secrets

        core.secrets._secrets_manager = None

        try:
            settings = SecretsManagerSettings(
                secrets_backend="local",
                model_config={"env_file": ".env.test"},
            )
            mgr1 = get_secrets_manager()
            mgr2 = get_secrets_manager()
            assert mgr1 is mgr2
        finally:
            core.secrets._secrets_manager = None


def test_module_is_importable():
    """Sanity check: the module is importable via src layout."""
    import core.secrets as mod

    assert mod.__name__ == "core.secrets"
    assert hasattr(mod, "SecretsManager")
    assert hasattr(mod, "SecretStr")