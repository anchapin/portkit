"""Queue backend adapter extracted from batch/queue_manager.py (Issue #1871).

Encapsulates Redis and Celery interaction details. The orchestration layer
(queue_manager.py) should depend on this module rather than importing broker
libraries directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class QueueBackendError(Exception):
    """Raised when the underlying queue broker fails an operation."""
    pass


class RedisQueueBackend:
    """Abstracts Redis calls for job state persistence and pub/sub."""

    def __init__(self, connection: Any) -> None:  # noqa: ANN401
        """Initialize with a configured redis.Redis client instance."""
        self._redis = connection

    def store_job_state(self, job_id: str, state: dict[str, Any]) -> None:
        """Persist current job status to Redis hash."""
        try:
            self._redis.hset(
                f"job:{job_id}",
                mapping={"payload": json.dumps(state, default=str)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist job state for %s: %s", job_id, exc)
            raise QueueBackendError(f"State persistence failed: {exc}") from exc

    def get_job_state(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve persisted job status. Returns None if job not found."""
        raw = self._redis.hget(f"job:{job_id}", "payload")
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Corrupted state payload for job %s: %s", job_id, exc)
            return None

    def publish_progress(self, job_id: str, progress: float, message: str = "") -> None:
        """Emit progress update via Redis channel."""
        payload = json.dumps({"job_id": job_id, "progress": progress, "message": message})
        self._redis.publish(f"progress:{job_id}", payload)


class CeleryTaskBackend:
    """Wraps Celery task submission and result polling."""

    def __init__(self, celery_app: Any) -> None:  # noqa: ANN401
        """Initialize with a configured celery.Celery app instance."""
        self._app = celery_app

    def submit_job(self, task_name: str, args: list[Any], kwargs: dict[str, Any]) -> str:
        """Queue a Celery task and return the generated task ID."""
        task = self._app.tasks.get(task_name)
        if not task:
            raise QueueBackendError(f"Unknown Celery task: {task_name}")
        async_result = task.delay(*args, **kwargs)
        return async_result.id

    def poll_result(self, task_id: str) -> dict[str, Any] | None:
        """Check task completion status without blocking."""
        from celery.result import AsyncResult  # noqa: PLC0415
        async_result = AsyncResult(task_id, app=self._app)
        if async_result.ready():
            return {"status": async_result.status, "result": async_result.get(timeout=0)}
        return None
