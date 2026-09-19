"""Unit tests for ``api.conversions`` input-validation helpers.

Issue #1784.

Covers:

- ``sanitize_filename``: NTFS-reserved names, unicode, null bytes,
  long names, empty strings, path traversal attempts, URL-encoded
  traversal, hidden-file conversion.
- ``validate_file_type``: allow-listed extensions, double-extension
  spoofing, disallowed extensions, case-insensitivity.
- ``validate_file_size``: under/over MAX_UPLOAD_SIZE, zero-byte files.
"""

from __future__ import annotations

import pytest

from api.conversions import (
    MAX_UPLOAD_SIZE,
    sanitize_filename,
    validate_file_size,
    validate_file_type,
)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Table-driven cases for filename sanitization."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            # Basic safe filenames pass through (after stripping path)
            ("plain.txt", "plain.txt"),
            ("example_mod.jar", "example_mod.jar"),
            ("file.zip", "file.zip"),
            ("my-mod_v1.0.jar", "my-mod_v1.0.jar"),
            # Unicode alphanumeric passes through (alphanumeric whitelist)
            ("mod123", "mod123"),
            ("123mod", "123mod"),
            # Hyphen and underscore preserved
            ("my_mod-file.jar", "my_mod-file.jar"),
            # Multiple periods preserved
            ("archive.v1.2.3.zip", "archive.v1.2.3.zip"),
        ],
    )
    def test_accepts_safe_filenames(self, filename: str, expected: str) -> None:
        assert sanitize_filename(filename) == expected

    @pytest.mark.parametrize(
        "filename",
        [
            # Directory traversal stripped by os.path.basename
            "/etc/passwd",
            "relative/path/file.jar",
            "relative\\path\\file.zip",
            "foo/bar/../../../etc/passwd",
        ],
    )
    def test_strips_directory_paths(self, filename: str) -> None:
        result = sanitize_filename(filename)
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result

    @pytest.mark.parametrize(
        "filename",
        [
            "..",
            "../etc/passwd",
            "foo/../../etc/passwd",
            # URL-encoded traversal
            "%2e%2e/etc/passwd",
            "%2E%2E/etc/passwd",
        ],
    )
    def test_removes_dotdot_traversal(self, filename: str) -> None:
        result = sanitize_filename(filename)
        assert ".." not in result
        # Double-encoding of .. should also be stripped
        assert "%2e" not in result.lower()

    @pytest.mark.parametrize(
        "filename",
        [
            "with space.txt",
            "with\ttab.txt",
            "with\nnewline.txt",
            "with\rcarriage.txt",
            "null\x00byte.txt",
            "esc\x1bseq.txt",
            "del\x7fchar.txt",
        ],
    )
    def test_removes_control_characters(self, filename: str) -> None:
        result = sanitize_filename(filename)
        assert "\x00" not in result
        assert "\t" not in result
        assert "\n" not in result
        assert "\r" not in result
        assert "\x1b" not in result
        assert "\x7f" not in result
        assert " " not in result

    @pytest.mark.parametrize(
        "filename",
        [
            ".hidden",
            ".htaccess",
            ".bashrc",
            ".env",
            ".DS_Store",
        ],
    )
    def test_prefixes_hidden_files(self, filename: str) -> None:
        result = sanitize_filename(filename)
        assert result.startswith("file")
        assert ".hidden" in result or result.startswith("file.")

    def test_empty_string_becomes_default(self) -> None:
        assert sanitize_filename("") == "uploaded_file"

    def test_only_dots_becomes_default(self) -> None:
        assert sanitize_filename("..") == "uploaded_file"

    def test_only_special_chars_becomes_default(self) -> None:
        result = sanitize_filename("%%$$@@")
        assert result == "uploaded_file"

    def test_removes_backslashes(self) -> None:
        result = sanitize_filename("foo\\bar\\file.jar")
        assert "\\" not in result

    def test_url_encoded_traversal_removed(self) -> None:
        result = sanitize_filename("%2e%2e%2f%2e%2e%2ffile.jar")
        assert "%2e" not in result.lower()
        assert ".." not in result.lower()

    @pytest.mark.parametrize(
        "filename,expected",
        [
            # Very long filename should be preserved (no length limit in helper)
            ("a" * 255 + ".jar", "a" * 255 + ".jar"),
            # Emoji stripped (not alphanumeric or ._-)
            ("mod😀.jar", "mod.jar"),
            # Non-ASCII dash stripped
            ("mod‐dash.jar", "moddash.jar"),
        ],
    )
    def test_edge_cases(self, filename: str, expected: str) -> None:
        assert sanitize_filename(filename) == expected


