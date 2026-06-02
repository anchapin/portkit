"""
Unit tests for orchestration/monitoring.py

Tests PerformanceMetric, ExecutionEvent, and OrchestrationMonitor classes.
"""

import pytest
import time
from orchestration.monitoring import (
    PerformanceMetric,
    ExecutionEvent,
    OrchestrationMonitor,
)
from orchestration.strategy_selector import OrchestrationStrategy


class TestPerformanceMetric:
    """Tests for PerformanceMetric dataclass."""

    def test_create_minimal(self):
        """Test creating a minimal PerformanceMetric."""
        metric = PerformanceMetric(metric_name="test_metric", value=1.0)
        assert metric.metric_name == "test_metric"
        assert metric.value == 1.0
        assert "timestamp" in metric.to_dict()

    def test_create_with_metadata(self):
        """Test creating a PerformanceMetric with metadata."""
        metric = PerformanceMetric(
            metric_name="test_metric",
            value=2.5,
            metadata={"key": "value"},
        )
        assert metric.metadata == {"key": "value"}

    def test_to_dict(self):
        """Test converting to dictionary."""
        metric = PerformanceMetric(metric_name="test", value=1.0)
        d = metric.to_dict()
        assert d["metric_name"] == "test"
        assert d["value"] == 1.0
        assert "timestamp" in d
        assert "metadata" in d


class TestExecutionEvent:
    """Tests for ExecutionEvent dataclass."""

    def test_create_minimal(self):
        """Test creating a minimal ExecutionEvent."""
        event = ExecutionEvent(event_type="task_started")
        assert event.event_type == "task_started"
        assert "timestamp" in event.to_dict()

    def test_create_with_details(self):
        """Test creating an ExecutionEvent with all details."""
        event = ExecutionEvent(
            event_type="task_completed",
            task_id="task-123",
            agent_name="converter",
            strategy="parallel",
            details={"duration": 10.5},
        )
        assert event.task_id == "task-123"
        assert event.agent_name == "converter"
        assert event.strategy == "parallel"
        assert event.details == {"duration": 10.5}

    def test_to_dict(self):
        """Test converting to dictionary."""
        event = ExecutionEvent(
            event_type="task_failed",
            task_id="task-456",
            details={"error": "timeout"},
        )
        d = event.to_dict()
        assert d["event_type"] == "task_failed"
        assert d["task_id"] == "task-456"
        assert d["details"]["error"] == "timeout"


class TestOrchestrationMonitor:
    """Tests for OrchestrationMonitor class."""

    def test_init_default(self):
        """Test initialization with default values."""
        # Don't start real-time monitoring to avoid thread issues
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        assert monitor.enable_real_time_monitoring is False
        assert monitor.metrics_retention_hours == 24
        assert monitor.metrics == []
        assert monitor.execution_events == []
        assert monitor.active_executions == {}

    def test_init_custom(self):
        """Test initialization with custom values."""
        monitor = OrchestrationMonitor(
            enable_real_time_monitoring=False,
            metrics_retention_hours=48,
        )
        assert monitor.metrics_retention_hours == 48

    def test_init_custom_alert_thresholds(self):
        """Test initialization with custom alert thresholds."""
        custom_thresholds = {"task_failure_rate": 0.3}
        monitor = OrchestrationMonitor(
            enable_real_time_monitoring=False,
            alert_thresholds=custom_thresholds,
        )
        assert monitor.alert_thresholds["task_failure_rate"] == 0.3

    def test_record_execution_start(self):
        """Test recording execution start."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        monitor.record_execution_start(
            execution_id="exec-1",
            strategy=OrchestrationStrategy.SEQUENTIAL,
            task_count=5,
        )
        assert "exec-1" in monitor.active_executions
        assert len(monitor.execution_events) == 1
        assert monitor.execution_events[0].event_type == "execution_started"

    def test_record_execution_end(self):
        """Test recording execution end."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        monitor.record_execution_start(
            execution_id="exec-1",
            strategy=OrchestrationStrategy.PARALLEL_BASIC,
            task_count=3,
        )
        monitor.record_execution_end(
            execution_id="exec-1",
            success=True,
            final_results={"overall_success_rate": 1.0},
        )
        assert "exec-1" not in monitor.active_executions

    def test_get_execution_events(self):
        """Test getting execution events."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        monitor.record_execution_start(
            execution_id="exec-1",
            strategy=OrchestrationStrategy.SEQUENTIAL,
            task_count=2,
        )
        events = monitor.get_execution_events()
        assert isinstance(events, list)
        assert len(events) == 1
        # Returns dicts, not ExecutionEvent objects
        assert events[0]["event_type"] == "execution_started"

    def test_get_performance_summary(self):
        """Test getting performance summary."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        summary = monitor.get_performance_summary()
        assert isinstance(summary, dict)

    def test_get_detailed_metrics(self):
        """Test getting detailed metrics."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        metrics = monitor.get_detailed_metrics()
        assert isinstance(metrics, list)

    def test_export_metrics(self, tmp_path):
        """Test exporting metrics."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        export_file = tmp_path / "metrics.json"
        result = monitor.export_metrics(str(export_file))
        assert result is True
        assert export_file.exists()

    def test_add_alert_callback(self):
        """Test adding an alert callback."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)
        callback_called = []

        def my_callback(alert_type, details):
            callback_called.append((alert_type, details))

        monitor.add_alert_callback(my_callback)
        assert len(monitor.alert_callbacks) == 1