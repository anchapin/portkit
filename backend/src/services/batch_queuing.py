"""
Intelligent Batch Queuing System

.. deprecated::
    Use :mod:`services.batch` instead.
    This module is a backwards-compatibility shim.

    - ``services.batch.models`` — QueuePriority, BatchJobStatus, BatchJob, BatchGroup, BatchQueueStats
    - ``services.batch.queue_manager`` — IntelligentBatchQueue, get_batch_queue, reset_batch_queue

Pipeline Flow:
1. Jobs enter queue
2. Classifier groups by mode (Simple together, Expert together)
3. Priority sorter arranges within groups
4. Resource allocator assigns resources
5. Parallel processor executes

See: docs/GAP-ANALYSIS-v2.5.md (GAP-2.5-05)

Issue: #1769 - Split batch_queuing.py into focused modules
"""

# Re-export all public symbols from the new module structure
from services.batch import (
    QueuePriority,
    BatchJobStatus,
    BatchJob,
    BatchGroup,
    BatchQueueStats,
    IntelligentBatchQueue,
    get_batch_queue,
    reset_batch_queue,
)

__all__ = [
    "QueuePriority",
    "BatchJobStatus",
    "BatchJob",
    "BatchGroup",
    "BatchQueueStats",
    "IntelligentBatchQueue",
    "get_batch_queue",
    "reset_batch_queue",
]
