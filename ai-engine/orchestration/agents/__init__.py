"""
RunAgent constraint-guided execution subpackage.

Split out of ``orchestration/run_agent.py`` as part of issue #1767:

- :mod:`orchestration.agents.models`      — dataclasses, enums, exceptions
- :mod:`orchestration.agents.plan`        — ``Step``, ``RunAgentPlan``
- :mod:`orchestration.agents.runner`      — ``RunAgent`` engine
- :mod:`orchestration.agents.constraints` — validator factories
"""

from .constraints import (
    create_conversion_constraints,
    disallow_out_of_order_execution,
    require_key_in_output,
    require_previous_step_output,
    validate_no_missing_dependencies,
    validate_step_timeout,
)
from .models import (
    Constraint,
    ConstraintViolation,
    ExecutionTrace,
    StepContext,
    StepOrderError,
    StepResult,
    StepStatus,
)
from .plan import RunAgentPlan, Step
from .runner import RunAgent

__all__ = [
    "Constraint",
    "ConstraintViolation",
    "ExecutionTrace",
    "RunAgent",
    "RunAgentPlan",
    "Step",
    "StepContext",
    "StepOrderError",
    "StepResult",
    "StepStatus",
    "create_conversion_constraints",
    "disallow_out_of_order_execution",
    "require_key_in_output",
    "require_previous_step_output",
    "validate_no_missing_dependencies",
    "validate_step_timeout",
]
