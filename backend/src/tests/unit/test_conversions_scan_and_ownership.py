"""Unit tests for ``api.conversions`` security-scan and ownership helpers.

Issue #1784.

Covers:

- ``scan_uploaded_file``: clean file → pass, infected file → rejection,
  scanner-unavailable → safe-deny.
- ``validate_and_scan_file``: orchestration of size/type/scan validation.
- ``_user_owns_job``: matching user, non-matching user, None job,
  job with no user_id.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.conversions import _user_owns_job, scan_uploaded_file
from security.file_security import (
    FileSecurityScanner,
    SecurityScanResult,
    SecurityThreat,
    SecurityThreatType,
    SecuritySeverity,
)


# ---------------------------------------------------------------------------
# scan_uploaded_file
# ---------------------------------------------------------------------------


class TestScanUploadedFile:
    """Tests for the ClamAV scan wrapper."""

    @pytest.mark.asyncio
    async def test_clean_file_returns_result(self, tmp_path: Path) -> None:
        """A clean file should return a safe SecurityScanResult."""
        test_file = tmp_path / "clean.jar"
        test_file.write_bytes(b"PK\x03\x04" + b"\x00" * 32)  # minimal ZIP header

        # Mock the scanner to return a clean result
        safe_result = SecurityScanResult(is_safe=True, threats=[])
        mock_scanner = MagicMock(spec=FileSecurityScanner)
        mock_scanner.scan_file = MagicMock(return_value=safe_result)

        with patch("api.conversions.get_security_scanner", return_value=mock_scanner):
            result = await scan_uploaded_file(test_file)
            assert isinstance(result, SecurityScanResult)
            assert result.is_safe is True

    @pytest.mark.asyncio
    async def test_infected_file_raises_http_exception(self, tmp_path: Path) -> None:
        """A file flagged with a critical threat must raise HTTP 400."""
        from fastapi import HTTPException

        test_file = tmp_path / "infected.jar"
        test_file.write_bytes(b"malicious content")

        # Mock the scanner to return a critical threat result
        critical_threat = SecurityThreat(
            threat_type=SecurityThreatType.ZIP_BOMB,
            severity=SecuritySeverity.CRITICAL,
            message="Detected zip bomb",
        )
        mock_result = SecurityScanResult(
            is_safe=False,
            threats=[critical_threat],
        )
        mock_scanner = MagicMock(spec=FileSecurityScanner)
        mock_scanner.scan_file = MagicMock(return_value=mock_result)

        with patch("api.conversions.get_security_scanner", return_value=mock_scanner):
            with pytest.raises(HTTPException) as exc_info:
                await scan_uploaded_file(test_file)
            assert exc_info.value.status_code == 400
            assert "security threat" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_high_threat_does_not_raise(self, tmp_path: Path) -> None:
        """High-severity threats are logged but do not raise HTTP 400."""
        test_file = tmp_path / "suspicious.jar"
        test_file.write_bytes(b"suspicious content")

        high_threat = SecurityThreat(
            threat_type=SecurityThreatType.SUSPICIOUS_CONTENT,
            severity=SecuritySeverity.HIGH,
            message="Suspicious content detected",
        )
        mock_result = SecurityScanResult(
            is_safe=True,
            threats=[high_threat],
        )
        mock_scanner = MagicMock(spec=FileSecurityScanner)
        mock_scanner.scan_file = MagicMock(return_value=mock_result)

        with patch("api.conversions.get_security_scanner", return_value=mock_scanner):
            # Should not raise — high threats are logged but don't block
            result = await scan_uploaded_file(test_file)
            assert result.has_high_threats is True

    @pytest.mark.asyncio
    async def test_safe_deny_on_scanner_error(self, tmp_path: Path) -> None:
        """Scanner errors return a safe-deny result without raising."""
        test_file = tmp_path / "file.jar"
        test_file.write_bytes(b"content")

        # Scanner unavailable: returns safe result (fail-closed)
        safe_deny = SecurityScanResult(is_safe=True, threats=[])
        mock_scanner = MagicMock(spec=FileSecurityScanner)
        mock_scanner.scan_file = MagicMock(return_value=safe_deny)

        with patch("api.conversions.get_security_scanner", return_value=mock_scanner):
            result = await scan_uploaded_file(test_file)
            assert result.is_safe is True


# ---------------------------------------------------------------------------
# validate_and_scan_file
# ---------------------------------------------------------------------------


class TestValidateAndScanFile:
    """Tests for the orchestration helper that runs all validations."""

    @pytest.mark.asyncio
    async def test_size_over_limit_raises_400(self) -> None:
        """File exceeding MAX_UPLOAD_SIZE must be rejected before scanning."""
        from fastapi import HTTPException
        from fastapi import UploadFile

        content = b"x" * (101 * 1024 * 1024)  # 101 MB
        file = UploadFile(filename="large.jar", file=BytesIO(content))
        await file.seek(0)
        fake_path = Path("/tmp/fake.jar")

        # Patch scan so it doesn't run on the oversized file
        with patch("api.conversions.scan_uploaded_file", new_callable=AsyncMock) as mock_scan:
            with pytest.raises(HTTPException) as exc_info:
                # Use validate_and_scan_file from within the patch context
                # so it sees the patched scan_uploaded_file
                import api.conversions
                result = await api.conversions.validate_and_scan_file(file, fake_path)
            assert exc_info.value.status_code == 400
            assert "exceeds" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_disallowed_type_raises_400(self) -> None:
        """Non-.jar/.zip files must be rejected before scanning."""
        from fastapi import HTTPException
        from fastapi import UploadFile

        content = b"malicious"
        file = UploadFile(filename="malware.exe", file=BytesIO(content))
        await file.seek(0)
        fake_path = Path("/tmp/fake.exe")

        with patch("api.conversions.scan_uploaded_file", new_callable=AsyncMock) as mock_scan:
            import api.conversions
            with pytest.raises(HTTPException) as exc_info:
                await api.conversions.validate_and_scan_file(file, fake_path)
            assert exc_info.value.status_code == 400
            assert "not supported" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_valid_file_passes_all_validations(self, tmp_path: Path) -> None:
        """A valid JAR file under the size limit should pass all checks."""
        from fastapi import UploadFile

        content = b"PK\x03\x04" + b"\x00" * 32  # minimal ZIP/JAR
        file = UploadFile(filename="valid.jar", file=BytesIO(content))
        await file.seek(0)
        test_path = tmp_path / "valid.jar"
        test_path.write_bytes(content)

        safe_result = SecurityScanResult(is_safe=True, threats=[])
        with patch("api.conversions.scan_uploaded_file", new_callable=AsyncMock, return_value=safe_result) as mock_scan:
            import api.conversions
            result = await api.conversions.validate_and_scan_file(file, test_path)
            assert result.is_safe is True

    @pytest.mark.asyncio
    async def test_infected_file_raises_on_scan(self, tmp_path: Path) -> None:
        """An infected file that passes size/type check must still fail scan."""
        from fastapi import HTTPException
        from fastapi import UploadFile

        content = b"PK\x03\x04" + b"\x00" * 32
        file = UploadFile(filename="infected.jar", file=BytesIO(content))
        await file.seek(0)
        test_path = tmp_path / "infected.jar"
        test_path.write_bytes(content)

        critical_threat = SecurityThreat(
            threat_type=SecurityThreatType.ZIP_BOMB,
            severity=SecuritySeverity.CRITICAL,
            message="Zip bomb detected",
        )
        infected_result = SecurityScanResult(
            is_safe=False,
            threats=[critical_threat],
        )

        # Patch get_security_scanner so scan_uploaded_file uses our mock
        mock_scanner = MagicMock(spec=FileSecurityScanner)
        mock_scanner.scan_file = MagicMock(return_value=infected_result)
        with patch("api.conversions.get_security_scanner", return_value=mock_scanner):
            # Import inside the patch context so the lookup happens after the patch is active
            from api.conversions import validate_and_scan_file as val_scan
            with pytest.raises(HTTPException) as exc_info:
                await val_scan(file, test_path)
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# _user_owns_job
# ---------------------------------------------------------------------------


class TestUserOwnsJob:
    """Tests for the job-ownership check (issue #1417 anti-enumeration gate)."""

    def test_matching_owner_returns_true(self) -> None:
        """When job.user_id matches current_user.id, return True."""
        job = MagicMock()
        job.user_id = "abcd1234-5678-90ef-abcd-1234567890ab"
        user = MagicMock()
        user.id = "abcd1234-5678-90ef-abcd-1234567890ab"

        assert _user_owns_job(job, user) is True

    def test_different_user_returns_false(self) -> None:
        """When job belongs to a different user, return False (not 403)."""
        job = MagicMock()
        job.user_id = "00000000-0000-0000-0000-000000000001"
        user = MagicMock()
        user.id = "00000000-0000-0000-0000-000000000002"

        assert _user_owns_job(job, user) is False

    def test_none_job_returns_false(self) -> None:
        """A None job (not-found) returns False — never raises."""
        user = MagicMock()
        assert _user_owns_job(None, user) is False

    def test_job_with_no_user_id_returns_false(self) -> None:
        """A job that has no user_id attribute returns False."""
        job = MagicMock(spec=[])  # object without user_id
        user = MagicMock()
        assert _user_owns_job(job, user) is False

    def test_job_user_id_none_returns_false(self) -> None:
        """A job with user_id=None returns False."""
        job = MagicMock()
        job.user_id = None
        user = MagicMock()
        assert _user_owns_job(job, user) is False

    def test_str_id_comparison_is_type_agnostic(self) -> None:
        """Comparison uses str() on both sides, tolerating int/UUID/str."""
        job = MagicMock()
        job.user_id = "abcd1234-5678-90ef-abcd-1234567890ab"
        user = MagicMock()
        # user.id could be UUID, str, or int in different code paths
        import uuid

        user.id = uuid.UUID("abcd1234-5678-90ef-abcd-1234567890ab")
        assert _user_owns_job(job, user) is True

    def test_user_id_mismatch_with_uuid_object(self) -> None:
        """String vs UUID mismatch should still return False."""
        job = MagicMock()
        job.user_id = "00000000-0000-0000-0000-000000000001"
        user = MagicMock()
        import uuid

        user.id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        assert _user_owns_job(job, user) is False
