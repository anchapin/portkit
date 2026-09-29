"""Unit tests for ``api.conversions`` path-traversal helpers.

Issue #1784.

Covers:

- ``validate_path_safe``: ``..`` traversal, absolute paths, symlink escape,
  mixed separators, in-bounds containment.
- ``_chunks_dir_for_upload``: integration with ``safe_join`` to guarantee
  containment under ``TEMP_UPLOADS_DIR``.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from api.conversions import _chunks_dir_for_upload, validate_path_safe
from security.path_sanitization import PathSanitizationError


# ---------------------------------------------------------------------------
# validate_path_safe
# ---------------------------------------------------------------------------


class TestValidatePathSafe:
    """Table-driven cases for path-traversal containment."""

    def test_in_bounds_path(self, tmp_path: Path) -> None:
        base = tmp_path / "uploads"
        base.mkdir()
        # Create the subdirectory and file first
        subdir = base / "subdir"
        subdir.mkdir()
        safe_file = subdir / "file.jar"
        safe_file.write_text("data")
        # Use relative path from base
        rel = safe_file.relative_to(base)
        result = validate_path_safe(str(rel), base)
        assert result is True

    @pytest.mark.parametrize(
        "traversal",
        [
            "..",
            "../etc/passwd",
            "foo/../../etc/passwd",
            # Multiple dot-dot sequences
            "../../etc/passwd",
        ],
    )
    def test_rejects_dotdot_traversal(self, tmp_path: Path, traversal: str) -> None:
        base = tmp_path / "uploads"
        base.mkdir()
        result = validate_path_safe(traversal, base)
        assert result is False

    @pytest.mark.parametrize(
        "abs_path",
        [
            "/etc/passwd",
            "/home/user/file.jar",
            "/tmp/../etc/shadow",
        ],
    )
    def test_rejects_absolute_paths(self, tmp_path: Path, abs_path: str) -> None:
        base = tmp_path / "uploads"
        base.mkdir()
        result = validate_path_safe(abs_path, base)
        assert result is False

    def test_rejects_symlink_escape(self, tmp_path: Path) -> None:
        """A path that resolves outside base via symlink must be rejected."""
        base = tmp_path / "uploads"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.jar"
        secret.write_text("secret")

        link = base / "link_to_outside"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not permitted on this platform")

        # Construct a path that, when resolved, is outside base
        # via the symlink: base/link_to_outside/secret.jar resolves to outside/secret.jar
        evil = (link / "secret.jar").resolve()
        # The resolved path is outside base
        assert not str(evil).startswith(str(base.resolve()))
        # Try to compute relative path; ValueError means it really is outside
        try:
            rel = str(evil.relative_to(base.resolve()))
        except ValueError:
            # If relative_to fails, the path is definitely outside base
            rel = str(evil)
        # validate_path_safe must catch this and return False
        result = validate_path_safe(rel, base)
        assert result is False

    def test_accepts_deeply_nested_in_bounds(self, tmp_path: Path) -> None:
        """A deeply nested path that stays within base is accepted."""
        base = tmp_path / "uploads"
        base.mkdir()
        deep = base / "a" / "b" / "c" / "d" / "file.jar"
        deep.parent.mkdir(parents=True, exist_ok=True)
        deep.write_text("data")
        rel = str(deep.relative_to(base))
        result = validate_path_safe(rel, base)
        assert result is True

    def test_returns_false_on_invalid_path_chars(self, tmp_path: Path) -> None:
        """Paths with characters causing OSError should be rejected."""
        base = tmp_path / "uploads"
        base.mkdir()
        # A path with null byte is invalid on most filesystems
        result = validate_path_safe("file\x00.jar", base)
        assert result is False


# ---------------------------------------------------------------------------
# _chunks_dir_for_upload
# ---------------------------------------------------------------------------


class TestChunksDirForUpload:
    """Integration tests for the upload-chunks directory helper."""

    def test_returns_path_under_temp_uploads_dir(self, monkeypatch, tmp_path) -> None:
        """The returned path must be inside ``TEMP_UPLOADS_DIR``."""
        import api.conversions as conv

        monkeypatch.setattr(conv, "TEMP_UPLOADS_DIR", str(tmp_path))
        upload_id = str(uuid.uuid4())
        result = _chunks_dir_for_upload(upload_id)
        assert str(result).startswith(str(tmp_path))

    def test_raises_400_on_traversal_upload_id(self, monkeypatch, tmp_path) -> None:
        """A traversal attempt in upload ID must raise HTTP 400."""
        import api.conversions as conv
        from fastapi import HTTPException

        monkeypatch.setattr(conv, "TEMP_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc_info:
            _chunks_dir_for_upload("../../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_uuid_upload_id_accepted(self, monkeypatch, tmp_path) -> None:
        """A valid UUID string should be accepted without error."""
        import api.conversions as conv

        monkeypatch.setattr(conv, "TEMP_UPLOADS_DIR", str(tmp_path))
        upload_id = str(uuid.uuid4())
        result = _chunks_dir_for_upload(upload_id)
        assert result is not None
        assert upload_id in str(result)

    def test_raises_400_on_empty_upload_id(self, monkeypatch, tmp_path) -> None:
        """An empty upload ID must raise HTTP 400."""
        import api.conversions as conv
        from fastapi import HTTPException

        monkeypatch.setattr(conv, "TEMP_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc_info:
            _chunks_dir_for_upload("")
        assert exc_info.value.status_code == 400

    def test_raises_400_on_segment_with_separator(self, monkeypatch, tmp_path) -> None:
        """Upload ID with path separator must raise HTTP 400."""
        import api.conversions as conv
        from fastapi import HTTPException

        monkeypatch.setattr(conv, "TEMP_UPLOADS_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc_info:
            _chunks_dir_for_upload("abc/def")
        assert exc_info.value.status_code == 400
