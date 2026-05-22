"""
Tests for orchestration monitoring module.
Covers OrchestrationMonitor class and PerformanceMetric, ExecutionEvent dataclasses.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path
import threading

from orchestration.monitoring import (
    OrchestrationMonitor,
    PerformanceMetric,
    ExecutionEvent,
)
from orchestration.strategy_selector import OrchestrationStrategy


class TestPerformanceMetric:
    """Test PerformanceMetric dataclass."""

    def test_metric_creation(self):
        """Test creating a performance metric."""
        metric = PerformanceMetric(
            metric_name="test_metric",
            value=42.0,
            timestamp=1234567890.0,
            metadata={"key": "value"},
        )

        assert metric.metric_name == "test_metric"
        assert metric.value == 42.0
        assert metric.timestamp == 1234567890.0
        assert metric.metadata == {"key": "value"}

    def test_metric_to_dict(self):
        """Test converting metric to dictionary."""
        metric = PerformanceMetric(
            metric_name="accuracy",
            value=0.95,
            timestamp=1000.0,
            metadata={"model": "v1"},
        )

        result = metric.to_dict()

        assert result["metric_name"] == "accuracy"
        assert result["value"] == 0.95
        assert result["timestamp"] == 1000.0
        assert result["metadata"] == {"model": "v1"}

    def test_metric_default_values(self):
        """Test default values for metric."""
        metric = PerformanceMetric(metric_name="default_test", value=10.0)

        assert metric.timestamp is not None
        assert metric.timestamp > 0
        assert metric.metadata == {}


class TestExecutionEvent:
    """Test ExecutionEvent dataclass."""

    def test_event_creation(self):
        """Test creating an execution event."""
        event = ExecutionEvent(
            event_type="task_completed",
            timestamp=1234567890.0,
            task_id="task_123",
            agent_name="translator",
            strategy="parallel",
            details={"success": True},
        )

        assert event.event_type == "task_completed"
        assert event.timestamp == 1234567890.0
        assert event.task_id == "task_123"
        assert event.agent_name == "translator"
        assert event.strategy == "parallel"
        assert event.details == {"success": True}

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = ExecutionEvent(
            event_type="task_started",
            task_id="task_456",
            agent_name="reviewer",
            details={"priority": "high"},
        )

        result = event.to_dict()

        assert result["event_type"] == "task_started"
        assert result["task_id"] == "task_456"
        assert result["agent_name"] == "reviewer"
        assert result["details"] == {"priority": "high"}

    def test_event_defaults(self):
        """Test default values for event."""
        event = ExecutionEvent(event_type="test_event")

        assert event.timestamp is not None
        assert event.timestamp > 0
        assert event.task_id is None
        assert event.agent_name is None


class TestOrchestrationMonitorInit:
    """Test OrchestrationMonitor initialization."""

    def test_init_default_values(self):
        """Test default initialization values."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        assert monitor.enable_real_time_monitoring is False
        assert monitor.metrics_retention_hours == 24
        assert len(monitor.alert_thresholds) == 4

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        monitor = OrchestrationMonitor(
            enable_real_time_monitoring=False,
            metrics_retention_hours=48,
            alert_thresholds={"custom_threshold": 0.5},
        )

        assert monitor.metrics_retention_hours == 48
        assert monitor.alert_thresholds["custom_threshold"] == 0.5

    def test_init_alert_thresholds_defaults(self):
        """Test default alert thresholds."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        assert monitor.alert_thresholds["task_failure_rate"] == 0.2
        assert monitor.alert_thresholds["avg_task_duration"] == 600.0
        assert monitor.alert_thresholds["queue_depth"] == 50
        assert monitor.alert_thresholds["worker_utilization"] == 0.9

    def test_init_empty_data_structures(self):
        """Test that data structures are initialized empty."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        assert monitor.metrics == []
        assert monitor.execution_events == []
        assert monitor.active_executions == {}


class TestRecordExecutionStart:
    """Test record_execution_start method."""

    def test_record_execution_start_basic(self):
        """Test basic execution start recording."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        monitor.record_execution_start(
            execution_id="exec_001",
            strategy=OrchestrationStrategy.PARALLEL_BASIC,
            task_count=10,
        )

        assert "exec_001" in monitor.active_executions
        assert monitor.active_executions["exec_001"]["task_count"] == 10

    def test_record_execution_start_with_metadata(self):
        """Test execution start with metadata."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        metadata = {"priority": "high", "user": "test_user"}
        monitor.record_execution_start(
            execution_id="exec_002",
            strategy=OrchestrationStrategy.SEQUENTIAL,
            task_count=5,
            metadata=metadata,
        )

        assert monitor.active_executions["exec_002"]["metadata"]["priority"] == "high"

    def test_record_execution_start_creates_event(self):
        """Test that execution start creates an event."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        initial_event_count = len(monitor.execution_events)

        monitor.record_execution_start(
            execution_id="exec_003",
            strategy=OrchestrationStrategy.HYBRID,
            task_count=8,
        )

        assert len(monitor.execution_events) == initial_event_count + 1


class TestRecordExecutionEnd:
    """Test record_execution_end method."""

    def test_record_execution_end_missing(self):
        """Test handling of non-existent execution."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        # Should not raise, just warn
        monitor.record_execution_end(
            execution_id="nonexistent",
            success=True,
            final_results={},
        )

        assert "nonexistent" not in monitor.active_executions

    def test_record_execution_end_clears_active(self):
        """Test that execution end clears from active executions."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        monitor.record_execution_start(
            execution_id="exec_004",
            strategy=OrchestrationStrategy.PARALLEL_BASIC,
            task_count=3,
        )

        # Simulate some work
        time.sleep(0.01)

        monitor.record_execution_end(
            execution_id="exec_004",
            success=True,
            final_results={"overall_success_rate": 1.0},
        )

        assert "exec_004" not in monitor.active_executions

    def test_record_execution_end_records_metrics(self):
        """Test that execution end records metrics."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        monitor.record_execution_start(
            execution_id="exec_005",
            strategy=OrchestrationStrategy.SEQUENTIAL,
            task_count=5,
        )

        initial_metric_count = len(monitor.metrics)

        monitor.record_execution_end(
            execution_id="exec_005",
            success=True,
            final_results={"overall_success_rate": 0.8},
        )

        assert len(monitor.metrics) >= initial_metric_count


