"""
Queue management and core processing Celery tasks.

Contains the main task dispatcher (``process_task``), the retry / timeout /
dead-letter helpers, the synchronous enqueue entry point, and the queue
introspection tasks (status, stats, cancel, health, retry-queue processing).

Task names are preserved as ``services.celery_tasks.*`` for runtime
compatibility (celery routing, beat schedule, in-flight tasks).

Issue: #1098 - Consolidate task queues
Issue: #1743 - Split celery_tasks.py into task domain modules
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import redis
from celery.exceptions import SoftTimeLimitExceeded

from services.celery_config import REDIS_URL, celery_app
from services.tasks.base import (
    DEAD_LETTER_QUEUE,
    DEFAULT_RETRY_POLICY,
    METRICS_KEY,
    PROCESSING_SET,
    QUEUE_NAMES,
    RETRY_QUEUE,
    CeleryTaskBase,
    TaskData,
    TaskPriority,
    TaskStatus,
    _get_redis_sync,
    _run_async,
)
from services.tasks.conversion_tasks import (
    handle_asset_conversion_task,
    handle_conversion_task,
    handle_java_analysis_task,
    handle_model_conversion_task,
    handle_texture_extraction_task,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=CeleryTaskBase, name="services.celery_tasks.process_task")
def process_task(self, task_id: str) -> Dict[str, Any]:
    """
    Process a task by ID - called by Celery workers.

    This is the main entry point for all task processing.
    """
    r = _get_redis_sync()

    try:
        task_data = r.get(f"portkit:task:{task_id}")
        if not task_data:
            logger.error(f"Task {task_id} not found in Redis")
            return {"status": "error", "message": "Task not found"}

        task = TaskData.from_dict(json.loads(task_data))

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)
        r.sadd(PROCESSING_SET, task_id)
        r.hincrby(METRICS_KEY, "tasks_dequeued", 1)

        logger.info(f"Processing task {task_id} ({task.name})")

        handler = _get_task_handler(task.name)
        if handler is None:
            raise ValueError(f"No handler for task type: {task.name}")

        result = handler(task.payload)

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        task.result = result
        r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)
        r.srem(PROCESSING_SET, task_id)
        r.hincrby(METRICS_KEY, "tasks_completed", 1)

        logger.info(f"Task {task_id} completed")
        return {"status": "success", "result": result}

    except SoftTimeLimitExceeded:
        logger.error(f"Task {task_id} soft time limit exceeded")
        _timeout_task(r, task_id)
        return {
            "status": "timeout",
            "error_code": "CONVERSION_TIMEOUT",
            "message": f"Conversion job exceeded time limit",
            "timeout_seconds": task.timeout_seconds,
            "tier": task.payload.get("subscription_tier", "free"),
            "can_retry": True,
            "retry_after_seconds": min(task.timeout_seconds * 2, 3600),
        }
    except Exception as exc:
        logger.error(f"Task {task_id} failed: {exc}")
        retry = _fail_task(r, task_id, str(exc), retry=True)
        if retry:
            raise self.retry(exc=exc, countdown=5)
        return {"status": "error", "message": str(exc)}


def _get_task_handler(task_name: str):
    """Get the handler function for a task name."""
    handlers = {
        "conversion": handle_conversion_task,
        "asset_conversion": handle_asset_conversion_task,
        "java_analysis": handle_java_analysis_task,
        "texture_extraction": handle_texture_extraction_task,
        "model_conversion": handle_model_conversion_task,
    }
    return handlers.get(task_name)


def _fail_task(r, task_id: str, error: str, retry: bool = True) -> bool:
    """Mark task as failed and potentially schedule retry."""
    task_data = r.get(f"portkit:task:{task_id}")
    if not task_data:
        return False

    task = TaskData.from_dict(json.loads(task_data))
    task.error = error

    retry_count = task.retry_count
    max_retries = task.max_retries

    if retry and retry_count < max_retries:
        delay = DEFAULT_RETRY_POLICY.calculate_delay(retry_count)
        next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)

        task.retry_count = retry_count + 1
        task.status = TaskStatus.RETRYING
        task.started_at = None
        task.next_retry_at = next_retry

        r.zadd(RETRY_QUEUE, {task_id: next_retry.timestamp()})
        r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)
        r.srem(PROCESSING_SET, task_id)
        r.hincrby(METRICS_KEY, "tasks_retried", 1)

        logger.info(f"Task {task_id} scheduled for retry ({retry_count + 1}/{max_retries})")
        return True
    else:
        if True:
            task.status = TaskStatus.DEAD_LETTER
            task.completed_at = datetime.now(timezone.utc)
            r.zadd(DEAD_LETTER_QUEUE, {task_id: time.time()})
            r.hincrby(METRICS_KEY, "tasks_dead_lettered", 1)
            logger.warning(f"Task {task_id} moved to dead letter queue: {error}")
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)
            r.hincrby(METRICS_KEY, "tasks_failed", 1)
            logger.error(f"Task {task_id} failed: {error}")

        r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)
        r.srem(PROCESSING_SET, task_id)
        return False


def _timeout_task(r, task_id: str) -> None:
    """Mark task as timed out with structured response - Issue #1151"""
    task_data = r.get(f"portkit:task:{task_id}")
    if not task_data:
        return

    task = TaskData.from_dict(json.loads(task_data))
    task.status = TaskStatus.TIMEOUT
    task.completed_at = datetime.now(timezone.utc)
    task.error = "Conversion job timed out"

    r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)
    r.srem(PROCESSING_SET, task_id)
    r.hincrby(METRICS_KEY, "tasks_timed_out", 1)
    logger.warning(f"Task {task_id} timed out")


