"""
Unit tests for ``security.byok_vault``.

Issue #1783.

Coverage areas:
- ``get_encryption_key``: BYOK_MASTER_KEY path, SECRET_KEY fallback, ValueError when neither set.
- ``BYOKKeyVault.encrypt``: happy path, empty-input ``BYOKEncryptionError``.
- ``BYOKKeyVault.decrypt``: happy path, empty-input ``BYOKEncryptionError``, InvalidToken → BYOKEncryptionError.
- ``BYOKKeyVault.mask_key``: empty string, ≤4 chars, normal key, long key.
- ``validate_api_key``: OPENROUTER / OPENAI / unsupported provider dispatch + BYOKValidationError.
- ``PIIScrubbingFilter._scrub_message``: sk- / mpk_ / Bearer / openrouter| patterns.
- ``setup_byok_logging``: attaches filter to root handlers.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from security.byok_vault import (
    BYOKEncryptionError,
    BYOKKeyVault,
    BYOKValidationError,
    LLMProvider,
    PIIScrubbingFilter,
    get_encryption_key,
    setup_byok_logging,
    validate_api_key,
)


# ---------------------------------------------------------------------------
# get_encryption_key
# ---------------------------------------------------------------------------


class TestGetEncryptionKey:
    """Tests for the encryption key derivation."""

    def test_uses_byok_master_key_when_set(self, monkeypatch):
        """When BYOK_MASTER_KEY is set, it is used as the source."""
        monkeypatch.setattr(
            "security.byok_vault.get_secret",
            lambda k, d=None: {
                "BYOK_MASTER_KEY": "a" * 32,
                "SECRET_KEY": None,
            }.get(k),
        )

        key = get_encryption_key()
        assert isinstance(key, bytes)
        # base64.urlsafe_b64encode of 32 bytes → 44 chars
        assert len(key) == 44

    def test_falls_back_to_secret_key_when_byok_master_key_not_set(self, monkeypatch):
        """When BYOK_MASTER_KEY is absent, SECRET_KEY is used."""
        monkeypatch.setattr(
            "security.byok_vault.get_secret",
            lambda k, d=None: {
                "BYOK_MASTER_KEY": None,
                "SECRET_KEY": "b" * 32,
            }.get(k),
        )

        key = get_encryption_key()
        assert isinstance(key, bytes)
        assert len(key) == 44

    def test_raises_value_error_when_neither_key_is_set(self, monkeypatch):
        """When neither BYOK_MASTER_KEY nor SECRET_KEY is set, ValueError is raised."""
        monkeypatch.setattr("security.byok_vault.get_secret", lambda k, d=None: None)

        with pytest.raises(ValueError, match="BYOK_MASTER_KEY or SECRET_KEY must be set"):
            get_encryption_key()

    def test_short_master_key_is_padded(self, monkeypatch):
        """A short BYOK_MASTER_KEY is padded to 32 bytes before base64-encoding."""
        monkeypatch.setattr(
            "security.byok_vault.get_secret",
            lambda k, d=None: {
                "BYOK_MASTER_KEY": "abc",
                "SECRET_KEY": None,
            }.get(k),
        )

        key = get_encryption_key()
        assert isinstance(key, bytes)
        assert len(key) == 44

    def test_short_secret_key_is_padded(self, monkeypatch):
        """A short SECRET_KEY is padded to 32 bytes before base64-encoding."""
        monkeypatch.setattr(
            "security.byok_vault.get_secret",
            lambda k, d=None: {
                "BYOK_MASTER_KEY": None,
                "SECRET_KEY": "xyz",
            }.get(k),
        )

        key = get_encryption_key()
        assert isinstance(key, bytes)
        assert len(key) == 44


# ---------------------------------------------------------------------------
# BYOKKeyVault.encrypt / decrypt
# ---------------------------------------------------------------------------


class TestBYOKKeyVaultEncryptDecrypt:
    """Round-trip encrypt/decrypt and error paths."""

    @pytest.fixture
    def vault(self, monkeypatch):
        """A BYOKKeyVault with a stable, patched key."""
        monkeypatch.setattr(
            "security.byok_vault.get_secret",
            lambda k, d=None: {
                "BYOK_MASTER_KEY": "k" * 32,
                "SECRET_KEY": None,
            }.get(k),
        )
        return BYOKKeyVault()

    def test_encrypt_decrypt_round_trip(self, vault):
        """Basic round-trip: encrypt then decrypt returns the original key."""
        original = "sk-abcdefghijklmnopqrstuvwxyz"
        encrypted = vault.encrypt(original)
        decrypted = vault.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_empty_string_raises_byok_encryption_error(self, vault):
        """Encrypting an empty string raises BYOKEncryptionError."""
        with pytest.raises(BYOKEncryptionError, match="Cannot encrypt empty API key"):
            vault.encrypt("")

    def test_encrypt_none_raises_byok_encryption_error(self, vault):
        """Encrypting None raises BYOKEncryptionError."""
        with pytest.raises(BYOKEncryptionError, match="Cannot encrypt empty API key"):
            vault.encrypt(None)  # type: ignore

    def test_decrypt_empty_bytes_raises_byok_encryption_error(self, vault):
        """Decrypting empty bytes raises BYOKEncryptionError."""
        with pytest.raises(BYOKEncryptionError, match="Cannot decrypt empty value"):
            vault.decrypt(b"")

    def test_decrypt_corrupted_ciphertext_raises_invalid_token(self, vault):
        """Decrypting corrupted ciphertext raises BYOKEncryptionError wrapping InvalidToken."""
        corrupted = b"not_a_valid_fernet_token"
        with pytest.raises(BYOKEncryptionError, match="Invalid encryption key or corrupted data"):
            vault.decrypt(corrupted)

    def test_different_vault_instances_use_same_key_and_round_trip(self, monkeypatch):
        """Two vault instances with the same key can decrypt each other's ciphertexts."""
        monkeypatch.setattr(
            "security.byok_vault.get_secret",
            lambda k, d=None: {
                "BYOK_MASTER_KEY": "m" * 32,
                "SECRET_KEY": None,
            }.get(k),
        )

        vault1 = BYOKKeyVault()
        vault2 = BYOKKeyVault()

        original = "mpk_abcdefghijklmnopqrstuvwxyz"
        encrypted = vault1.encrypt(original)
        decrypted = vault2.decrypt(encrypted)
        assert decrypted == original


