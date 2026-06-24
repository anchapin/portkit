"""
Backward-compatibility shim for the Celery tasks package.

This module was previously a 33K monolith bundling every Celery task across
multiple business domains. It has been split into focused domain modules under
``services/tasks/``:

- ``services/tasks/base.py``            - types, constants, CeleryTaskBase, helpers
- ``services/tasks/conversion_tasks.py`` - conversion handlers & enqueue_task
- ``services/tasks/queue_tasks.py``      - process_task dispatcher & queue mgmt
- ``services/tasks/cleanup_tasks.py``    - file retention / purge tasks
- ``services/tasks/inference_tasks.py``  - LLM inference & heavy task

All Celery task names are preserved as ``services.celery_tasks.*`` so existing
routing (celery_config.task_routes / beat_schedule) and in-flight Redis tasks
keep working unchanged. This file now only re-exports the public API.

``redis`` is imported (and re-exported) so legacy patch targets such as
``src.services.celery_tasks.redis.from_url`` continue to resolve to the shared
``redis`` module object.

Issue: #1743 - Split celery_tasks.py into task domain modules
"""

import redis  # noqa: F401  (re-exported; preserves patch targets like redis.from_url)

from services.tasks import (  # noqa: F401
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
    _enqueue_task_sync,
    _fail_task,
    _get_redis_sync,
    _get_task_handler,
    _run_async,
    _timeout_task,
    asset_conversion_task,
    cancel_task,
    celery_enqueue,
    cleanup_old_tasks,
    conversion_task,
    delete_input_file,
    enqueue_task,
    get_dead_letter_tasks,
    get_queue_stats,
    get_task_status,
    handle_asset_conversion_task,
    handle_conversion_task,
    handle_java_analysis_task,
    handle_model_conversion_task,
    handle_texture_extraction_task,
    health_check,
    heavy_task,
    init_celery_sentry,
    java_analysis_task,
    llm_inference_task,
    model_conversion_task,
    process_retry_queue,
    process_task,
    purge_orphaned_files,
    reprocess_dead_letter_task,
    texture_extraction_task,
)

__all__ = [
    "redis",
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
]
