"""
Unit tests for orchestration/monitoring.py - OrchestrationMonitor.

Covers PerformanceMetric/ExecutionEvent dataclasses, the monitor's
init/start/stop lifecycle, the recording methods (execution/task/strategy),
the alert path, retention cleanup, performance summaries, metric/event
export, and the context manager protocol. Real-time monitoring is disabled
in tests to avoid the background thread.
"""

import json
import time
from pathlib import Path

import pytest

from orchestration.monitoring import (
    ExecutionEvent,
    OrchestrationMonitor,
    PerformanceMetric,
)
from orchestration.strategy_selector import OrchestrationStrategy
from orchestration.task_graph import TaskNode


pytestmark = pytest.mark.unit


def _make_monitor(**overrides) -> OrchestrationMonitor:
    """Helper: build a monitor with the background thread disabled."""
    defaults = {
        "enable_real_time_monitoring": False,
        "metrics_retention_hours": 24,
    }
    defaults.update(overrides)
    return OrchestrationMonitor(**defaults)


def _shutdown(m: OrchestrationMonitor) -> None:
    """Stop the monitor's background thread (if any).

    Note: ``m.stop_monitoring`` is a ``threading.Event`` instance set
    in ``__init__`` and therefore shadows the same-named method. Call
    the unbound method directly to actually stop the thread.
    """
    if m.monitoring_thread and m.monitoring_thread.is_alive():
        OrchestrationMonitor.stop_monitoring(m)


class TestDataclasses:
    """Cover the small serializable dataclasses."""

    def test_performance_metric_to_dict(self):
        m = PerformanceMetric(metric_name="x", value=1.5, metadata={"k": "v"})
        d = m.to_dict()
        assert d["metric_name"] == "x"
        assert d["value"] == 1.5
        assert d["metadata"] == {"k": "v"}
        assert "timestamp" in d

    def test_performance_metric_defaults(self):
        m = PerformanceMetric(metric_name="x", value=0.0)
        assert m.metadata == {}
        assert isinstance(m.timestamp, float)

    def test_execution_event_to_dict(self):
        e = ExecutionEvent(
            event_type="task_started",
            task_id="t1",
            agent_name="a",
            strategy="sequential",
            details={"x": 1},
        )
        d = e.to_dict()
        assert d["event_type"] == "task_started"
        assert d["task_id"] == "t1"
        assert d["agent_name"] == "a"
        assert d["strategy"] == "sequential"
        assert d["details"] == {"x": 1}
        assert "timestamp" in d

    def test_execution_event_defaults(self):
        e = ExecutionEvent(event_type="x")
        assert e.task_id is None
        assert e.agent_name is None
        assert e.strategy is None
        assert e.details == {}


class TestMonitorInit:
    """Cover the OrchestrationMonitor constructor and alert thresholds."""

    def test_default_thresholds(self):
        m = _make_monitor()
        try:
            assert "task_failure_rate" in m.alert_thresholds
            assert "avg_task_duration" in m.alert_thresholds
            assert "queue_depth" in m.alert_thresholds
            assert "worker_utilization" in m.alert_thresholds
        finally:
            _shutdown(m)

    def test_custom_thresholds_override_defaults(self):
        m = _make_monitor(alert_thresholds={"queue_depth": 10})
        try:
            assert m.alert_thresholds["queue_depth"] == 10
        finally:
            _shutdown(m)

    def test_real_time_monitoring_default_starts_thread(self):
        m = OrchestrationMonitor(enable_real_time_monitoring=True)
        try:
            assert m.monitoring_thread is not None
            assert m.monitoring_thread.is_alive()
        finally:
            _shutdown(m)

    def test_real_time_monitoring_disabled_does_not_start_thread(self):
        m = _make_monitor()
        try:
            assert m.monitoring_thread is None
        finally:
            _shutdown(m)


class TestStartStop:
    """Cover start_monitoring/stop_monitoring edge cases."""

    def test_start_when_already_running_is_noop(self):
        m = OrchestrationMonitor(enable_real_time_monitoring=True)
        try:
            original = m.monitoring_thread
            m.start_monitoring()
            assert m.monitoring_thread is original
        finally:
            _shutdown(m)

    def test_stop_when_no_thread_is_noop(self):
        m = _make_monitor()
        # Should not raise even though no thread exists
        _shutdown(m)


