"""
Regression tests for ``security.resource_limits`` module-level functions
(DiskSpaceMonitor, get_resource_limiter, reset_resource_limiter) and the
time_limit context manager.
"""

import signal
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest

from security.resource_limits import (
    DiskSpaceMonitor,
    ResourceLimiter,
    ResourceLimits,
    ResourceLimitExceeded,
    get_resource_limiter,
    reset_resource_limiter,
)


@pytest.mark.unit
class TestDiskSpaceMonitorCheckDiskSpace:
    """Exercise DiskSpaceMonitor.check_disk_space tri-state and error paths."""

    def _monitor(self) -> DiskSpaceMonitor:
        # Tiny thresholds so any non-zero free space triggers "ok"
        return DiskSpaceMonitor(warning_threshold_mb=500, critical_threshold_mb=100)

    def test_returns_ok_status_when_plenty_of_space(self, tmp_path: Path):
        monitor = self._monitor()
        # 1 TB free
        fake_stat = SimpleNamespace(
            total=1024 * 1024 * 1024 * 1024,
            used=100 * 1024 * 1024 * 1024,
            free=924 * 1024 * 1024 * 1024,
        )
        with patch("shutil.disk_usage", return_value=fake_stat):
            result = monitor.check_disk_space(tmp_path)
            assert result["status"] == "ok"
            assert "free_mb" in result
            assert "percent_used" in result

    def test_returns_warning_status_when_space_below_warning_threshold(self, tmp_path: Path):
        monitor = self._monitor()
        # 300 MB free (below 500 MB warning, above 100 MB critical)
        fake_stat = SimpleNamespace(
            total=1024 * 1024 * 1024,
            used=724 * 1024 * 1024,
            free=300 * 1024 * 1024,
        )
        with patch("shutil.disk_usage", return_value=fake_stat):
            result = monitor.check_disk_space(tmp_path)
            assert result["status"] == "warning"

    def test_returns_critical_status_when_space_below_critical_threshold(
        self, tmp_path: Path
    ):
        monitor = self._monitor()
        # 50 MB free (below 100 MB critical)
        fake_stat = SimpleNamespace(
            total=1024 * 1024 * 1024,
            used=974 * 1024 * 1024,
            free=50 * 1024 * 1024,
        )
        with patch("shutil.disk_usage", return_value=fake_stat):
            result = monitor.check_disk_space(tmp_path)
            assert result["status"] == "critical"

    def test_returns_error_status_when_disk_usage_raises(self, tmp_path: Path):
        monitor = self._monitor()
        with patch("shutil.disk_usage", side_effect=OSError("mocked IO error")):
            result = monitor.check_disk_space(tmp_path)
            assert result["status"] == "error"
            assert "error" in result


@pytest.mark.unit
class TestResourceLimiterTimeLimit:
    """Exercise time_limit context manager signal and fallback paths."""

    def _limiter(self) -> ResourceLimiter:
        return ResourceLimiter(ResourceLimits(max_processing_time_seconds=300))

    def test_raises_when_operation_exceeds_time_limit(self):
        limiter = self._limiter()
        import time

        with pytest.raises(ResourceLimitExceeded) as exc_info:
            with limiter.time_limit(seconds=1):
                time.sleep(2)  # Exceed the 1-second limit
        assert exc_info.value.resource_type == "time"

    def test_succeeds_when_operation_completes_within_limit(self):
        limiter = self._limiter()
        import time

        # Should not raise
        with limiter.time_limit(seconds=5):
            time.sleep(0.1)

    def test_time_limit_fallback_on_signal_valueerror(self):
        """
        When signal.SIGALRM raises ValueError (non-main-thread or Windows),
        the fallback path should still enforce the time limit.
        """
        limiter = self._limiter()
        import time
        from unittest.mock import patch

        # Force the signal path to raise ValueError, exercising the fallback
        with patch("signal.signal", side_effect=ValueError("SIGALRM not available")):
            with pytest.raises(ResourceLimitExceeded) as exc_info:
                with limiter.time_limit(seconds=1):
                    time.sleep(2)
            assert exc_info.value.resource_type == "time"


@pytest.mark.unit
class TestModuleLevelResourceLimiterFunctions:
    """Exercise get_resource_limiter singleton and reset_resource_limiter."""

    def test_get_resource_limiter_returns_same_instance(self):
        reset_resource_limiter()  # Start clean
        first = get_resource_limiter()
        second = get_resource_limiter()
        assert first is second

    def test_reset_resource_limiter_clears_singleton(self):
        reset_resource_limiter()
        first = get_resource_limiter()
        reset_resource_limiter()
        second = get_resource_limiter()
        assert first is not second

    def test_resource_limiter_singleton_has_default_limits(self):
        reset_resource_limiter()
        limiter = get_resource_limiter()
        assert limiter.limits.max_memory_mb == 512
        assert limiter.limits.max_disk_usage_mb == 1024
        assert limiter.limits.max_processing_time_seconds == 300
        assert limiter.limits.max_concurrent_uploads == 10
        assert limiter.limits.max_concurrent_extractions == 5
