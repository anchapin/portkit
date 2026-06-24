"""
Data models, enums, and exceptions for the RunAgent constraint-guided
execution framework.

Extracted from ``orchestration/run_agent.py`` as part of issue #1767.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class StepStatus(Enum):
    """Status of a step in the RunAgent execution"""
    PENDING = "pending"
    VALIDATING = "validating"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class ConstraintViolation(Exception):
    """Raised when a step violates its constraints"""
    pass


class StepOrderError(Exception):
    """Raised when steps are executed out of order"""
    pass


@dataclass
class Constraint:
    """A constraint that must be satisfied for step execution"""
    name: str
    description: str
    validator: Callable[["StepContext"], bool]
    severity: str = "error"  # "error", "warning", "info"
    remediation: Optional[str] = None


@dataclass
class StepContext:
    """Context passed to each step during execution"""
    step_id: str
    step_name: str
    inputs: Dict[str, Any]
    previous_outputs: Dict[str, Any]
    execution_trace: List[Dict[str, Any]]
    constraints: List[Constraint] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """Result of a step execution"""
    step_id: str
    status: StepStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration: Optional[float] = None
    constraints_satisfied: bool = True
    constraint_violations: List[str] = field(default_factory=list)
    trace_entry: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionTrace:
    """Complete trace of RunAgent execution"""
    execution_id: str
    plan_name: str
    start_time: float
    end_time: Optional[float] = None
    steps: List[StepResult] = field(default_factory=list)
    total_constraints_checked: int = 0
    constraint_violations: List[str] = field(default_factory=list)
    rollback_count: int = 0

    @property
    def duration(self) -> Optional[float]:
        if self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "plan_name": self.plan_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "steps": [
                {
                    "step_id": s.step_id,
                    "status": s.status.value,
                    "output": s.output,
                    "error": s.error,
                    "duration": s.duration,
                    "constraints_satisfied": s.constraints_satisfied,
                    "constraint_violations": s.constraint_violations,
                }
                for s in self.steps
            ],
            "total_constraints_checked": self.total_constraints_checked,
            "constraint_violations": self.constraint_violations,
            "rollback_count": self.rollback_count,
        }
