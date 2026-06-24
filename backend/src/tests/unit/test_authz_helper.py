"""
Regression tests for ``api._authz`` — specifically the anti-enumeration
invariant introduced in issue #1417: ``assert_owner`` returns 404 (never 403)
when a user requests a resource they don't own, to avoid leaking resource
existence to anonymous probers.

Also covers all ``get_current_user`` rejection branches (four 401 modes).
"""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api._authz import assert_owner, get_current_user
from security.auth import verify_api_key, verify_token


# ---------------------------------------------------------------------------
# Fake AsyncSession (mirrors test_security_auth_verify_api_key.py patterns)
# ---------------------------------------------------------------------------


class _ScalarResult:
    """Mimics the slice of the SQLAlchemy ``Result`` API used by get_current_user."""

    def __init__(self, rows: list[Any]):
        self._rows = rows

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _FakeAsyncSession:
    """Single-call fake that returns a canned User row."""

    def __init__(self, user: Any | None):
        self._user = user

    async def execute(self, _stmt: Any) -> _ScalarResult:
        return _ScalarResult([self._user] if self._user else [])


# ---------------------------------------------------------------------------
# Fake credentials
# ---------------------------------------------------------------------------


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ---------------------------------------------------------------------------
# Tests: get_current_user — mpk_ API-key path
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCurrentUserApiKeyPath:
    """Exercise get_current_user when the token starts with 'mpk_'."""

    async def test_valid_api_key_returns_user(self):
        fake_user = SimpleNamespace(id=uuid4(), email="api@example.com")
        with patch(
            "api._authz.verify_api_key", return_value=fake_user
        ) as mock_verify:
            user = await get_current_user(
                credentials=_credentials("mpk_test-api-key-12345678"),
                db=_FakeAsyncSession(fake_user),
            )
            assert user is fake_user
            mock_verify.assert_called_once()

    async def test_revoked_api_key_returns_none_raises_401(self):
        with patch("api._authz.verify_api_key", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    credentials=_credentials("mpk_revoked-key-12345678"),
                    db=_FakeAsyncSession(None),
                )
            assert exc_info.value.status_code == 401
            assert "Invalid or revoked API key" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: get_current_user — JWT path
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCurrentUserJwtPath:
    """Exercise get_current_user when the token is a plain JWT."""

    async def _call(self, token: str, user: Any | None):
        return await get_current_user(
            credentials=_credentials(token),
            db=_FakeAsyncSession(user),
        )

    async def test_valid_jwt_returns_user(self):
        fake_user = SimpleNamespace(id=uuid4(), email="jwt@example.com")
        with patch("api._authz.verify_token", return_value=str(fake_user.id)):
            user = await self._call("jwt.unsigned.token", fake_user)
            assert user is fake_user

    async def test_invalid_token_raises_401(self):
        with patch("api._authz.verify_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await self._call("invalid.jwt.token", None)
            assert exc_info.value.status_code == 401
            assert "Invalid or expired token" in exc_info.value.detail

    async def test_expired_token_raises_401(self):
        with patch("api._authz.verify_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await self._call("expired.jwt.token", None)
            assert exc_info.value.status_code == 401

    async def test_malformed_uuid_payload_raises_401(self):
        with patch("api._authz.verify_token", return_value="not-a-uuid-string"):
            with pytest.raises(HTTPException) as exc_info:
                await self._call("jwt.with.bad.payload", None)
            assert exc_info.value.status_code == 401
            assert "Invalid token payload" in exc_info.value.detail

    async def test_missing_user_raises_401(self):
        with patch("api._authz.verify_token", return_value=str(uuid4())):
            with pytest.raises(HTTPException) as exc_info:
                await self._call("jwt.no.such.user", None)
            assert exc_info.value.status_code == 401
            assert "User not found" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: assert_owner — the anti-enumeration invariant (issue #1417)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAssertOwnerAntiEnumeration:
    """
    Verify assert_owner returns 404 (NEVER 403) when:
    - resource is None
    - user does not own the resource

    This locks the anti-enumeration invariant as an executable regression test.
    """

    def _user(self, id: str | None = None):
        id = id or str(uuid4())
        return SimpleNamespace(id=id)

    def _resource(self, user_id: str):
        return SimpleNamespace(user_id=user_id)

    def test_none_resource_raises_404(self):
        user = self._user()
        with pytest.raises(HTTPException) as exc_info:
            assert_owner(None, user)
        assert exc_info.value.status_code == 404

    def test_non_owner_raises_404_never_403(self):
        """
        CRITICAL: This must always be 404, never 403.
        A 403 tells the prober "the resource exists but you don't have access".
        A 404 tells them nothing — preserving the anti-enumeration invariant.
        """
        owner_id = str(uuid4())
        other_user = self._user()
        resource = self._resource(owner_id)
        with pytest.raises(HTTPException) as exc_info:
            assert_owner(resource, other_user)
        assert exc_info.value.status_code == 404, (
            "assert_owner must return 404 (never 403) for non-owner access"
        )
        assert "Resource not found" in exc_info.value.detail

    def test_owner_returns_resource(self):
        owner_id = str(uuid4())
        owner_user = self._user(owner_id)
        resource = self._resource(owner_id)
        result = assert_owner(resource, owner_user)
        assert result is resource

    def test_owner_with_none_owner_field_raises_404(self):
        """A resource with owner_field=None should be treated as non-owned."""
        user = self._user()
        resource = SimpleNamespace(user_id=None)
        with pytest.raises(HTTPException) as exc_info:
            assert_owner(resource, user)
        assert exc_info.value.status_code == 404

    def test_owner_with_custom_owner_field(self):
        """assert_owner respects a custom owner_field name."""
        custom_owner_id = str(uuid4())
        owner_user = self._user(custom_owner_id)
        resource = SimpleNamespace(creator_id=custom_owner_id)
        result = assert_owner(resource, owner_user, owner_field="creator_id")
        assert result is resource

    def test_non_owner_with_custom_owner_field_raises_404(self):
        """Custom owner_field also returns 404 for non-owner."""
        owner_user = self._user()
        resource = SimpleNamespace(creator_id=str(uuid4()))  # Different user
        with pytest.raises(HTTPException) as exc_info:
            assert_owner(resource, owner_user, owner_field="creator_id")
        assert exc_info.value.status_code == 404

    def test_custom_not_found_detail(self):
        """assert_owner uses the provided not_found_detail in the 404 body."""
        user = self._user()
        resource = SimpleNamespace(user_id=str(uuid4()))  # Different user
        custom_msg = "custom-not-found-message"
        with pytest.raises(HTTPException) as exc_info:
            assert_owner(resource, user, not_found_detail=custom_msg)
        assert exc_info.value.status_code == 404
        assert custom_msg in exc_info.value.detail

    def test_str_owner_comparison(self):
        """assert_owner compares owner as string, so int UUIDs work too."""
        owner_id = uuid4()  # UUID object
        owner_user = SimpleNamespace(id=owner_id)
        # Resource stores owner as string
        resource = SimpleNamespace(user_id=str(owner_id))
        result = assert_owner(resource, owner_user)
        assert result is resource
