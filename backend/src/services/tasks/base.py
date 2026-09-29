"""
Base types, constants, and shared helpers for Celery tasks.

Holds the Celery task base class, retry policies, task data structures,
queue constants, and the shared sync-Redis / async-bridge helpers used by
every task domain module.

Issue: #1098 - Consolidate task queues: remove task_queue.py duplicate, migrate to Celery
Issue: #1743 - Split celery_tasks.py into task domain modules
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import redis
import sentry_sdk
from celery import Task

from services.celery_config import REDIS_URL
from services.sentry_config import init_celery_sentry

logger = logging.getLogger(__name__)

# Initialize Sentry for Celery workers (import-time side effect preserved from
# the original celery_tasks.py so workers are instrumented on import).
init_celery_sentry()


class TaskStatus(Enum):
    """Task status enum with lifecycle states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"
    RETRYING = "retrying"
    TIMEOUT = "timeout"  # Issue #1151: Timeout status for clean timeout response


@dataclass
class TimeoutResult:
    """Structured timeout response (not a 500) - Issue #1151"""

    status: str = "timeout"
    message: str = ""
    timeout_seconds: int = 0
    tier: str = "free"
    can_retry: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "timeout",
            "error_code": "CONVERSION_TIMEOUT",
            "message": self.message,
            "timeout_seconds": self.timeout_seconds,
            "tier": self.tier,
            "can_retry": self.can_retry,
            "retry_after_seconds": min(self.timeout_seconds * 2, 3600),
        }


class TaskPriority(IntEnum):
    """Task priority enum."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class RetryPolicy:
    """Configurable retry policy for tasks."""

    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0
    backoff_multiplier: float = 2.0
    retryable_errors: List[str] = field(default_factory=list)  # Added for backward compat

    def calculate_delay(self, retry_count: int) -> float:
        """Calculate delay for exponential backoff."""
        delay = self.initial_delay_seconds * (self.backoff_multiplier**retry_count)
        return min(delay, self.max_delay_seconds)

    def should_retry(self, error_type: str, retry_count: int) -> bool:
        """Determine if a task should be retried based on error and retry count."""
        if retry_count >= self.max_retries:
            return False
        return not (self.retryable_errors and error_type not in self.retryable_errors)


DEFAULT_RETRY_POLICY = RetryPolicy()
CONVERSION_RETRY_POLICY = RetryPolicy(
    max_retries=5,
    initial_delay_seconds=2.0,
    max_delay_seconds=600.0,
)


@dataclass
class TaskData:
    """Task data structure stored in Redis."""

    id: str
    name: str
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.QUEUED
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[datetime] = None
    timeout_seconds: int = 300

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "payload": self.payload,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": (self.next_retry_at.isoformat() if self.next_retry_at else None),
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskData":
        return cls(
            id=data["id"],
            name=data["name"],
            payload=data["payload"],
            status=TaskStatus(data["status"]),
            priority=TaskPriority(data["priority"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            result=data.get("result"),
            error=data.get("error"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            next_retry_at=(
                datetime.fromisoformat(data["next_retry_at"]) if data.get("next_retry_at") else None
            ),
            timeout_seconds=data.get("timeout_seconds", 300),
        )


# Queue constants
QUEUE_NAMES = {
    TaskPriority.LOW: "portkit:queue:low",
    TaskPriority.NORMAL: "portkit:queue:normal",
    TaskPriority.HIGH: "portkit:queue:high",
    TaskPriority.CRITICAL: "portkit:queue:critical",
}
DEAD_LETTER_QUEUE = "portkit:dead_letter"
PROCESSING_SET = "portkit:processing"
METRICS_KEY = "portkit:metrics"
RETRY_QUEUE = "portkit:retry"
TASK_KEY_PREFIX = "portkit:task:"


def _get_redis_sync():
    """Get synchronous Redis client for Celery tasks."""
    return redis.from_url(REDIS_URL, decode_responses=True)


def _run_async(coro):
    """Run an async coroutine from synchronous context.

    This is used by Celery task handlers (which run synchronously) to call
    async service functions.

    When no event loop exists, creates a new one and runs the coroutine.
    When called from an already-running async context, runs in a separate
    thread with its own event loop to avoid blocking.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result(timeout=300)


class CeleryTaskBase(Task):
    """Base class for Celery tasks with retry logic."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(f"Task {task_id} failed: {exc}")
        sentry_sdk.capture_exception(
            exc,
            scope={
                "task_id": task_id,
                "task_name": self.name,
                "args": args,
                "kwargs": kwargs,
            },
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        logger.info(f"Task {task_id} retrying: {exc}")
        sentry_sdk.capture_message(
            f"Task retry: {task_id}",
            level="warning",
            scope={
                "task_id": task_id,
                "task_name": self.name,
                "retry_count": self.request.retries,
            },
        )
