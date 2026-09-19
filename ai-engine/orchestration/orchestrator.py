"""
Backwards-compatibility shim.

The contents of this module have been split into the ``core`` subpackage
per issue #1767:

- :mod:`orchestration.core.orchestrator` — dispatcher + lifecycle management
- :mod:`orchestration.core.workflows`    — workflow construction
- :mod:`orchestration.core.execution`    — workflow execution loops

This shim re-exports the previous public API so existing imports of the form
``from orchestration.orchestrator import ParallelOrchestrator`` keep working.
Prefer importing from :mod:`orchestration.core` in new code.
"""

from .core.orchestrator import ParallelOrchestrator

__all__ = [
    "ParallelOrchestrator",
]
