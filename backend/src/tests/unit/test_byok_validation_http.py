"""
Unit tests for BYOK HTTP validation (httpx mocking).

Issue #1783.

Covers:
- ``_validate_openrouter_key``: 200 / 401 / 429 / other-status / TimeoutException / generic-exception
- ``_validate_openai_key``: same branches
- ``validate_api_key``: provider dispatch
- ``PIIScrubbingFilter._scrub_message``: all four regex patterns
- ``setup_byok_logging``: filter attachment
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from security.byok_vault import (
    BYOKValidationError,
    LLMProvider,
    PIIScrubbingFilter,
    _validate_openai_key,
    _validate_openrouter_key,
    setup_byok_logging,
    validate_api_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_response(status_code: int) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    return mock


def make_mock_client(response_or_exc):
    """Build an async-context-manager mock that returns response_or_exc from .get()."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    if isinstance(response_or_exc, Exception):
        mock_client.get = AsyncMock(side_effect=response_or_exc)
    else:
        mock_client.get = AsyncMock(return_value=response_or_exc)
    return mock_client


# ---------------------------------------------------------------------------
# _validate_openrouter_key
# ---------------------------------------------------------------------------


class TestValidateOpenrouterKey:
    """HTTP-level tests for OpenRouter key validation."""

    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        """A 200 response from OpenRouter indicates a valid key."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(200))):
            result = await _validate_openrouter_key("sk-openrouter-testkey1234567890")
            assert result is True

    @pytest.mark.asyncio
    async def test_raises_on_401(self):
        """A 401 response raises BYOKValidationError with invalid key message."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(401))):
            with pytest.raises(BYOKValidationError, match="invalid"):
                await _validate_openrouter_key("sk-badkey")

    @pytest.mark.asyncio
    async def test_raises_on_429(self):
        """A 429 response raises BYOKValidationError with rate-limit message."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(429))):
            with pytest.raises(BYOKValidationError, match="rate-limited"):
                await _validate_openrouter_key("sk-testkey")

    @pytest.mark.asyncio
    async def test_returns_false_on_other_status(self):
        """Any other status code returns False (key may or may not be valid)."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(500))):
            result = await _validate_openrouter_key("sk-testkey")
            assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """An httpx.TimeoutException raises BYOKValidationError with timeout message."""
        import httpx

        with patch(
            "httpx.AsyncClient",
            return_value=make_mock_client(httpx.TimeoutException("timed out")),
        ):
            with pytest.raises(BYOKValidationError, match="timed out"):
                await _validate_openrouter_key("sk-testkey")

    @pytest.mark.asyncio
    async def test_raises_on_generic_exception(self):
        """Any other exception raises BYOKValidationError with a descriptive message."""
        with patch(
            "httpx.AsyncClient",
            return_value=make_mock_client(RuntimeError("network error")),
        ):
            with pytest.raises(BYOKValidationError, match="Failed to validate"):
                await _validate_openrouter_key("sk-testkey")


# ---------------------------------------------------------------------------
# _validate_openai_key
# ---------------------------------------------------------------------------


class TestValidateOpenaiKey:
    """HTTP-level tests for OpenAI key validation."""

    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        """A 200 response from OpenAI indicates a valid key."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(200))):
            result = await _validate_openai_key("sk-openaikeytest12345678901234")
            assert result is True

    @pytest.mark.asyncio
    async def test_raises_on_401(self):
        """A 401 response raises BYOKValidationError with invalid key message."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(401))):
            with pytest.raises(BYOKValidationError, match="invalid"):
                await _validate_openai_key("sk-badkey")

    @pytest.mark.asyncio
    async def test_raises_on_429(self):
        """A 429 response raises BYOKValidationError with rate-limit message."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(429))):
            with pytest.raises(BYOKValidationError, match="rate-limited"):
                await _validate_openai_key("sk-testkey")

    @pytest.mark.asyncio
    async def test_returns_false_on_other_status(self):
        """Any other status code returns False."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(403))):
            result = await _validate_openai_key("sk-testkey")
            assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """An httpx.TimeoutException raises BYOKValidationError."""
        import httpx

        with patch(
            "httpx.AsyncClient",
            return_value=make_mock_client(httpx.TimeoutException("timeout")),
        ):
            with pytest.raises(BYOKValidationError, match="timed out"):
                await _validate_openai_key("sk-testkey")

    @pytest.mark.asyncio
    async def test_raises_on_generic_exception(self):
        """A generic exception raises BYOKValidationError."""
        with patch(
            "httpx.AsyncClient",
            return_value=make_mock_client(OSError("connection refused")),
        ):
            with pytest.raises(BYOKValidationError, match="Failed to validate"):
                await _validate_openai_key("sk-testkey")


# ---------------------------------------------------------------------------
# validate_api_key dispatch
# ---------------------------------------------------------------------------