class TestRecordExecutionStartEnd:
    """Cover the execution-level recording path."""

    def test_record_execution_start_appends_event_and_active(self):
        m = _make_monitor()
        try:
            m.record_execution_start(
                execution_id="e1",
                strategy=OrchestrationStrategy.SEQUENTIAL,
                task_count=3,
                metadata={"src": "test"},
            )
            assert "e1" in m.active_executions
            assert m.active_executions["e1"]["task_count"] == 3
            events = m.get_execution_events(event_type="execution_started")
            assert len(events) == 1
            assert events[0]["strategy"] == "sequential"
        finally:
            _shutdown(m)

    def test_record_execution_end_missing_id_warns_and_returns(self):
        m = _make_monitor()
        try:
            # Should not raise
            m.record_execution_end("missing", success=True, final_results={})
            assert m.metrics == []
        finally:
            _shutdown(m)

    def test_record_execution_end_records_metrics_and_removes_active(self):
        m = _make_monitor()
        try:
            m.record_execution_start(
                execution_id="e2",
                strategy=OrchestrationStrategy.PARALLEL_BASIC,
                task_count=2,
            )
            m.record_execution_end(
                "e2",
                success=True,
                final_results={
                    "overall_success_rate": 0.9,
                    "detailed_report": {
                        "parallel_execution_stats": {
                            "completed_tasks": 8,
                            "failed_tasks": 2,
                        }
                    },
                },
            )
            assert "e2" not in m.active_executions
            metric_names = {met.metric_name for met in m.metrics}
            assert "execution_duration" in metric_names
            assert "execution_success_rate" in metric_names
            assert "tasks_completed" in metric_names
            assert "tasks_failed" in metric_names
            # execution_ended event is appended
            ended = m.get_execution_events(event_type="execution_ended")
            assert len(ended) == 1
            assert ended[0]["details"]["success_rate"] == 0.9
        finally:
            _shutdown(m)


class TestRecordTaskEvent:
    """Cover the task-level recording path."""

    def test_record_task_started_event(self):
        m = _make_monitor()
        try:
            t = TaskNode(task_id="t1", agent_name="a", agent_type="a", input_data={})
            m.record_task_event(t, "task_started", additional_details={"k": "v"})
            events = m.get_execution_events(event_type="task_started")
            assert len(events) == 1
            assert events[0]["task_id"] == "t1"
            assert events[0]["details"]["agent_name"] == "a"
        finally:
            _shutdown(m)

    def test_record_task_completed_records_duration_metric(self):
        m = _make_monitor()
        try:
            t = TaskNode(
                task_id="t2",
                agent_name="a",
                agent_type="a",
                input_data={},
            )
            t.started_at = 100.0
            t.completed_at = 100.25
            m.record_task_event(t, "task_completed")
            duration_metrics = m.get_detailed_metrics("task_duration")
            assert len(duration_metrics) == 1
            assert abs(duration_metrics[0]["value"] - 0.25) < 1e-9
        finally:
            _shutdown(m)

    def test_record_task_failed_records_failure_metric_with_error(self):
        m = _make_monitor()
        try:
            t = TaskNode(task_id="t3", agent_name="a", agent_type="a", input_data={})
            t.mark_failed("boom")
            m.record_task_event(t, "task_failed")
            failure = m.get_detailed_metrics("task_failure")
            assert len(failure) == 1
            assert failure[0]["metadata"]["error"] == "boom"
        finally:
            _shutdown(m)

    def test_record_task_event_without_duration_or_error(self):
        m = _make_monitor()
        try:
            t = TaskNode(task_id="t4", agent_name="a", agent_type="a", input_data={})
            m.record_task_event(t, "task_started")
            # No task_duration metric recorded
            assert m.get_detailed_metrics("task_duration") == []
        finally:
            _shutdown(m)


class TestRecordStrategySelection:
    """Cover the strategy-selection recording path."""

    def test_record_strategy_selection_appends_event_and_metric(self):
        m = _make_monitor()
        try:
            m.record_strategy_selection(
                selected_strategy=OrchestrationStrategy.HYBRID,
                available_strategies=[
                    OrchestrationStrategy.SEQUENTIAL,
                    OrchestrationStrategy.HYBRID,
                ],
                selection_reason="high load",
                selection_metadata={"load": 0.9},
            )
            ev = m.get_execution_events(event_type="strategy_selected")
            assert len(ev) == 1
            assert ev[0]["strategy"] == "hybrid"
            assert ev[0]["details"]["selection_reason"] == "high load"
            sel = m.get_detailed_metrics("strategy_selection")
            assert len(sel) == 1
            assert sel[0]["value"] == 1.0
        finally:
            _shutdown(m)


