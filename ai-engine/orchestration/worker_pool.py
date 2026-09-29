"""
Backwards-compatibility shim.

The contents of this module have been split into the ``pool`` subpackage
per issue #1767:

- :mod:`orchestration.pool.models`      — ``WorkerType``, ``WorkerStats``
- :mod:`orchestration.pool.worker_pool` — ``WorkerPool``
- :mod:`orchestration.pool.executor`    — ``create_agent_executor``, ``setup_signal_handlers``

This shim re-exports the previous public API so existing imports of the form
``from orchestration.worker_pool import WorkerPool`` keep working.
Prefer importing from :mod:`orchestration.pool` in new code.
"""

from .pool import (
    WorkerPool,
    WorkerStats,
    WorkerType,
    create_agent_executor,
    setup_signal_handlers,
)

__all__ = [
    "WorkerPool",
    "WorkerStats",
    "WorkerType",
    "create_agent_executor",
    "setup_signal_handlers",
]
