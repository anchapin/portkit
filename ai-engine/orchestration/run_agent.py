"""
Backwards-compatibility shim.

The contents of this module have been split into the ``agents`` subpackage
per issue #1767:

- :mod:`orchestration.agents.models`      — dataclasses, enums, exceptions
- :mod:`orchestration.agents.plan`        — ``Step``, ``RunAgentPlan``
- :mod:`orchestration.agents.runner`      — ``RunAgent`` engine
- :mod:`orchestration.agents.constraints` — validator factories

This shim re-exports the previous public API so existing imports of the form
``from orchestration.run_agent import RunAgent`` keep working.
Prefer importing from :mod:`orchestration.agents` in new code.
"""

from .agents import (
    Constraint,
    ConstraintViolation,
    ExecutionTrace,
    RunAgent,
    RunAgentPlan,
    Step,
    StepContext,
    StepOrderError,
    StepResult,
    StepStatus,
    create_conversion_constraints,
    disallow_out_of_order_execution,
    require_key_in_output,
    require_previous_step_output,
    validate_no_missing_dependencies,
    validate_step_timeout,
)

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
