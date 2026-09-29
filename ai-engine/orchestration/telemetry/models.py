"""
Telemetry data models for orchestration monitoring.

Extracted from ``orchestration/monitoring.py`` as part of issue #1767.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PerformanceMetric:
    """Represents a performance metric measurement"""

    metric_name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionEvent:
    """Represents an execution event for monitoring"""

    event_type: str  # 'task_started', 'task_completed', 'task_failed', 'strategy_selected', etc.
    timestamp: float = field(default_factory=time.time)
    task_id: Optional[str] = None
    agent_name: Optional[str] = None
    strategy: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "strategy": self.strategy,
            "details": self.details,
        }
