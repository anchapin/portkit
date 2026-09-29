"""
Backwards-compatibility shim.

The contents of this module have been split into the ``telemetry`` subpackage
per issue #1767:

- :mod:`orchestration.telemetry.models`  — ``PerformanceMetric``, ``ExecutionEvent``
- :mod:`orchestration.telemetry.monitor` — ``OrchestrationMonitor``

This shim re-exports the previous public API so existing imports of the form
``from orchestration.monitoring import OrchestrationMonitor`` keep working.
Prefer importing from :mod:`orchestration.telemetry` in new code.
"""

from .telemetry import ExecutionEvent, OrchestrationMonitor, PerformanceMetric

__all__ = [
    "ExecutionEvent",
    "OrchestrationMonitor",
    "PerformanceMetric",
]