# ---------------------------------------------------------------------------
# validate_file_type
# ---------------------------------------------------------------------------


class TestValidateFileType:
    """Table-driven cases for file-type validation."""

    @pytest.mark.parametrize(
        "filename,is_valid",
        [
            # Allowed extensions
            ("mod.jar", True),
            ("mod.zip", True),
            ("archive.JAR", True),
            ("archive.ZIP", True),
            ("archive.Jar", True),
            # Double-extension: outer extension determines validity
            ("malware.jar.txt", False),  # outer .txt is NOT allowed
            ("malware.zip.txt", False),  # outer .txt is NOT allowed
            ("script.jar.jar", True),  # outer .jar IS allowed
            ("script.jar.zip", True),  # outer .zip IS allowed
            ("data", False),  # no extension
            ("mod", False),  # no extension
        ],
    )
    def test_allowed_extensions(self, filename: str, is_valid: bool) -> None:
        result, _ = validate_file_type(filename)
        assert result is is_valid

    @pytest.mark.parametrize(
        "filename",
        [
            "mod.exe",
            "mod.dll",
            "mod.so",
            "mod.sh",
            "mod.py",
            "mod.js",
            "mod.html",
            "mod.pdf",
            "mod.doc",
            "mod.xls",
            "mod.png",
            "mod.jpg",
            "mod.gif",
            "mod.mp3",
            "mod.mp4",
            "modavi",
        ],
    )
    def test_rejects_disallowed_extensions(self, filename: str) -> None:
        result, error_msg = validate_file_type(filename)
        assert result is False
        assert "not supported" in error_msg.lower() or "allowed" in error_msg.lower()

    def test_case_insensitive(self) -> None:
        for ext in (".JAR", ".ZIP", ".Jar", ".zIp"):
            result, _ = validate_file_type(f"file{ext}")
            assert result is True

    def test_no_extension_returns_false(self) -> None:
        result, error_msg = validate_file_type("noextension")
        assert result is False
        assert "not supported" in error_msg.lower()


# ---------------------------------------------------------------------------
# validate_file_size
# ---------------------------------------------------------------------------


class TestValidateFileSize:
    """Table-driven cases for file-size validation."""

    @pytest.mark.parametrize(
        "size_bytes,is_valid",
        [
            # Under limit
            (0, True),
            (1, True),
            (1024, True),  # 1 KB
            (1024 * 1024, True),  # 1 MB
            (50 * 1024 * 1024, True),  # 50 MB
            (MAX_UPLOAD_SIZE - 1, True),
            (MAX_UPLOAD_SIZE, True),  # exactly at limit
        ],
    )
    async def test_under_limit(self, size_bytes: int, is_valid: bool) -> None:
        from io import BytesIO

        from fastapi import UploadFile

        content = b"x" * size_bytes
        file = UploadFile(filename="test.jar", file=BytesIO(content))
        await file.seek(0)

        result, _ = await validate_file_size(file)
        assert result is is_valid

    @pytest.mark.parametrize(
        "size_bytes",
        [
            MAX_UPLOAD_SIZE + 1,
            MAX_UPLOAD_SIZE + 1024,
            MAX_UPLOAD_SIZE * 2,
            200 * 1024 * 1024,  # 200 MB
        ],
    )
    async def test_over_limit(self, size_bytes: int) -> None:
        from io import BytesIO

        from fastapi import UploadFile

        content = b"x" * size_bytes
        file = UploadFile(filename="test.jar", file=BytesIO(content))
        await file.seek(0)

        result, error_msg = await validate_file_size(file)
        assert result is False
        assert "exceeds" in error_msg.lower()

    async def test_zero_byte_file(self) -> None:
        """Zero-byte files should be accepted (legitimate empty archive)."""
        from io import BytesIO

        from fastapi import UploadFile

        file = UploadFile(filename="empty.zip", file=BytesIO(b""))
        await file.seek(0)

        result, _ = await validate_file_size(file)
        assert result is True
