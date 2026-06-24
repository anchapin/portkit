"""
Regression tests for ``security.resource_limits.ResourceLimiter``.

Covers the four raise-branches in ``check_limits`` (lines 180/184/188/196),
the concurrent-cap rejection and counter-decrement-in-finally paths in
``track_operation``, and the exception→False path in
``check_available_disk_space``.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from security.resource_limits import (
    ResourceLimiter,
    ResourceLimits,
    ResourceLimitExceeded,
)


@pytest.mark.unit
class TestResourceLimiterCheckLimits:
    """Exercise ResourceLimiter.check_limits rejection branches."""

    def _limiter(self, **kwargs) -> ResourceLimiter:
        """Build a limiter with tiny limits so any usage triggers the branch."""
        limits = ResourceLimits(
            max_memory_mb=1,
            max_disk_usage_mb=1,
            max_processing_time_seconds=1,
            max_open_files=1,
            max_concurrent_uploads=1,
            max_concurrent_extractions=1,
        )
        limiter = ResourceLimiter(limits)
        # Start tracking so elapsed time is measured
        limiter.start_tracking(Path("/tmp"))
        return limiter

    def test_raises_on_memory_exceeded(self):
        limiter = self._limiter()
        with patch.object(limiter, "_get_memory_usage_mb", return_value=9999.0):
            with pytest.raises(ResourceLimitExceeded) as exc_info:
                limiter.check_limits()
            assert exc_info.value.resource_type == "memory"
            assert exc_info.value.current == 9999.0
            assert exc_info.value.limit == 1

    def test_raises_on_disk_exceeded(self):
        limiter = self._limiter()
        limiter._disk_usage_path = Path("/tmp")
        # Ensure memory/time/files don't trigger first by mocking them to 0
        with patch.object(limiter, "_get_memory_usage_mb", return_value=0.0):
            with patch.object(limiter, "_get_open_file_count", return_value=0):
                with patch.object(limiter, "_get_cpu_time", return_value=0.0):
                    with patch.object(limiter, "_get_directory_size_mb", return_value=9999.0):
                        with pytest.raises(ResourceLimitExceeded) as exc_info:
                            limiter.check_limits()
                        assert exc_info.value.resource_type == "disk"

    def test_raises_on_processing_time_exceeded(self):
        limiter = self._limiter()
        # Ensure memory/disk/files don't trigger first
        with patch.object(limiter, "_get_memory_usage_mb", return_value=0.0):
            with patch.object(limiter, "_get_open_file_count", return_value=0):
                with patch.object(limiter, "_get_cpu_time", return_value=0.0):
                    with patch.object(limiter, "_get_directory_size_mb", return_value=0.0):
                        # Patch datetime.now to return a time far in the future
                        from datetime import datetime, timezone
                        import unittest.mock

                        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
                        with unittest.mock.patch(
                            "security.resource_limits.datetime"
                        ) as mock_dt:
                            mock_dt.now.return_value = future
                            with pytest.raises(ResourceLimitExceeded) as exc_info:
                                limiter.check_limits()
                            assert exc_info.value.resource_type == "processing_time"

    def test_raises_on_open_files_exceeded(self):
        limiter = self._limiter()
        # Also mock disk to prevent disk check from triggering first
        with patch.object(limiter, "_get_memory_usage_mb", return_value=0.0):
            with patch.object(limiter, "_get_directory_size_mb", return_value=0.0):
                with patch.object(limiter, "_get_open_file_count", return_value=9999):
                    with patch.object(limiter, "_get_cpu_time", return_value=0.0):
                        with pytest.raises(ResourceLimitExceeded) as exc_info:
                            limiter.check_limits()
                        assert exc_info.value.resource_type == "open_files"


@pytest.mark.unit
class TestResourceLimiterTrackOperation:
    """Exercise track_operation concurrent-cap and finally-decrement branches."""

    def _limiter(self) -> ResourceLimiter:
        limits = ResourceLimits(
            max_concurrent_uploads=1,
            max_concurrent_extractions=1,
        )
        return ResourceLimiter(limits)

    def test_upload_rejects_when_at_capacity(self):
        limiter = self._limiter()
        # Use nested context managers so both operations are active simultaneously
        with pytest.raises(ResourceLimitExceeded) as exc_info:
            with limiter.track_operation("upload"):
                # While this upload is active, try to start another
                with limiter.track_operation("upload"):
                    pass
        assert exc_info.value.resource_type == "concurrent_uploads"

    def test_extraction_rejects_when_at_capacity(self):
        limiter = self._limiter()
        with pytest.raises(ResourceLimitExceeded) as exc_info:
            with limiter.track_operation("extraction"):
                with limiter.track_operation("extraction"):
                    pass
        assert exc_info.value.resource_type == "concurrent_extractions"

    def test_upload_counter_decremented_in_finally_when_body_raises(self):
        """Counter must be decremented even when the body raises."""
        limiter = self._limiter()
        assert limiter._active_operations["uploads"] == 0
        try:
            with limiter.track_operation("upload"):
                assert limiter._active_operations["uploads"] == 1
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        # Counter MUST be zero after the finally block
        assert limiter._active_operations["uploads"] == 0

    def test_extraction_counter_decremented_in_finally_when_body_raises(self):
        """Counter must be decremented even when the body raises."""
        limiter = self._limiter()
        assert limiter._active_operations["extractions"] == 0
        try:
            with limiter.track_operation("extraction"):
                assert limiter._active_operations["extractions"] == 1
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert limiter._active_operations["extractions"] == 0

    def test_check_limits_called_inside_operation_context(self):
        """check_limits is called inside the context manager body."""
        limiter = ResourceLimiter(
            ResourceLimits(
                max_concurrent_uploads=10,
                max_concurrent_extractions=10,
                max_memory_mb=0,  # Any memory usage will exceed
                max_disk_usage_mb=1000,
                max_processing_time_seconds=300,
                max_open_files=100,
            )
        )
        with patch.object(limiter, "_get_memory_usage_mb", return_value=9999.0):
            with pytest.raises(ResourceLimitExceeded) as exc_info:
                with limiter.track_operation("upload"):
                    pass
            assert exc_info.value.resource_type == "memory"


@pytest.mark.unit
class TestResourceLimiterCheckAvailableDiskSpace:
    """Exercise check_available_disk_space paths."""

    def _limiter(self) -> ResourceLimiter:
        return ResourceLimiter()

    def test_returns_true_when_space_sufficient(self, tmp_path: Path):
        limiter = self._limiter()
        # Mock shutil.disk_usage to return plenty of free space
        fake_stat = SimpleNamespace(free=100 * 1024 * 1024 * 1024)  # 100 GB
        with patch("shutil.disk_usage", return_value=fake_stat):
            result = limiter.check_available_disk_space(tmp_path, required_mb=1000)
            assert result is True

    def test_returns_false_when_space_insufficient(self, tmp_path: Path):
        limiter = self._limiter()
        fake_stat = SimpleNamespace(free=1 * 1024 * 1024)  # 1 MB
        with patch("shutil.disk_usage", return_value=fake_stat):
            result = limiter.check_available_disk_space(tmp_path, required_mb=1000)
            assert result is False

    def test_returns_false_when_disk_usage_raises(self, tmp_path: Path):
        limiter = self._limiter()
        with patch("shutil.disk_usage", side_effect=OSError("mocked error")):
            result = limiter.check_available_disk_space(tmp_path, required_mb=1000)
            assert result is False


@pytest.mark.unit
class TestResourceLimiterStartStopTracking:
    """Basic start/stop tracking smoke tests."""

    def test_start_then_stop_returns_usage(self):
        limiter = ResourceLimiter()
        limiter.start_tracking(Path("/tmp"))
        usage = limiter.stop_tracking()
        assert usage.processing_time_seconds >= 0
        assert isinstance(usage.memory_mb, float)

    def test_get_current_usage_returns_all_zeros_when_no_tracking(self):
        limiter = ResourceLimiter()
        # Mock all the get_* methods to ensure predictable values
        with patch.object(limiter, "_get_memory_usage_mb", return_value=0.0):
            with patch.object(limiter, "_get_directory_size_mb", return_value=0.0):
                with patch.object(limiter, "_get_open_file_count", return_value=0):
                    with patch.object(limiter, "_get_cpu_time", return_value=0.0):
                        usage = limiter.get_current_usage()
                        assert usage.memory_mb == 0.0
                        assert usage.disk_mb == 0.0
                        assert usage.open_files == 0
                        assert usage.cpu_time_seconds == 0.0
                        assert usage.processing_time_seconds == 0.0
