"""
Celery tasks subpackage — domain-split from the original celery_tasks.py.

Modules:
- base: TaskStatus, TaskPriority, TaskData, RetryPolicy, TimeoutResult, queue
  constants, CeleryTaskBase, shared sync/async helpers, Sentry init
- conversion_tasks: conversion handlers, convenience tasks, enqueue_task
- queue_tasks: process_task dispatcher, retry/timeout/dead-letter helpers,
  queue introspection (status, stats, cancel, health, retry queue)
- cleanup_tasks: old-task reaping, orphaned file purge, input file deletion
- inference_tasks: self-hosted LLM inference, heavy task

All Celery task names are preserved as ``services.celery_tasks.*`` so existing
routing (celery_config task_routes / beat_schedule) and in-flight tasks keep
working. The original ``services/celery_tasks.py`` is now a thin re-export
shim over this package.

Issue: #1098 - Consolidate task queues
Issue: #1743 - Split celery_tasks.py into task domain modules
"""

# Importing every task module at package import time ensures the
# @celery_app.task / @shared_task decorators run and register tasks under their
# canonical ``services.celery_tasks.*`` names when a worker (or the shim) loads
# this package.
from services.tasks import base, cleanup_tasks, conversion_tasks, inference_tasks, queue_tasks  # noqa: F401
from services.tasks.base import (
    CeleryTaskBase,
    CONVERSION_RETRY_POLICY,
    DEAD_LETTER_QUEUE,
    DEFAULT_RETRY_POLICY,
    METRICS_KEY,
    PROCESSING_SET,
    QUEUE_NAMES,
    RETRY_QUEUE,
    RetryPolicy,
    TASK_KEY_PREFIX,
    TaskData,
    TaskPriority,
    TaskStatus,
    TimeoutResult,
    _get_redis_sync,
    _run_async,
    init_celery_sentry,
)
from services.tasks.cleanup_tasks import (
    cleanup_old_tasks,
    delete_input_file,
    purge_orphaned_files,
)
from services.tasks.conversion_tasks import (
    asset_conversion_task,
    celery_enqueue,
    conversion_task,
    enqueue_task,
    handle_asset_conversion_task,
    handle_conversion_task,
    handle_java_analysis_task,
    handle_model_conversion_task,
    handle_texture_extraction_task,
    java_analysis_task,
    model_conversion_task,
    texture_extraction_task,
)
from services.tasks.inference_tasks import heavy_task, llm_inference_task
from services.tasks.queue_tasks import (
    _enqueue_task_sync,
    _fail_task,
    _get_task_handler,
    _timeout_task,
    cancel_task,
    get_dead_letter_tasks,
    get_queue_stats,
    get_task_status,
    health_check,
    process_retry_queue,
    process_task,
    reprocess_dead_letter_task,
)

# Re-export Celery app for convenience
from services.celery_config import celery_app

__all__ = [
    # Submodules
    "base",
    "cleanup_tasks",
    "conversion_tasks",
    "inference_tasks",
    "queue_tasks",
    # Base types & constants
    "TaskStatus",
    "TaskPriority",
    "TaskData",
    "TimeoutResult",
    "RetryPolicy",
    "DEFAULT_RETRY_POLICY",
    "CONVERSION_RETRY_POLICY",
    "QUEUE_NAMES",
    "DEAD_LETTER_QUEUE",
    "PROCESSING_SET",
    "METRICS_KEY",
    "RETRY_QUEUE",
    "TASK_KEY_PREFIX",
    "CeleryTaskBase",
    # Conversion domain
    "handle_conversion_task",
    "handle_asset_conversion_task",
    "handle_java_analysis_task",
    "handle_texture_extraction_task",
    "handle_model_conversion_task",
    "conversion_task",
    "asset_conversion_task",
    "java_analysis_task",
    "texture_extraction_task",
    "model_conversion_task",
    "enqueue_task",
    "celery_enqueue",
    # Queue domain
    "process_task",
    "process_retry_queue",
    "_enqueue_task_sync",
    "_fail_task",
    "_timeout_task",
    "_get_task_handler",
    "get_task_status",
    "cancel_task",
    "get_queue_stats",
    "get_dead_letter_tasks",
    "reprocess_dead_letter_task",
    "health_check",
    # Cleanup domain
    "cleanup_old_tasks",
    "purge_orphaned_files",
    "delete_input_file",
    # Inference domain
    "llm_inference_task",
    "heavy_task",
    # Helpers
    "_get_redis_sync",
    "_run_async",
    "init_celery_sentry",
    # Celery app
    "celery_app",
]