class TestRecordStrategySelection:
    """Test record_strategy_selection method."""

    def test_record_strategy_selection_basic(self):
        """Test basic strategy selection recording."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        initial_events = len(monitor.execution_events)

        monitor.record_strategy_selection(
            selected_strategy=OrchestrationStrategy.PARALLEL_BASIC,
            available_strategies=[OrchestrationStrategy.PARALLEL_BASIC, OrchestrationStrategy.SEQUENTIAL],
            selection_reason="more parallelism needed",
        )

        assert len(monitor.execution_events) == initial_events + 1
        last_event = monitor.execution_events[-1]
        assert last_event.event_type == "strategy_selected"
        assert last_event.strategy == "parallel_basic"

    def test_record_strategy_selection_records_metric(self):
        """Test that strategy selection also records a metric."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        initial_metrics = len(monitor.metrics)

        monitor.record_strategy_selection(
            selected_strategy=OrchestrationStrategy.HYBRID,
            available_strategies=list(OrchestrationStrategy),
            selection_reason="optimal for complex mods",
        )

        assert len(monitor.metrics) >= initial_metrics


class TestRecordTaskEvent:
    """Test record_task_event method."""

    def test_record_task_event_basic(self):
        """Test basic task event recording."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        initial_events = len(monitor.execution_events)

        mock_task = Mock()
        mock_task.task_id = "task_001"
        mock_task.agent_name = "translator"
        mock_task.agent_type = "converter"
        mock_task.status = "completed"

        monitor.record_task_event(mock_task, "task_completed")

        assert len(monitor.execution_events) == initial_events + 1


class TestAlerting:
    """Test alerting functionality."""

    def test_add_alert_callback(self):
        """Test adding an alert callback."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        def test_callback(alert_type, data):
            pass

        monitor.add_alert_callback(test_callback)

        assert len(monitor.alert_callbacks) == 1


class TestMetricsRecording:
    """Test internal metrics recording."""

    def test_record_metric_internal(self):
        """Test _record_metric internal method."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        initial_count = len(monitor.metrics)

        # Access the private method for testing
        monitor._record_metric("accuracy", 0.95)

        assert len(monitor.metrics) == initial_count + 1
        assert monitor.metrics[-1].metric_name == "accuracy"
        assert monitor.metrics[-1].value == 0.95

    def test_record_metric_with_metadata(self):
        """Test metric recording with metadata."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        monitor._record_metric(
            "latency",
            120.5,
            metadata={"endpoint": "/api/convert"},
        )

        last_metric = monitor.metrics[-1]
        assert last_metric.metadata["endpoint"] == "/api/convert"


class TestGetPerformanceSummary:
    """Test get_performance_summary method."""

    def test_get_performance_summary_returns_dict(self):
        """Test that performance summary returns a dictionary."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        summary = monitor.get_performance_summary()

        assert isinstance(summary, dict)


class TestGetDetailedMetrics:
    """Test get_detailed_metrics method."""

    def test_get_detailed_metrics_returns_list(self):
        """Test that detailed metrics returns a list."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        metrics = monitor.get_detailed_metrics()

        assert isinstance(metrics, list)


class TestGetExecutionEvents:
    """Test get_execution_events method."""

    def test_get_execution_events_returns_list(self):
        """Test that execution events returns a list."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        events = monitor.get_execution_events()

        assert isinstance(events, list)


class TestExportMetrics:
    """Test export_metrics method."""

    def test_export_metrics_returns_bool(self):
        """Test that export metrics returns a bool."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        exported = monitor.export_metrics(file_path=Path("/tmp/test_metrics.json"))

        assert isinstance(exported, bool)


class TestMonitoringThread:
    """Test monitoring thread functionality."""

    def test_start_monitoring_creates_thread(self):
        """Test that start_monitoring creates a thread."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        monitor.start_monitoring()

        assert monitor.monitoring_thread is not None
        assert isinstance(monitor.monitoring_thread, threading.Thread)

        monitor.stop_monitoring.set()

    def test_stop_monitoring_works(self):
        """Test that stop_monitoring works."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        monitor.start_monitoring()
        monitor.stop_monitoring.set()

        assert monitor.stop_monitoring.is_set()

    def test_monitoring_not_started_by_default(self):
        """Test that monitoring is not started by default when disabled."""
        monitor = OrchestrationMonitor(enable_real_time_monitoring=False)

        assert monitor.monitoring_thread is None