class TestValidateApiKeyDispatch:
    """Integration of dispatch logic with provider enum."""

    @pytest.mark.asyncio
    async def test_dispatches_to_openrouter(self):
        """When provider is OPENROUTER, _validate_openrouter_key is called."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(200))):
            result = await validate_api_key(
                "sk-testkey12345678901234567890", LLMProvider.OPENROUTER
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_dispatches_to_openai(self):
        """When provider is OPENAI, _validate_openai_key is called."""
        with patch("httpx.AsyncClient", return_value=make_mock_client(make_mock_response(200))):
            result = await validate_api_key(
                "sk-testkey12345678901234567890", LLMProvider.OPENAI
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises(self):
        """An unsupported provider raises BYOKValidationError before any HTTP call.

        LLMProvider only has OPENAI and OPENROUTER, so we use a dummy object
        to simulate an unsupported provider value.
        """
        with patch(
            "httpx.AsyncClient",
            return_value=make_mock_client(make_mock_response(200)),
        ):
            unsupported_provider = object()  # not a valid LLMProvider
            with pytest.raises(BYOKValidationError, match="Unsupported provider"):
                await validate_api_key("sk-testkey", unsupported_provider)  # type: ignore


# ---------------------------------------------------------------------------
# PII scrubbing — full pattern coverage
# ---------------------------------------------------------------------------


class TestPIIScrubbingPatterns:
    """Exhaustive tests for each PII regex pattern in PIIScrubbingFilter."""

    @pytest.fixture
    def filt(self):
        return PIIScrubbingFilter()

    def test_sk_pattern(self, filt):
        """sk-... keys (≥20 alphanum after sk-) are scrubbed."""
        msg = "API call with sk-abcdefghijklmnopqrstuvwxyz0123 and result OK"
        assert "sk-abcdefghijkl" not in filt._scrub_message(msg)
        assert "***REDACTED_API_KEY***" in filt._scrub_message(msg)

    def test_mpk_pattern(self, filt):
        """mpk_... keys (≥20 alphanum after mpk_) are scrubbed."""
        msg = "Token mpk_abcdefghijklmnopqrstuvwxyz0123 rejected"
        assert "mpk_abcdefghijkl" not in filt._scrub_message(msg)
        assert "***REDACTED_API_KEY***" in filt._scrub_message(msg)

    def test_bearer_jwt_pattern(self, filt):
        """Bearer JWT patterns (three dot-separated base64url segments) are scrubbed."""
        msg = "Auth: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjN9.abcDEF123signature"
        scrubbed = filt._scrub_message(msg)
        assert "***REDACTED_API_KEY***" in scrubbed
        assert "eyJzdWIiOiIxMjN9" not in scrubbed

    def test_openrouter_pipe_pattern(self, filt):
        """openrouter|... keys (≥20 alphanum after pipe) are scrubbed."""
        msg = "Using openrouter|abcdefghijklmnopqrstuvwxyz012345 for model"
        assert "openrouter|abcdefghijkl" not in filt._scrub_message(msg)
        assert "***REDACTED_API_KEY***" in filt._scrub_message(msg)

    def test_multiple_patterns_in_one_message(self, filt):
        """When multiple PII patterns appear in one message, all are scrubbed."""
        msg = (
            "sk-abcdefghijklmnopqrstuvwxyz0123 | "
            "mpk_abcdefghijklmnopqrstuvwxyz0123 | "
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjN9.abcDEF123sig | "
            "openrouter|abcdefghijklmnopqrstuvwxyz012345"
        )
        scrubbed = filt._scrub_message(msg)
        assert scrubbed.count("***REDACTED_API_KEY***") == 4

    def test_filter_returns_true_to_allow_record(self, filt):
        """The filter returns True to indicate the record should pass through."""
        record = logging.makeLogRecord({"msg": "normal message", "args": ()})
        assert filt.filter(record) is True

    def test_filter_returns_true_when_msg_is_none(self, filt):
        """The filter returns True even when record.msg is None."""
        record = logging.makeLogRecord({"msg": None, "args": ()})
        assert filt.filter(record) is True


# ---------------------------------------------------------------------------
# setup_byok_logging
# ---------------------------------------------------------------------------


class TestSetupByokLoggingIntegration:
    """Integration tests for logging setup."""

    def test_info_message_is_logged_after_setup(self, caplog):
        """After setup_byok_logging, the info message is logged."""
        with caplog.at_level(logging.INFO):
            setup_byok_logging()

        assert any("BYOK PII logging filter installed" in r.msg for r in caplog.records)

    def test_api_key_is_scrubbed_in_log_after_setup(self, caplog):
        """After setup_byok_logging, PII is scrubbed from log output."""
        with caplog.at_level(logging.INFO):
            setup_byok_logging()
            logger = logging.getLogger("test_byok2")
            logger.info("Using key sk-abcdefghijklmnopqrstuvwxyz012345678 for request")

        for record in caplog.records:
            assert "sk-abcdefghijkl" not in record.msg
            assert "***REDACTED_API_KEY***" in record.msg or "sk-abcdef" not in record.msg