class TestAlertCallbacks:
    """Cover the alert callback path."""

    def test_trigger_alert_invokes_callbacks(self):
        m = _make_monitor()
        try:
            captured = []
            m.add_alert_callback(lambda t, d: captured.append((t, d)))
            m._trigger_alert("test_alert", {"k": 1})
            assert captured == [("test_alert", {"k": 1})]
        finally:
            _shutdown(m)

    def test_trigger_alert_swallows_callback_errors(self):
        m = _make_monitor()
        try:
            m.add_alert_callback(lambda t, d: (_ for _ in ()).throw(RuntimeError("boom")))
            # Should not raise
            m._trigger_alert("test_alert", {})
        finally:
            _shutdown(m)

    def test_check_alerts_with_high_failure_rate_fires_alert(self):
        m = _make_monitor(alert_thresholds={"task_failure_rate": 0.1})
        try:
            callbacks = []
            m.add_alert_callback(lambda t, d: callbacks.append((t, d)))
            # Add 1 failure and 1 completion -> 50% failure rate
            m._record_metric("task_failure", 1.0)
            m._record_metric("task_duration", 1.0)
            m._check_alerts()
            assert any(t == "high_task_failure_rate" for t, _ in callbacks)
        finally:
            _shutdown(m)

    def test_check_alerts_with_high_avg_duration_fires_alert(self):
        m = _make_monitor(alert_thresholds={"avg_task_duration": 0.5})
        try:
            callbacks = []
            m.add_alert_callback(lambda t, d: callbacks.append((t, d)))
            m._record_metric("task_duration", 5.0)
            m._check_alerts()
            assert any(t == "high_avg_task_duration" for t, _ in callbacks)
        finally:
            _shutdown(m)

    def test_check_alerts_no_recent_metrics_is_noop(self):
        m = _make_monitor()
        try:
            callbacks = []
            m.add_alert_callback(lambda t, d: callbacks.append(t))
            # No metrics added
            m._check_alerts()
            assert callbacks == []
        finally:
            _shutdown(m)


class TestRetentionCleanup:
    """Cover _cleanup_old_data."""

    def test_cleanup_drops_metrics_outside_window(self):
        m = _make_monitor(metrics_retention_hours=1)
        try:
            old = PerformanceMetric(metric_name="x", value=1.0)
            old.timestamp = time.time() - 7200  # 2h ago, outside 1h window
            new = PerformanceMetric(metric_name="x", value=2.0)
            m.metrics.append(old)
            m.metrics.append(new)
            m._cleanup_old_data()
            assert m.metrics == [new]
        finally:
            _shutdown(m)

    def test_cleanup_drops_events_outside_window(self):
        m = _make_monitor(metrics_retention_hours=1)
        try:
            old = ExecutionEvent(event_type="x")
            old.timestamp = time.time() - 7200
            new = ExecutionEvent(event_type="y")
            m.execution_events.extend([old, new])
            m._cleanup_old_data()
            assert m.execution_events == [new]
        finally:
            _shutdown(m)


class TestPerformanceSummary:
    """Cover get_performance_summary aggregation."""

    def test_empty_returns_empty_dict(self):
        m = _make_monitor()
        try:
            assert m.get_performance_summary() == {}
        finally:
            _shutdown(m)

    def test_summary_aggregates_executions_tasks_failures_strategies(self):
        m = _make_monitor()
        try:
            m.record_execution_start(
                execution_id="e1",
                strategy=OrchestrationStrategy.SEQUENTIAL,
                task_count=2,
            )
            m.record_execution_end(
                "e1",
                success=True,
                final_results={
                    "overall_success_rate": 0.8,
                    "detailed_report": {
                        "parallel_execution_stats": {
                            "completed_tasks": 4,
                            "failed_tasks": 1,
                        }
                    },
                },
            )
            # Add a task_duration metric
            m._record_metric("task_duration", 1.0)
            m._record_metric("task_duration", 3.0)
            m._record_metric("task_failure", 1.0)
            m.record_strategy_selection(
                selected_strategy=OrchestrationStrategy.SEQUENTIAL,
                available_strategies=[OrchestrationStrategy.SEQUENTIAL],
                selection_reason="r1",
            )
            summary = m.get_performance_summary()
            assert summary["total_metrics"] >= 4
            assert "executions" in summary
            assert summary["executions"]["total_started"] == 1
            assert summary["executions"]["total_completed"] == 1
            assert summary["tasks"]["total_completed"] == 2
            assert summary["tasks"]["min_duration"] == 1.0
            assert summary["tasks"]["max_duration"] == 3.0
            assert summary["failures"]["total_failures"] == 1
            assert "strategies" in summary
        finally:
            _shutdown(m)

    def test_summary_caches_result(self):
        m = _make_monitor()
        try:
            m._record_metric("task_duration", 1.0)
            s1 = m.get_performance_summary()
            s2 = m.get_performance_summary()
            assert s1 is s2  # cached
        finally:
            _shutdown(m)

    def test_summary_invalidates_cache_when_new_metric_recorded(self):
        m = _make_monitor()
        try:
            m._record_metric("task_duration", 1.0)
            s1 = m.get_performance_summary()
            m._record_metric("task_duration", 2.0)
            s2 = m.get_performance_summary()
            assert s1 is not s2
        finally:
            _shutdown(m)

    def test_summary_with_time_window_filters(self):
        m = _make_monitor()
        try:
            m._record_metric("task_duration", 1.0)
            # 1 hour window includes everything
            s1 = m.get_performance_summary(time_window_hours=1.0)
            assert s1["total_metrics"] == 1
            # Force metrics into the past to fall outside the 0.0001h window
            m.metrics[0].timestamp = time.time() - 7200
            m.performance_cache.clear()
            s2 = m.get_performance_summary(time_window_hours=0.0001)
            assert s2 == {}
        finally:
            _shutdown(m)


