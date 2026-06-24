"""
Conversion-related Celery tasks.

Includes the per-domain task handlers (conversion, asset conversion, Java
analysis, texture extraction, model conversion), their shared_task convenience
wrappers, and the legacy generic ``enqueue_task`` entry point used across the
codebase.

Task names are preserved as ``services.celery_tasks.*`` for runtime
compatibility (celery routing, beat schedule, in-flight tasks).

Issue: #1098 - Consolidate task queues
Issue: #1743 - Split celery_tasks.py into task domain modules
"""

import json
import logging
import time
import uuid
from typing import Any, Dict

from celery import shared_task

from services.celery_config import celery_app
from services.tasks.base import (
    QUEUE_NAMES,
    METRICS_KEY,
    TaskData,
    TaskPriority,
    _get_redis_sync,
    _run_async,
)

logger = logging.getLogger(__name__)


def handle_conversion_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle conversion task - runs in worker process."""
    from services.conversion_service import process_conversion_task as _process

    job_id = payload.get("job_id")
    file_id = payload.get("file_id")
    logger.info(f"Processing conversion job: {job_id}")
    try:
        return _run_async(_process(payload))
    except Exception as e:
        logger.error(f"Conversion job {job_id} failed: {e}")
        raise


def handle_asset_conversion_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle asset conversion task."""
    from services.asset_conversion_service import asset_conversion_service as _svc

    asset_id = payload.get("asset_id")
    logger.info(f"Processing asset conversion: {asset_id}")
    try:
        return _run_async(_svc.convert_asset(asset_id))
    except Exception as e:
        logger.error(f"Asset conversion {asset_id} failed: {e}")
        raise


def handle_java_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle Java analysis task."""
    from services.java_parser import analyze_java_file
    from db import crud
    from db.base import AsyncSessionLocal

    mod_id = payload.get("mod_id")
    logger.info(f"Processing Java analysis: {mod_id}")
    try:

        async def _analyze():
            async with AsyncSessionLocal() as session:
                mod = await crud.get_mod(session, mod_id)
                if not mod:
                    raise ValueError(f"Mod {mod_id} not found")
                source_code = mod.source_code or ""
                return analyze_java_file(source_code, f"mod_{mod_id}.java")

        result = _run_async(_analyze())
        return {"mod_id": mod_id, "status": "analyzed", "result": result}
    except Exception as e:
        logger.error(f"Java analysis {mod_id} failed: {e}")
        raise


def handle_texture_extraction_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle texture extraction task."""
    from utils.texture_metadata_extractor import TextureMetadataExtractor

    jar_path = payload.get("jar_path")
    logger.info(f"Processing texture extraction: {jar_path}")
    try:
        extractor = TextureMetadataExtractor()
        result = _run_async(extractor.extract_from_jar(jar_path))
        return {"jar_path": jar_path, "status": "extracted", "result": result}
    except Exception as e:
        logger.error(f"Texture extraction {jar_path} failed: {e}")
        raise


def handle_model_conversion_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle model conversion task."""
    from services.asset_conversion_service import asset_conversion_service as _svc

    model_id = payload.get("model_id")
    logger.info(f"Processing model conversion: {model_id}")
    try:
        return _run_async(_svc.convert_asset(model_id))
    except Exception as e:
        logger.error(f"Model conversion {model_id} failed: {e}")
        raise


# Conversion task shortcuts
@shared_task(name="services.celery_tasks.conversion_task")
def conversion_task(job_id: str, file_id: str) -> Dict[str, Any]:
    """Convenience task for conversion jobs."""
    return handle_conversion_task({"job_id": job_id, "file_id": file_id})


@shared_task(name="services.celery_tasks.asset_conversion_task")
def asset_conversion_task(asset_id: str) -> Dict[str, Any]:
    """Convenience task for asset conversion."""
    return handle_asset_conversion_task({"asset_id": asset_id})


@shared_task(name="services.celery_tasks.java_analysis_task")
def java_analysis_task(mod_id: str) -> Dict[str, Any]:
    """Convenience task for Java analysis."""
    return handle_java_analysis_task({"mod_id": mod_id})


@shared_task(name="services.celery_tasks.texture_extraction_task")
def texture_extraction_task(jar_path: str) -> Dict[str, Any]:
    """Convenience task for texture extraction."""
    return handle_texture_extraction_task({"jar_path": jar_path})


@shared_task(name="services.celery_tasks.model_conversion_task")
def model_conversion_task(model_id: str) -> Dict[str, Any]:
    """Convenience task for model conversion."""
    return handle_model_conversion_task({"model_id": model_id})


# Legacy compatibility - expose same interface as old task_queue_enhanced
async def enqueue_task(
    name: str,
    payload: Dict[str, Any],
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 3,
    timeout_seconds: int = 300,
    subscription_tier: str = "free",
) -> TaskData:
    """Async wrapper for enqueueing tasks - maintains compatibility with old code.

    Args:
        name: Task name (conversion, asset_conversion, etc.)
        payload: Task payload data
        priority: Task priority (LOW, NORMAL, HIGH, CRITICAL)
        max_retries: Maximum retry attempts
        timeout_seconds: Task timeout in seconds (overrides tier-based default if > 0)
        subscription_tier: User's subscription tier for timeout calculation (Issue #1151)
    """
    # Issue #1151: Use tier-based timeout if not explicitly overridden
    if timeout_seconds == 300:
        from services.celery_config import get_conversion_timeout

        tier_timeout = get_conversion_timeout(subscription_tier)
        timeout_seconds = tier_timeout

    task = TaskData(
        id=str(uuid.uuid4()),
        name=name,
        payload=payload,
        priority=priority,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
    )

    r = _get_redis_sync()
    r.set(f"portkit:task:{task.id}", json.dumps(task.to_dict()), ex=86400)

    queue_name = QUEUE_NAMES[priority]
    r.zadd(queue_name, {task.id: time.time()})
    r.hincrby(METRICS_KEY, "tasks_enqueued", 1)

    celery_app.send_task(
        "services.celery_tasks.process_task",
        args=[task.id],
        queue=queue_name,
        timeout=timeout_seconds,
        soft_timeout=timeout_seconds - 30,  # Soft timeout 30s before hard timeout
    )

    return task


# Backwards compatibility alias
celery_enqueue = enqueue_task
