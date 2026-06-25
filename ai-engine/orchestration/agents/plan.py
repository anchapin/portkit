"""
Step and plan definitions for the RunAgent framework.

Extracted from ``orchestration/run_agent.py`` as part of issue #1767.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import Constraint, StepContext

logger = logging.getLogger(__name__)


class Step:
    """A single executable step in the RunAgent framework"""

    def __init__(
        self,
        step_id: str,
        name: str,
        description: str,
        execute_fn: Callable[[StepContext], Any],
        constraints: Optional[List[Constraint]] = None,
        pre_conditions: Optional[List[Callable[[StepContext], bool]]] = None,
        post_conditions: Optional[List[Callable[[StepContext, Any], bool]]] = None,
        rollback_fn: Optional[Callable[[StepContext], None]] = None,
    ):
        self.step_id = step_id
        self.name = name
        self.description = description
        self.execute_fn = execute_fn
        self.constraints = constraints or []
        self.pre_conditions = pre_conditions or []
        self.post_conditions = post_conditions or []
        self.rollback_fn = rollback_fn

    def validate_constraints(self, context: StepContext) -> Tuple[bool, List[str]]:
        """Validate all constraints for this step"""
        violations = []
        for constraint in self.constraints:
            try:
                if not constraint.validator(context):
                    violations.append(f"{constraint.name}: {constraint.description}")
                    if constraint.severity == "error":
                        logger.error(
                            f"Constraint violation in step {self.step_id}: {constraint.name}"
                        )
                    else:
                        logger.warning(
                            f"Constraint warning in step {self.step_id}: {constraint.name}"
                        )
            except Exception as e:
                violations.append(f"{constraint.name}: validation error - {str(e)}")
                logger.error(f"Constraint validation error in step {self.step_id}: {e}")

        return len(violations) == 0, violations


class RunAgentPlan:
    """A plan consisting of ordered steps with cross-step dependencies"""

    def __init__(
        self,
        plan_id: str,
        name: str,
        description: str,
        steps: Optional[List[Step]] = None,
        global_constraints: Optional[List[Constraint]] = None,
    ):
        self.plan_id = plan_id
        self.name = name
        self.description = description
        self.steps: List[Step] = steps or []
        self.global_constraints: List[Constraint] = global_constraints or []
        self._step_index: Dict[str, Step] = {s.step_id: s for s in self.steps}

    def add_step(self, step: Step) -> None:
        """Add a step to the plan"""
        self.steps.append(step)
        self._step_index[step.step_id] = step

    def get_step(self, step_id: str) -> Optional[Step]:
        """Get a step by ID"""
        return self._step_index.get(step_id)

    def get_step_order(self) -> List[str]:
        """Get the ordered list of step IDs"""
        return [s.step_id for s in self.steps]

    def validate_plan(self) -> Tuple[bool, List[str]]:
        """Validate the plan structure"""
        errors = []

        # Check for duplicate step IDs
        step_ids = [s.step_id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("Duplicate step IDs found")

        # Check that steps have execute functions
        for step in self.steps:
            if not callable(step.execute_fn):
                errors.append(f"Step {step.step_id} has no executable function")

        # Check for circular dependencies (would require dependency graph)

        return len(errors) == 0, errors
