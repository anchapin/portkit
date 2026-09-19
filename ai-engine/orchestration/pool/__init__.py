"""
Worker pool management subpackage.

Split out of ``orchestration/worker_pool.py`` as part of issue #1767:

- :mod:`orchestration.pool.models`      — ``WorkerType``, ``WorkerStats``
- :mod:`orchestration.pool.worker_pool` — ``WorkerPool``
- :mod:`orchestration.pool.executor`    — ``create_agent_executor``, ``setup_signal_handlers``
"""

from .executor import create_agent_executor, setup_signal_handlers
from .models import WorkerStats, WorkerType
from .worker_pool import WorkerPool

__all__ = [
    "WorkerPool",
    "WorkerStats",
    "WorkerType",
    "create_agent_executor",
    "setup_signal_handlers",
]
