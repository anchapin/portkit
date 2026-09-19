"""
Cleanup-related Celery tasks.

Includes old-task reaping, orphaned JAR / output file purging, and post-
conversion input file deletion.

Task names are preserved as ``services.celery_tasks.*`` for runtime
compatibility (celery routing, beat schedule, in-flight tasks).

Issue: #1156 - JAR data retention: 24hr auto-delete + Privacy Policy statement
Issue: #1743 - Split celery_tasks.py into task domain modules
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from celery import shared_task

from services.audit_logger import get_audit_logger
from services.celery_config import celery_app
from services.tasks.base import (
    METRICS_KEY,
    PROCESSING_SET,
    QUEUE_NAMES,
    RETRY_QUEUE,
    _get_redis_sync,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="services.celery_tasks.cleanup_old_tasks")
def cleanup_old_tasks(max_age_hours: int = 24) -> Dict[str, Any]:
    """Clean up old completed/failed tasks."""
    r = _get_redis_sync()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    cleaned = 0

    for key in r.scan_iter("portkit:task:*"):
        if key == METRICS_KEY:
            continue
        task_data = r.get(key)
        if task_data:
            task_dict = json.loads(task_data)
            status = task_dict.get("status")
            if status in ("completed", "failed", "cancelled", "dead_letter"):
                completed_at = task_dict.get("completed_at")
                if completed_at:
                    completed_time = datetime.fromisoformat(completed_at)
                    if completed_time < cutoff:
                        r.delete(key)
                        cleaned += 1

    logger.info(f"Cleaned up {cleaned} old tasks")
    return {"cleaned": cleaned}


@celery_app.task(name="services.celery_tasks.purge_orphaned_files")
def purge_orphaned_files(max_age_hours: int = 24) -> Dict[str, Any]:
    """
    Purge orphaned JAR files older than max_age_hours.

    An orphaned file is one that has no associated active job
    (not in conversion queue, not being processed).

    Issue: #1156 - JAR data retention: 24hr auto-delete + Privacy Policy statement
    """
    from core.storage import storage_manager

    try:
        audit = get_audit_logger()
    except Exception:
        audit = None

    r = _get_redis_sync()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    max_age_days = 7  # For output files (.mcaddon)
    output_cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    deleted_input = 0
    deleted_output = 0
    errors = 0

    active_jobs = set()
    for queue_name in QUEUE_NAMES.values():
        for task_id in r.zrange(queue_name, 0, -1):
            active_jobs.add(task_id)
    for task_id in r.smembers(PROCESSING_SET):
        active_jobs.add(task_id)
    for task_id in r.zrange(RETRY_QUEUE, 0, -1):
        active_jobs.add(task_id)

    uploads_base = os.path.join(storage_manager.base_path, storage_manager.UPLOADS_DIR)
    if os.path.exists(uploads_base):
        for root, dirs, files in os.walk(uploads_base):
            for filename in files:
                if not filename.endswith(".jar"):
                    continue
                file_path = os.path.join(root, filename)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < cutoff:
                        rel_path = os.path.relpath(file_path, uploads_base)
                        path_parts = rel_path.split(os.sep)
                        if len(path_parts) >= 2:
                            job_id = path_parts[1]
                            if job_id not in active_jobs:
                                os.remove(file_path)
                                if audit:
                                    audit.log_file_deleted(
                                        job_id=job_id,
                                        filename=filename,
                                        deleted_by="system",
                                        reason="orphaned_file_24h",
                                    )
                                deleted_input += 1
                except OSError as e:
                    logger.error(f"Error purging {file_path}: {e}")
                    errors += 1

    results_base = os.path.join(storage_manager.base_path, storage_manager.RESULTS_DIR)
    if os.path.exists(results_base):
        for root, dirs, files in os.walk(results_base):
            for filename in files:
                if not filename.endswith((".mcaddon", ".zip")):
                    continue
                file_path = os.path.join(root, filename)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < output_cutoff:
                        rel_path = os.path.relpath(file_path, results_base)
                        path_parts = rel_path.split(os.sep)
                        if len(path_parts) >= 2:
                            job_id = path_parts[1]
                            if job_id not in active_jobs:
                                os.remove(file_path)
                                if audit:
                                    audit.log_file_deleted(
                                        job_id=job_id,
                                        filename=filename,
                                        deleted_by="system",
                                        reason="orphaned_output_7d",
                                    )
                                deleted_output += 1
                except OSError as e:
                    logger.error(f"Error purging {file_path}: {e}")
                    errors += 1

    logger.info(
        f"Purged {deleted_input} orphaned input files, {deleted_output} orphaned output files, {errors} errors"
    )
    return {
        "deleted_input": deleted_input,
        "deleted_output": deleted_output,
        "errors": errors,
    }


@shared_task(name="services.celery_tasks.delete_input_file")
def delete_input_file(job_id: str, file_id: str) -> Dict[str, Any]:
    """
    Delete the original input JAR file after conversion completes.

    Issue: #1156 - JAR data retention: 24hr auto-delete + Privacy Policy statement
    """
    try:
        audit = get_audit_logger()
    except Exception:
        audit = None

    file_path = os.path.join(os.getenv("TEMP_UPLOADS_DIR", "temp_uploads"), f"{file_id}.jar")

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            if audit:
                audit.log_file_deleted(
                    job_id=job_id,
                    filename=f"{file_id}.jar",
                    deleted_by="system",
                    reason="conversion_complete",
                )
            logger.info(f"Deleted input file: {file_path}")
            return {"deleted": True, "file_path": file_path}
        else:
            logger.warning(f"Input file not found for deletion: {file_path}")
            return {"deleted": False, "file_path": file_path, "reason": "file_not_found"}
    except OSError as e:
        logger.error(f"Error deleting input file {file_path}: {e}")
        return {"deleted": False, "error": str(e)}