# ---------------------------------------------------------------------------
# mask_key
# ---------------------------------------------------------------------------


class TestMaskKey:
    """Tests for API key masking."""

    @pytest.fixture
    def vault(self, monkeypatch):
        monkeypatch.setattr("security.byok_vault.get_secret", lambda k, d=None: None)
        return BYOKKeyVault()

    def test_empty_string_returns_asterisks(self, vault):
        assert vault.mask_key("") == "****"

    def test_none_returns_asterisks(self, vault):
        assert vault.mask_key(None) == "****"  # type: ignore

    def test_short_key_up_to_four_chars_returns_asterisks(self, vault):
        """Keys with ≤4 characters are fully redacted."""
        assert vault.mask_key("ab") == "****"
        assert vault.mask_key("abcd") == "****"

    def test_five_char_key_shows_last_four(self, vault):
        """A 5-char key shows 1 asterisk + last 4 chars."""
        assert vault.mask_key("abcde") == "*bcde"

    def test_normal_key_shows_last_four(self, vault):
        """A normal key is masked leaving the last 4 characters visible."""
        # "sk-abcdefghij" → 13 chars → 9 asterisks + "ghij"
        masked = vault.mask_key("sk-abcdefghij")
        assert masked.endswith("ghij")
        assert len(masked) == len("sk-abcdefghij")
        assert masked.count("*") == 9

    def test_long_key(self, vault):
        """A long key is masked correctly."""
        key = "sk-" + "a" * 50
        masked = vault.mask_key(key)
        assert masked.endswith(key[-4:])


# ---------------------------------------------------------------------------
# validate_api_key — httpx.AsyncClient mocked via patch at httpx module
# ---------------------------------------------------------------------------


