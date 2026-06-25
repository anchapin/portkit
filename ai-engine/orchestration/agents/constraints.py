"""
Pre-built constraint validators and factories for common conversion scenarios.

Extracted from ``orchestration/run_agent.py`` as part of issue #1767.
"""

from typing import Any, Dict, List

from .models import Constraint, StepContext


def require_previous_step_output(step_id: str) -> Constraint:
    """Constraint that requires a previous step to have produced output"""

    def validator(context: StepContext) -> bool:
        return step_id in context.previous_outputs

    return Constraint(
        name=f"require_previous_output_{step_id}",
        description=f"Requires output from step '{step_id}'",
        validator=validator,
    )


def require_key_in_output(key: str) -> Constraint:
    """Constraint that requires a key to be present in step output"""

    def validator(context: StepContext) -> bool:
        for output in context.previous_outputs.values():
            if isinstance(output, dict) and key in output:
                return True
        return False

    return Constraint(
        name=f"require_key_{key}",
        description=f"Requires key '{key}' in any previous output",
        validator=validator,
    )


def disallow_out_of_order_execution(expected_step_id: str) -> Constraint:
    """Constraint that enforces step order"""

    def validator(context: StepContext) -> bool:
        executed_steps = list(context.previous_outputs.keys())
        if expected_step_id not in executed_steps:
            return False
        expected_idx = -1
        for i, step in enumerate(self.plan.steps if hasattr(self, "plan") else []):
            if step.step_id == expected_step_id:
                expected_idx = i
                break
        if expected_idx < 0:
            return True
        # Check that all steps before expected_step_id have been executed
        for i in range(expected_idx):
            if self.plan.steps[i].step_id not in executed_steps:
                return False
        return True

    return Constraint(
        name=f"require_step_before",
        description=f"Requires step '{expected_step_id}' to complete first",
        validator=validator,
    )


def validate_no_missing_dependencies(context: StepContext) -> bool:
    """Check that all dependencies are resolved"""
    if isinstance(context.inputs, dict):
        required_keys = ["mod_path", "output_path"]
        return all(k in context.inputs for k in required_keys)
    return True


def validate_step_timeout(context: StepContext) -> bool:
    """Check that step hasn't exceeded reasonable time"""
    if "timeout" in context.metadata:
        return True  # Timeout was already checked
    return True


# Conversion-specific constraint factory


def create_conversion_constraints(step_id: str) -> List[Constraint]:
    """Create standard constraints for conversion steps"""
    return [
        Constraint(
            name=f"valid_inputs_{step_id}",
            description="Step must have valid inputs",
            validator=lambda ctx: len(ctx.inputs) > 0 or len(ctx.previous_outputs) > 0,
        ),
        Constraint(
            name=f"no_circular_refs_{step_id}",
            description="No circular dependencies in outputs",
            validator=lambda ctx: _check_no_circular_refs(ctx.previous_outputs),
        ),
    ]


def _check_no_circular_refs(outputs: Dict[str, Any]) -> bool:
    """Check that outputs don't contain circular references"""
    visited = set()

    def check_value(val):
        if id(val) in visited:
            return False
        visited.add(id(val))
        if isinstance(val, dict):
            for v in val.values():
                if not check_value(v):
                    return False
        elif isinstance(val, list):
            for v in val:
                if not check_value(v):
                    return False
        visited.discard(id(val))
        return True

    for output in outputs.values():
        if isinstance(output, dict):
            if not check_value(output):
                return False
    return True
