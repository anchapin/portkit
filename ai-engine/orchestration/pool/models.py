"""
Models and enums for the worker pool.

Extracted from ``orchestration/worker_pool.py`` as part of issue #1767.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WorkerType(Enum):
    """Types of workers for different execution contexts"""

    THREAD = "thread"  # For I/O-bound tasks (LLM API calls)
    PROCESS = "process"  # For CPU-bound tasks (file processing)
    ASYNC = "async"  # For async I/O operations


@dataclass
class WorkerStats:
    """Statistics for worker performance tracking"""

    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    average_task_time: float = 0.0
    last_activity: Optional[float] = None

    def update_completion(self, execution_time: float):
        """Update stats after successful task completion"""
        self.tasks_completed += 1
        self.total_execution_time += execution_time
        self.average_task_time = self.total_execution_time / self.tasks_completed
        self.last_activity = time.time()

    def update_failure(self):
        """Update stats after task failure"""
        self.tasks_failed += 1
        self.last_activity = time.time()
