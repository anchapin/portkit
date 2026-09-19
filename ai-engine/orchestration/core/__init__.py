"""
Core orchestration subpackage: dispatcher and lifecycle management.

Split out of ``orchestration/orchestrator.py`` as part of issue #1767:

- :mod:`orchestration.core.orchestrator` — ``ParallelOrchestrator``
- :mod:`orchestration.core.workflows`    — workflow construction mixin
- :mod:`orchestration.core.execution`    — workflow execution mixin
"""

from .execution import WorkflowExecutorMixin
from .orchestrator import ParallelOrchestrator
from .workflows import WorkflowBuilderMixin

__all__ = [
    "ParallelOrchestrator",
    "WorkflowBuilderMixin",
    "WorkflowExecutorMixin",
]