def _make_mock_client(response_or_exc):
    """Build an async-context-manager mock whose .get() raises or returns response."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    if isinstance(response_or_exc, Exception):
        mock_client.get = AsyncMock(side_effect=response_or_exc)
    else:
        mock_resp = MagicMock()
        for k, v in response_or_exc.items():
            setattr(mock_resp, k, v)
        mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


class TestValidateApiKey:
    """Tests for API key provider dispatch and error handling."""

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises(self):
        """When provider is neither OPENROUTER nor OPENAI, BYOKValidationError is raised."""
        # LLMProvider enum only has OPENROUTER and OPENAI, so we patch to simulate
        # a third (unsupported) provider value.
        unsupported = object()  # dummy object, not a valid LLMProvider
        with pytest.raises(BYOKValidationError, match="Unsupported provider"):
            await validate_api_key("test-key", unsupported)  # type: ignore

    @pytest.mark.asyncio
    async def test_validate_openrouter_key_200(self):
        """OPENROUTER validation returns True on 200 response."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 200}),
        ):
            from security.byok_vault import _validate_openrouter_key

            result = await _validate_openrouter_key("sk-testkey12345678901234567890")
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_openai_key_200(self):
        """OPENAI validation returns True on 200 response."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 200}),
        ):
            from security.byok_vault import _validate_openai_key

            result = await _validate_openai_key("sk-testkey12345678901234567890")
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_openrouter_key_401(self):
        """OPENROUTER validation raises BYOKValidationError on 401."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 401}),
        ):
            from security.byok_vault import _validate_openrouter_key

            with pytest.raises(BYOKValidationError, match="invalid"):
                await _validate_openrouter_key("sk-badkey")

    @pytest.mark.asyncio
    async def test_validate_openai_key_429_raises_rate_limit(self):
        """OPENAI validation raises BYOKValidationError on 429."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 429}),
        ):
            from security.byok_vault import _validate_openai_key

            with pytest.raises(BYOKValidationError, match="rate-limited"):
                await _validate_openai_key("sk-test")

    @pytest.mark.asyncio
    async def test_validate_openrouter_key_timeout(self):
        """OPENROUTER validation raises BYOKValidationError on timeout."""
        import httpx

        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client(httpx.TimeoutException("timed out")),
        ):
            from security.byok_vault import _validate_openrouter_key

            with pytest.raises(BYOKValidationError, match="timed out"):
                await _validate_openrouter_key("sk-test")

    @pytest.mark.asyncio
    async def test_validate_openai_key_generic_exception(self):
        """OPENAI validation raises BYOKValidationError on unexpected exception."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client(RuntimeError("unexpected")),
        ):
            from security.byok_vault import _validate_openai_key

            with pytest.raises(BYOKValidationError, match="Failed to validate"):
                await _validate_openai_key("sk-test")

    @pytest.mark.asyncio
    async def test_validate_openrouter_key_other_status_returns_false(self):
        """OPENROUTER validation returns False for unexpected status codes."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 500}),
        ):
            from security.byok_vault import _validate_openrouter_key

            result = await _validate_openrouter_key("sk-test")
            assert result is False

    @pytest.mark.asyncio
    async def test_dispatches_to_openrouter(self):
        """When provider is OPENROUTER, _validate_openrouter_key is called."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 200}),
        ):
            result = await validate_api_key(
                "sk-testkey12345678901234567890", LLMProvider.OPENROUTER
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_dispatches_to_openai(self):
        """When provider is OPENAI, _validate_openai_key is called."""
        with patch(
            "httpx.AsyncClient",
            return_value=_make_mock_client({"status_code": 200}),
        ):
            result = await validate_api_key(
                "sk-testkey12345678901234567890", LLMProvider.OPENAI
            )
            assert result is True


# ---------------------------------------------------------------------------
# PIIScrubbingFilter
# ---------------------------------------------------------------------------


class TestPIIScrubbingFilter:
    """Tests for PII scrubbing in log messages."""

    @pytest.fixture
    def filt(self):
        return PIIScrubbingFilter()

    def test_scrubs_sk_api_key(self, filt):
        """sk-... patterns are redacted."""
        msg = "Using API key sk-abcdefghijklmnopqrstuvwxyz for request"
        scrubbed = filt._scrub_message(msg)
        assert "sk-abcdef" not in scrubbed
        assert "***REDACTED_API_KEY***" in scrubbed

    def test_scrubs_mpk_api_key(self, filt):
        """mpk_... patterns are redacted."""
        msg = "Token mpk_abcdefghijklmnopqrstuvwxyz is invalid"
        scrubbed = filt._scrub_message(msg)
        assert "mpk_abcdef" not in scrubbed
        assert "***REDACTED_API_KEY***" in scrubbed

    def test_scrubs_bearer_jwt_token(self, filt):
        """Bearer JWT token patterns are redacted."""
        msg = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.signature"
        scrubbed = filt._scrub_message(msg)
        assert "***REDACTED_API_KEY***" in scrubbed
        assert "eyJzdWIiOiIxIn0" not in scrubbed

    def test_scrubs_openrouter_pipe_key(self, filt):
        """openrouter|... patterns are redacted."""
        msg = "Provider openrouter|abcdefghijklmnopqrstuvwxyz response OK"
        scrubbed = filt._scrub_message(msg)
        assert "openrouter|abcdef" not in scrubbed
        assert "***REDACTED_API_KEY***" in scrubbed

    def test_scrub_message_idempotent_on_clean_message(self, filt):
        """A clean message passes through unchanged."""
        clean = "This is a normal log message with no secrets."
        assert filt._scrub_message(clean) == clean

    def test_filter_applies_to_record(self, filt):
        """The filter method modifies record.msg in place."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Using sk-abcdefghijklmnopqrstuvwxyz here",
            args=(),
            exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert "***REDACTED_API_KEY***" in record.msg

    def test_filter_scrubs_record_args(self, filt):
        """The filter also scrubs record.args tuple entries."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Key %s used",
            args=("sk-abcdefghijklmnopqrstuvwxyz",),
            exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert "sk-abcdef" not in str(record.args)

    def test_filter_returns_true_when_msg_is_none(self, filt):
        """The filter returns True even when record.msg is None."""
        record = logging.makeLogRecord({"msg": None, "args": ()})
        assert filt.filter(record) is True


# ---------------------------------------------------------------------------
# setup_byok_logging
# ---------------------------------------------------------------------------


class TestSetupByokLogging:
    def test_attaches_filter_to_root_handlers(self, caplog):
        """setup_byok_logging attaches the PII filter to all root handlers."""
        with caplog.at_level(logging.INFO):
            setup_byok_logging()

        has_filter = any(
            isinstance(f, PIIScrubbingFilter)
            for handler in logging.root.handlers
            for f in handler.filters
        )
        assert has_filter, "PIIScrubbingFilter should be attached to root handlers"


# ---------------------------------------------------------------------------
# Module importability
# ---------------------------------------------------------------------------


def test_module_is_importable_via_src_layout():
    """Sanity check: the module is importable with the project's pythonpath=src."""
    import security.byok_vault as mod

    assert mod.__name__ == "security.byok_vault"