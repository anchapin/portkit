"""
Orchestration monitoring: real-time metrics, alerting, and performance analysis.

Extracted from ``orchestration/monitoring.py`` as part of issue #1767.
Part of Phase 5: Monitoring, Error Handling, and Evaluation.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..strategy_selector import OrchestrationStrategy
from ..task_graph import TaskNode
from .models import ExecutionEvent, PerformanceMetric

logger = logging.getLogger(__name__)


class OrchestrationMonitor:
    """
    Monitors orchestration execution and collects performance metrics.
    Provides real-time monitoring, error detection, and performance analysis.
    """

    def __init__(
        self,
        enable_real_time_monitoring: bool = True,
        metrics_retention_hours: int = 24,
        alert_thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize the orchestration monitor

        Args:
            enable_real_time_monitoring: Enable real-time monitoring and alerting
            metrics_retention_hours: How long to retain metrics data
            alert_thresholds: Thresholds for triggering alerts
        """
        self.enable_real_time_monitoring = enable_real_time_monitoring
        self.metrics_retention_hours = metrics_retention_hours

        # Default alert thresholds
        self.alert_thresholds = alert_thresholds or {
            "task_failure_rate": 0.2,  # Alert if >20% of tasks fail
            "avg_task_duration": 600.0,  # Alert if avg task duration >10 minutes
            "queue_depth": 50,  # Alert if task queue depth >50
            "worker_utilization": 0.9,  # Alert if worker utilization >90%
        }

        # Data storage
        self.metrics: List[PerformanceMetric] = []
        self.execution_events: List[ExecutionEvent] = []
        self.active_executions: Dict[str, Dict[str, Any]] = {}

        # Real-time monitoring
        self.monitoring_thread: Optional[threading.Thread] = None
        self.stop_monitoring = threading.Event()
        self.alert_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []

        # Performance aggregates
        self.performance_cache: Dict[str, Any] = {}
        self.cache_expiry = 0

        if self.enable_real_time_monitoring:
            self.start_monitoring()

    def start_monitoring(self):
        """Start the real-time monitoring thread"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.warning("Monitoring thread already running")
            return

        self.stop_monitoring.clear()
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("Orchestration monitoring started")

    def stop_monitoring(self):
        """Stop the real-time monitoring thread"""
        if self.monitoring_thread:
            self.stop_monitoring.set()
            self.monitoring_thread.join(timeout=5.0)
            logger.info("Orchestration monitoring stopped")

    def record_execution_start(
        self,
        execution_id: str,
        strategy: OrchestrationStrategy,
        task_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record the start of an orchestration execution"""

        execution_data = {
            "execution_id": execution_id,
            "strategy": strategy.value,
            "task_count": task_count,
            "start_time": time.time(),
            "metadata": metadata or {},
        }

        self.active_executions[execution_id] = execution_data

        # Record event
        event = ExecutionEvent(
            event_type="execution_started",
            strategy=strategy.value,
            details={
                "execution_id": execution_id,
                "task_count": task_count,
                **execution_data["metadata"],
            },
        )
        self.execution_events.append(event)

        logger.info(
            f"Started monitoring execution {execution_id} with {task_count} tasks using {strategy.value}"
        )

    def record_execution_end(self, execution_id: str, success: bool, final_results: Dict[str, Any]):
        """Record the end of an orchestration execution"""

        if execution_id not in self.active_executions:
            logger.warning(f"Execution {execution_id} not found in active executions")
            return

        execution_data = self.active_executions[execution_id]
        end_time = time.time()
        duration = end_time - execution_data["start_time"]

        # Calculate performance metrics
        success_rate = final_results.get("overall_success_rate", 0.0)
        completed_tasks = (
            final_results.get("detailed_report", {})
            .get("parallel_execution_stats", {})
            .get("completed_tasks", 0)
        )
        failed_tasks = (
            final_results.get("detailed_report", {})
            .get("parallel_execution_stats", {})
            .get("failed_tasks", 0)
        )

        # Record metrics
        self._record_metric(
            "execution_duration",
            duration,
            {
                "execution_id": execution_id,
                "strategy": execution_data["strategy"],
                "success": success,
            },
        )

        self._record_metric(
            "execution_success_rate",
            success_rate,
            {"execution_id": execution_id, "strategy": execution_data["strategy"]},
        )

        self._record_metric(
            "tasks_completed",
            completed_tasks,
            {"execution_id": execution_id, "strategy": execution_data["strategy"]},
        )

        self._record_metric(
            "tasks_failed",
            failed_tasks,
            {"execution_id": execution_id, "strategy": execution_data["strategy"]},
        )

        # Record event
        event = ExecutionEvent(
            event_type="execution_ended",
            strategy=execution_data["strategy"],
            details={
                "execution_id": execution_id,
                "success": success,
                "duration": duration,
                "success_rate": success_rate,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
            },
        )
        self.execution_events.append(event)

        # Remove from active executions
        del self.active_executions[execution_id]

        logger.info(
            f"Completed monitoring execution {execution_id}: "
            f"success={success}, duration={duration:.2f}s, success_rate={success_rate:.2%}"
        )

    def record_task_event(
        self, task: TaskNode, event_type: str, additional_details: Optional[Dict[str, Any]] = None
    ):
        """Record a task-level event"""

        details = {
            "task_id": task.task_id,
            "agent_name": task.agent_name,
            "agent_type": task.agent_type,
            "priority": task.priority,
            "retry_count": task.retry_count,
            **(additional_details or {}),
        }

        if task.duration:
            details["duration"] = task.duration

        if task.error:
            details["error"] = task.error

        event = ExecutionEvent(
            event_type=event_type, task_id=task.task_id, agent_name=task.agent_name, details=details
        )

        self.execution_events.append(event)

        # Record specific metrics based on event type
        if event_type == "task_completed" and task.duration:
            self._record_metric(
                "task_duration",
                task.duration,
                {
                    "agent_name": task.agent_name,
                    "agent_type": task.agent_type,
                    "priority": task.priority,
                },
            )

        elif event_type == "task_failed":
            self._record_metric(
                "task_failure",
                1.0,
                {
                    "agent_name": task.agent_name,
                    "agent_type": task.agent_type,
                    "error": task.error,
                    "retry_count": task.retry_count,
                },
            )

    def record_strategy_selection(
        self,
        selected_strategy: OrchestrationStrategy,
        available_strategies: List[OrchestrationStrategy],
        selection_reason: str,
        selection_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record strategy selection event"""

        event = ExecutionEvent(
            event_type="strategy_selected",
            strategy=selected_strategy.value,
            details={
                "available_strategies": [s.value for s in available_strategies],
                "selection_reason": selection_reason,
                "metadata": selection_metadata or {},
            },
        )

        self.execution_events.append(event)

        # Record metric
        self._record_metric(
            "strategy_selection",
            1.0,
            {"strategy": selected_strategy.value, "reason": selection_reason},
        )

        logger.info(f"Strategy selected: {selected_strategy.value} ({selection_reason})")

    def _record_metric(
        self, metric_name: str, value: float, metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a performance metric"""

        metric = PerformanceMetric(metric_name=metric_name, value=value, metadata=metadata or {})

        self.metrics.append(metric)

        # Clean up old metrics
        self._cleanup_old_data()

        # Invalidate cache
        self.performance_cache.clear()
        self.cache_expiry = 0

    def _monitoring_loop(self):
        """Main monitoring loop that runs in background thread"""

        logger.debug("Monitoring loop started")

        while not self.stop_monitoring.wait(timeout=30.0):  # Check every 30 seconds
            try:
                self._check_alerts()
                self._cleanup_old_data()

                # Log periodic status
                if self.active_executions:
                    logger.debug(f"Active executions: {len(self.active_executions)}")

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

        logger.debug("Monitoring loop stopped")

    def _check_alerts(self):
        """Check for alert conditions and trigger callbacks if needed"""

        current_time = time.time()
        recent_window = current_time - 300  # Last 5 minutes

        # Get recent metrics
        recent_metrics = [m for m in self.metrics if m.timestamp >= recent_window]

        if not recent_metrics:
            return

        # Check task failure rate
        failure_metrics = [m for m in recent_metrics if m.metric_name == "task_failure"]
        completion_metrics = [m for m in recent_metrics if m.metric_name == "task_duration"]

        if completion_metrics:
            total_tasks = len(completion_metrics) + len(failure_metrics)
            failure_rate = len(failure_metrics) / total_tasks if total_tasks > 0 else 0

            if failure_rate > self.alert_thresholds.get("task_failure_rate", 1.0):
                self._trigger_alert(
                    "high_task_failure_rate",
                    {
                        "failure_rate": failure_rate,
                        "failed_tasks": len(failure_metrics),
                        "total_tasks": total_tasks,
                        "window_minutes": 5,
                    },
                )

        # Check average task duration
        if completion_metrics:
            durations = [m.value for m in completion_metrics]
            avg_duration = sum(durations) / len(durations)

            if avg_duration > self.alert_thresholds.get("avg_task_duration", float("inf")):
                self._trigger_alert(
                    "high_avg_task_duration",
                    {
                        "avg_duration": avg_duration,
                        "max_duration": max(durations),
                        "task_count": len(durations),
                        "window_minutes": 5,
                    },
                )

    def _trigger_alert(self, alert_type: str, alert_data: Dict[str, Any]):
        """Trigger an alert by calling registered callbacks"""

        logger.warning(f"ALERT: {alert_type} - {alert_data}")

        for callback in self.alert_callbacks:
            try:
                callback(alert_type, alert_data)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")

    def add_alert_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Add a callback function for handling alerts"""
        self.alert_callbacks.append(callback)

    def _cleanup_old_data(self):
        """Clean up old metrics and events based on retention policy"""

        cutoff_time = time.time() - (self.metrics_retention_hours * 3600)

        # Clean up metrics
        original_count = len(self.metrics)
        self.metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]

        # Clean up events
        self.execution_events = [e for e in self.execution_events if e.timestamp >= cutoff_time]

        if len(self.metrics) < original_count:
            logger.debug(f"Cleaned up {original_count - len(self.metrics)} old metrics")

    def get_performance_summary(self, time_window_hours: Optional[float] = None) -> Dict[str, Any]:
        """Get performance summary for the specified time window"""

        # Check cache
        cache_key = f"summary_{time_window_hours or 'all'}"
        if cache_key in self.performance_cache and time.time() < self.cache_expiry:
            return self.performance_cache[cache_key]

        # Calculate time window
        if time_window_hours:
            cutoff_time = time.time() - (time_window_hours * 3600)
            metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]
            events = [e for e in self.execution_events if e.timestamp >= cutoff_time]
        else:
            metrics = self.metrics
            events = self.execution_events

        if not metrics and not events:
            return {}

        # Group metrics by type
        metrics_by_type = {}
        for metric in metrics:
            if metric.metric_name not in metrics_by_type:
                metrics_by_type[metric.metric_name] = []
            metrics_by_type[metric.metric_name].append(metric)

        # Calculate summary statistics
        summary = {
            "time_window_hours": time_window_hours,
            "total_metrics": len(metrics),
            "total_events": len(events),
            "active_executions": len(self.active_executions),
        }

        # Execution statistics
        execution_events = [
            e for e in events if e.event_type in ["execution_started", "execution_ended"]
        ]
        if execution_events:
            completed_executions = [
                e for e in execution_events if e.event_type == "execution_ended"
            ]

            summary["executions"] = {
                "total_started": len(
                    [e for e in execution_events if e.event_type == "execution_started"]
                ),
                "total_completed": len(completed_executions),
                "avg_success_rate": sum(
                    e.details.get("success_rate", 0) for e in completed_executions
                )
                / len(completed_executions)
                if completed_executions
                else 0,
                "avg_duration": sum(e.details.get("duration", 0) for e in completed_executions)
                / len(completed_executions)
                if completed_executions
                else 0,
            }

        # Task statistics
        if "task_duration" in metrics_by_type:
            durations = [m.value for m in metrics_by_type["task_duration"]]
            summary["tasks"] = {
                "total_completed": len(durations),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
            }

        if "task_failure" in metrics_by_type:
            failures = metrics_by_type["task_failure"]
            summary["failures"] = {
                "total_failures": len(failures),
                "failure_rate": len(failures)
                / (summary.get("tasks", {}).get("total_completed", 0) + len(failures))
                if summary.get("tasks")
                else 0,
            }

        # Strategy usage
        strategy_events = [e for e in events if e.event_type == "strategy_selected"]
        if strategy_events:
            strategy_counts = {}
            for event in strategy_events:
                strategy = event.strategy
                if strategy not in strategy_counts:
                    strategy_counts[strategy] = 0
                strategy_counts[strategy] += 1

            summary["strategies"] = {
                "usage_counts": strategy_counts,
                "most_used": max(strategy_counts.keys(), key=lambda k: strategy_counts[k])
                if strategy_counts
                else None,
            }

        # Cache result
        self.performance_cache[cache_key] = summary
        self.cache_expiry = time.time() + 300  # Cache for 5 minutes

        return summary

    def get_detailed_metrics(
        self, metric_name: Optional[str] = None, time_window_hours: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Get detailed metrics data"""

        # Filter by time window
        if time_window_hours:
            cutoff_time = time.time() - (time_window_hours * 3600)
            metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]
        else:
            metrics = self.metrics

        # Filter by metric name
        if metric_name:
            metrics = [m for m in metrics if m.metric_name == metric_name]

        return [m.to_dict() for m in metrics]

    def get_execution_events(
        self, event_type: Optional[str] = None, time_window_hours: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Get execution events"""

        # Filter by time window
        if time_window_hours:
            cutoff_time = time.time() - (time_window_hours * 3600)
            events = [e for e in self.execution_events if e.timestamp >= cutoff_time]
        else:
            events = self.execution_events

        # Filter by event type
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return [e.to_dict() for e in events]

    def export_metrics(self, file_path: Path, format: str = "json") -> bool:
        """Export metrics to file"""

        try:
            data = {
                "export_timestamp": time.time(),
                "metrics": [m.to_dict() for m in self.metrics],
                "events": [e.to_dict() for e in self.execution_events],
                "performance_summary": self.get_performance_summary(),
            }

            if format.lower() == "json":
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
            else:
                raise ValueError(f"Unsupported export format: {format}")

            logger.info(f"Exported metrics to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return False

    def __enter__(self):
        """Context manager entry"""
        if not self.enable_real_time_monitoring:
            self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_monitoring()