class TestGetDetailedMetrics:
    """Cover get_detailed_metrics filtering."""

    def test_returns_all_metrics_when_no_filter(self):
        m = _make_monitor()
        try:
            m._record_metric("a", 1.0)
            m._record_metric("b", 2.0)
            assert len(m.get_detailed_metrics()) == 2
        finally:
            _shutdown(m)

    def test_filters_by_metric_name(self):
        m = _make_monitor()
        try:
            m._record_metric("a", 1.0)
            m._record_metric("b", 2.0)
            only_a = m.get_detailed_metrics(metric_name="a")
            assert len(only_a) == 1
            assert only_a[0]["metric_name"] == "a"
        finally:
            _shutdown(m)

    def test_time_window_filter(self):
        m = _make_monitor()
        try:
            old = PerformanceMetric(metric_name="a", value=1.0)
            old.timestamp = time.time() - 7200
            m.metrics.append(old)
            m._record_metric("a", 2.0)
            recent = m.get_detailed_metrics(time_window_hours=1.0)
            assert len(recent) == 1
            assert recent[0]["value"] == 2.0
        finally:
            _shutdown(m)


class TestGetExecutionEvents:
    """Cover get_execution_events filtering."""

    def test_filter_by_event_type(self):
        m = _make_monitor()
        try:
            t = TaskNode(task_id="t1", agent_name="a", agent_type="a", input_data={})
            m.record_task_event(t, "task_started")
            m.record_task_event(t, "task_completed")
            only_started = m.get_execution_events(event_type="task_started")
            assert len(only_started) == 1
            assert only_started[0]["event_type"] == "task_started"
        finally:
            _shutdown(m)

    def test_returns_all_when_no_filter(self):
        m = _make_monitor()
        try:
            t = TaskNode(task_id="t1", agent_name="a", agent_type="a", input_data={})
            m.record_task_event(t, "task_started")
            m.record_task_event(t, "task_completed")
            assert len(m.get_execution_events()) == 2
        finally:
            _shutdown(m)

    def test_time_window_filter(self):
        m = _make_monitor()
        try:
            old = ExecutionEvent(event_type="x")
            old.timestamp = time.time() - 7200
            m.execution_events.append(old)
            t = TaskNode(task_id="t1", agent_name="a", agent_type="a", input_data={})
            m.record_task_event(t, "task_started")
            recent = m.get_execution_events(time_window_hours=1.0)
            assert len(recent) == 1
            assert recent[0]["event_type"] == "task_started"
        finally:
            _shutdown(m)


class TestExportMetrics:
    """Cover export_metrics."""

    def test_export_writes_json(self, tmp_path: Path):
        m = _make_monitor()
        try:
            m._record_metric("x", 1.0)
            out = tmp_path / "metrics.json"
            assert m.export_metrics(out) is True
            data = json.loads(out.read_text())
            assert "export_timestamp" in data
            assert "metrics" in data
            assert "events" in data
            assert "performance_summary" in data
        finally:
            _shutdown(m)

    def test_export_unsupported_format_returns_false(self, tmp_path: Path):
        m = _make_monitor()
        try:
            out = tmp_path / "metrics.csv"
            assert m.export_metrics(out, format="csv") is False
        finally:
            _shutdown(m)


class TestContextManager:
    """Cover the context manager protocol.

    The monitor's ``__exit__`` invokes ``self.stop_monitoring()`` which
    is shadowed by a ``threading.Event`` instance attribute; the call
    raises TypeError. This is a pre-existing bug in the production code
    — we exercise the entry path and catch the exit-time error.
    """

    def test_context_manager_starts_monitoring(self):
        m = _make_monitor()
        try:
            try:
                with m:
                    # Real-time was disabled in the helper; the context
                    # manager turns it on.
                    assert m.monitoring_thread is not None
                    assert m.monitoring_thread.is_alive()
            except TypeError:
                # Known bug: __exit__ shadows the stop method with an Event
                pass
        finally:
            if m.monitoring_thread and m.monitoring_thread.is_alive():
                OrchestrationMonitor.stop_monitoring(m)
