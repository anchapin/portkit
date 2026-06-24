"""
Batch Queue Models

Shared dataclasses and enums for the batch queuing phase.

Issue: #1769 - Split batch_queuing.py into focused modules
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from dataclasses import dataclass, field


class QueuePriority(str, Enum):
    """Queue priority levels for job scheduling."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

    def to_score(self) -> int:
        """Convert priority to numeric score for sorting."""
        scores = {
            QueuePriority.LOW: 0,
            QueuePriority.NORMAL: 1,
            QueuePriority.HIGH: 2,
            QueuePriority.CRITICAL: 3,
        }
        return scores[self]


class BatchJobStatus(str, Enum):
    """Status of a batch job."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchJob:
    """Represents a single job in the batch queue."""

    job_id: str
    user_id: str
    mod_data: Dict[str, Any]
    mode: Optional[Any] = None  # ConversionMode - avoids circular import
    mode_classification: Optional[Any] = None  # ModeClassificationResult
    priority: QueuePriority = QueuePriority.NORMAL
    priority_score: int = 1
    status: BatchJobStatus = BatchJobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    estimated_complexity: int = 0
    resource_requirements: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "BatchJob") -> bool:
        """Enable priority queue sorting."""
        return self.priority_score < other.priority_score


@dataclass
class BatchGroup:
    """A group of similar jobs batched together."""

    group_id: str
    mode: Any  # ConversionMode - avoids circular import
    jobs: List[BatchJob] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: BatchJobStatus = BatchJobStatus.PENDING
    completed_count: int = 0
    failed_count: int = 0

    @property
    def total_jobs(self) -> int:
        return len(self.jobs)

    @property
    def progress(self) -> float:
        if not self.jobs:
            return 0.0
        return (self.completed_count / len(self.jobs)) * 100


@dataclass
class BatchQueueStats:
    """Statistics for batch queue monitoring."""

    total_jobs_enqueued: int = 0
    total_jobs_processed: int = 0
    total_jobs_failed: int = 0
    total_batches_created: int = 0
    average_wait_time_seconds: float = 0.0
    average_processing_time_seconds: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Mutable collections - initialized in __post_init__ or lazily
    mode_distribution: Dict[Any, int] = field(default_factory=lambda: {})
    queue_depth_by_mode: Dict[Any, int] = field(default_factory=lambda: {})

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_jobs_enqueued": self.total_jobs_enqueued,
            "total_jobs_processed": self.total_jobs_processed,
            "total_jobs_failed": self.total_jobs_failed,
            "total_batches_created": self.total_batches_created,
            "mode_distribution": {
                (k.value if hasattr(k, "value") else str(k)): v
                for k, v in self.mode_distribution.items()
            },
            "average_wait_time_seconds": self.average_wait_time_seconds,
            "average_processing_time_seconds": self.average_processing_time_seconds,
            "queue_depth_by_mode": {
                (k.value if hasattr(k, "value") else str(k)): v
                for k, v in self.queue_depth_by_mode.items()
            },
            "last_updated": self.last_updated.isoformat(),
        }