@celery_app.task(name="services.celery_tasks.process_retry_queue")
def process_retry_queue() -> Dict[str, Any]:
    """Process tasks in the retry queue that are ready."""
    r = _get_redis_sync()
    now = time.time()
    task_ids = r.zrangebyscore(RETRY_QUEUE, min=0, max=now)
    requeued = 0

    for task_id in task_ids:
        r.zrem(RETRY_QUEUE, task_id)
        task_data = r.get(f"portkit:task:{task_id}")
        if task_data:
            task = TaskData.from_dict(json.loads(task_data))
            task.status = TaskStatus.QUEUED
            task.next_retry_at = None

            queue_name = QUEUE_NAMES[task.priority]
            r.zadd(queue_name, {task_id: time.time()})
            r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)
            requeued += 1

    if requeued > 0:
        logger.info(f"Re-queued {requeued} tasks from retry queue")

    return {"requeued": requeued}


@celery_app.task(name="services.celery_tasks._enqueue_task_sync")
def _enqueue_task_sync(
    name: str,
    payload: Dict[str, Any],
    priority: int = 1,
    max_retries: int = 3,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Internal: Enqueue a new task via Celery (synchronous)."""

    async def _enqueue():
        r = redis.from_url(REDIS_URL, decode_responses=True)

        task = TaskData(
            id=str(uuid.uuid4()),
            name=name,
            payload=payload,
            priority=TaskPriority(priority),
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

        r.set(f"portkit:task:{task.id}", json.dumps(task.to_dict()), ex=86400)

        queue_name = QUEUE_NAMES[task.priority]
        r.zadd(queue_name, {task.id: time.time()})
        r.hincrby(METRICS_KEY, "tasks_enqueued", 1)

        celery_app.send_task(
            "services.celery_tasks.process_task",
            args=[task.id],
            queue=queue_name,
            timeout=timeout_seconds,
        )

        logger.info(f"Task {task.id} ({name}) enqueued with priority {task.priority.name}")
        return {"task_id": task.id, "status": "queued"}

    return _run_async(_enqueue())


@celery_app.task(name="services.celery_tasks.get_task_status")
def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get task status by ID."""
    r = _get_redis_sync()
    task_data = r.get(f"portkit:task:{task_id}")
    if task_data:
        return json.loads(task_data)
    return None


@celery_app.task(name="services.celery_tasks.cancel_task")
def cancel_task(task_id: str) -> bool:
    """Cancel a queued task."""
    r = _get_redis_sync()
    task_data = r.get(f"portkit:task:{task_id}")
    if task_data:
        task_dict = json.loads(task_data)
        if task_dict["status"] == TaskStatus.QUEUED.value:
            task_dict["status"] = TaskStatus.CANCELLED.value
            task_dict["completed_at"] = datetime.now(timezone.utc).isoformat()
            r.set(f"portkit:task:{task_id}", json.dumps(task_dict), ex=86400)

            for queue_name in QUEUE_NAMES.values():
                r.zrem(queue_name, task_id)
            r.zrem(RETRY_QUEUE, task_id)

            r.hincrby(METRICS_KEY, "tasks_cancelled", 1)
            logger.info(f"Task {task_id} cancelled")
            return True
    return False


@celery_app.task(name="services.celery_tasks.get_queue_stats")
def get_queue_stats() -> Dict[str, Any]:
    """Get queue statistics."""
    r = _get_redis_sync()

    stats = {
        "queues": {},
        "total_queued": 0,
        "total_processing": r.scard(PROCESSING_SET),
        "total_dead_letter": r.zcard(DEAD_LETTER_QUEUE),
    }

    for priority, queue_name in QUEUE_NAMES.items():
        count = r.zcard(queue_name)
        stats["queues"][priority.name.lower()] = count
        stats["total_queued"] += count

    return stats


@celery_app.task(name="services.celery_tasks.get_dead_letter_tasks")
def get_dead_letter_tasks(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Get tasks from the dead letter queue."""
    r = _get_redis_sync()
    task_ids = r.zrange(DEAD_LETTER_QUEUE, start=offset, end=offset + limit - 1)

    tasks = []
    for task_id in task_ids:
        task_data = r.get(f"portkit:task:{task_id}")
        if task_data:
            tasks.append(json.loads(task_data))

    return tasks


@celery_app.task(name="services.celery_tasks.reprocess_dead_letter_task")
def reprocess_dead_letter_task(task_id: str) -> bool:
    """Move a task from dead letter queue back to main queue."""
    r = _get_redis_sync()
    task_data = r.get(f"portkit:task:{task_id}")
    if not task_data:
        return False

    task = TaskData.from_dict(json.loads(task_data))

    r.zrem(DEAD_LETTER_QUEUE, task_id)

    task.status = TaskStatus.QUEUED
    task.retry_count = 0
    task.error = None
    task.started_at = None
    task.completed_at = None

    queue_name = QUEUE_NAMES[task.priority]
    r.zadd(queue_name, {task_id: time.time()})
    r.set(f"portkit:task:{task_id}", json.dumps(task.to_dict()), ex=86400)

    r.hincrby(METRICS_KEY, "tasks_reprocessed", 1)
    logger.info(f"Task {task_id} reprocessed from dead letter queue")

    return True


@celery_app.task(name="services.celery_tasks.health_check")
def health_check() -> Dict[str, Any]:
    """Check queue health."""
    stats = get_queue_stats()
    issues = []

    if stats["total_queued"] > 1000:
        issues.append(f"Queue backlog is high: {stats['total_queued']} tasks")

    if stats["total_dead_letter"] > 50:
        issues.append(f"Dead letter queue has {stats['total_dead_letter']} tasks")

    return {
        "healthy": len(issues) == 0,
        "issues": issues,
        "stats": stats,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
