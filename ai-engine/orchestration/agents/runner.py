"""
RunAgent: constraint-guided execution engine.

Extracted from ``orchestration/run_agent.py`` as part of issue #1767.

Based on RunAgent: Interpreting Natural-Language Plans (https://arxiv.org/abs/2605.00798v1).
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import ExecutionTrace, StepContext, StepResult, StepStatus
from .plan import RunAgentPlan, Step

logger = logging.getLogger(__name__)


class RunAgent:
    """
    Constraint-guided execution framework for stepwise conversion.

    Wraps agent execution in explicit control constructs and rubric-based constraints
    to enforce strict stepwise adherence to Java-to-Bedrock mapping rules.
    """

    def __init__(
        self,
        plan: RunAgentPlan,
        enable_rollback: bool = True,
        max_rollbacks: int = 3,
        strict_mode: bool = True,
    ):
        """
        Initialize RunAgent with a plan

        Args:
            plan: RunAgentPlan defining the steps and constraints
            enable_rollback: Whether to enable automatic rollback on violations
            max_rollbacks: Maximum number of rollbacks allowed
            strict_mode: If True, violations cause immediate failure
        """
        self.plan = plan
        self.enable_rollback = enable_rollback
        self.max_rollbacks = max_rollbacks
        self.strict_mode = strict_mode

        self._execution_trace: Optional[ExecutionTrace] = None
        self._rollback_history: List[Dict[str, Any]] = []
        self._step_outputs: Dict[str, Any] = {}

        # Validate plan on initialization
        is_valid, errors = plan.validate_plan()
        if not is_valid:
            logger.error(f"Invalid RunAgent plan: {errors}")
            raise ValueError(f"Invalid RunAgent plan: {errors}")

        logger.info(f"RunAgent initialized with plan '{plan.name}' ({len(plan.steps)} steps)")

    async def execute(
        self,
        initial_inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
    ) -> Tuple[bool, ExecutionTrace]:
        """
        Execute the plan with constraint validation

        Args:
            initial_inputs: Initial inputs to pass to the first step
            execution_id: Optional execution ID for tracing

        Returns:
            Tuple of (success, execution_trace)
        """
        import uuid
        execution_id = execution_id or str(uuid.uuid4())[:8]

        logger.info(f"Starting RunAgent execution {execution_id} for plan '{self.plan.name}'")

        self._execution_trace = ExecutionTrace(
            execution_id=execution_id,
            plan_name=self.plan.name,
            start_time=time.time(),
        )
        self._rollback_history = []
        self._step_outputs = {}

        # Build initial context
        context = StepContext(
            step_id="init",
            step_name="initialization",
            inputs=initial_inputs,
            previous_outputs={},
            execution_trace=[],
            metadata={"execution_id": execution_id},
        )

        success = True

        for i, step in enumerate(self.plan.steps):
            logger.info(f"Executing step {i+1}/{len(self.plan.steps)}: {step.name} ({step.step_id})")

            step_result = await self._execute_step(step, context)

            self._execution_trace.steps.append(step_result)
            self._execution_trace.total_constraints_checked += (
                len(step.constraints) + len(self.plan.global_constraints)
            )

            if step_result.constraint_violations:
                self._execution_trace.constraint_violations.extend(
                    step_result.constraint_violations
                )

            if step_result.status == StepStatus.COMPLETED:
                # Update context for next step
                context.previous_outputs[step.step_id] = step_result.output
                context.execution_trace.append(step_result.trace_entry)
                self._step_outputs[step.step_id] = step_result.output

            elif step_result.status == StepStatus.FAILED:
                if step_result.constraint_violations and self.enable_rollback:
                    # Attempt rollback
                    rollback_success = await self._attempt_rollback(step, context)
                    if not rollback_success:
                        success = False
                        break
                else:
                    success = False
                    break

            elif step_result.status == StepStatus.SKIPPED:
                # Step was skipped, continue
                logger.info(f"Step {step.step_id} was skipped")

        self._execution_trace.end_time = time.time()

        logger.info(
            f"RunAgent execution {execution_id} completed: "
            f"success={success}, steps={len(self._execution_trace.steps)}, "
            f"rollbacks={self._execution_trace.rollback_count}"
        )

        return success, self._execution_trace

    async def _execute_step(self, step: Step, context: StepContext) -> StepResult:
        """Execute a single step with constraint validation"""
        start_time = time.time()
        step_context = StepContext(
            step_id=step.step_id,
            step_name=step.name,
            inputs=context.inputs,
            previous_outputs=context.previous_outputs.copy(),
            execution_trace=context.execution_trace.copy(),
            metadata=context.metadata.copy(),
        )

        # Phase 1: Constraint Validation
        step_context.status = StepStatus.VALIDATING

        # Check global constraints
        global_violations = []
        for constraint in self.plan.global_constraints:
            try:
                if not constraint.validator(step_context):
                    global_violations.append(f"Global: {constraint.name}")
            except Exception as e:
                global_violations.append(f"Global: {constraint.name} - {str(e)}")

        # Check step-specific constraints
        step_valid, step_violations = step.validate_constraints(step_context)
        all_violations = global_violations + step_violations

        if all_violations:
            if self.strict_mode:
                return StepResult(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    error=f"Constraint violations: {all_violations}",
                    duration=time.time() - start_time,
                    constraints_satisfied=False,
                    constraint_violations=all_violations,
                    trace_entry=self._create_trace_entry(step, step_context, None, all_violations),
                )
            else:
                logger.warning(f"Step {step.step_id} has constraints violations: {all_violations}")

        # Phase 2: Pre-conditions
        for pre_condition in step.pre_conditions:
            try:
                if not pre_condition(step_context):
                    return StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=f"Pre-condition failed: {pre_condition.__name__}",
                        duration=time.time() - start_time,
                        constraints_satisfied=len(all_violations) == 0,
                        constraint_violations=all_violations,
                        trace_entry=self._create_trace_entry(step, step_context, None, all_violations),
                    )
            except Exception as e:
                return StepResult(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    error=f"Pre-condition error: {str(e)}",
                    duration=time.time() - start_time,
                    constraints_satisfied=len(all_violations) == 0,
                    constraint_violations=all_violations,
                    trace_entry=self._create_trace_entry(step, step_context, None, all_violations),
                )

        # Phase 3: Execution
        step_context.status = StepStatus.EXECUTING
        output = None
        execution_error = None

        try:
            if asyncio.iscoroutinefunction(step.execute_fn):
                output = await step.execute_fn(step_context)
            else:
                output = step.execute_fn(step_context)
        except Exception as e:
            execution_error = str(e)
            logger.error(f"Step {step.step_id} execution error: {e}")

        # Phase 4: Post-conditions
        if output is not None:
            for post_condition in step.post_conditions:
                try:
                    if not post_condition(step_context, output):
                        execution_error = f"Post-condition failed: {post_condition.__name__}"
                        break
                except Exception as e:
                    execution_error = f"Post-condition error: {str(e)}"
                    break

        # Determine status
        if execution_error:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=execution_error,
                duration=time.time() - start_time,
                constraints_satisfied=len(all_violations) == 0,
                constraint_violations=all_violations,
                trace_entry=self._create_trace_entry(step, step_context, None, all_violations),
            )

        return StepResult(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            output=output,
            duration=time.time() - start_time,
            constraints_satisfied=len(all_violations) == 0,
            constraint_violations=all_violations,
            trace_entry=self._create_trace_entry(step, step_context, output, all_violations),
        )

    async def _attempt_rollback(self, failed_step: Step, context: StepContext) -> bool:
        """Attempt to rollback after a constraint violation"""
        if not self.enable_rollback:
            return False

        if len(self._rollback_history) >= self.max_rollbacks:
            logger.error(f"Max rollbacks ({self.max_rollbacks}) reached")
            return False

        logger.info(f"Attempting rollback for failed step {failed_step.step_id}")

        # Find the rollback point
        rollback_target = None
        for i, step in enumerate(self.plan.steps):
            if step.step_id == failed_step.step_id:
                # Rollback to the state before this step
                if i > 0:
                    rollback_target = self.plan.steps[i - 1]
                break

        if rollback_target and rollback_target.rollback_fn:
            try:
                await rollback_target.rollback_fn(context)
                self._rollback_history.append({
                    "failed_step": failed_step.step_id,
                    "rollback_target": rollback_target.step_id,
                    "timestamp": time.time(),
                })
                self._execution_trace.rollback_count += 1
                logger.info(f"Rollback successful to step {rollback_target.step_id}")
                return True
            except Exception as e:
                logger.error(f"Rollback failed: {e}")
                return False

        return False

    def _create_trace_entry(
        self,
        step: Step,
        context: StepContext,
        output: Any,
        violations: List[str],
    ) -> Dict[str, Any]:
        """Create a trace entry for the step execution"""
        return {
            "step_id": step.step_id,
            "step_name": step.name,
            "timestamp": time.time(),
            "status": context.status.value if hasattr(context.status, 'value') else str(context.status),
            "output_preview": str(output)[:200] if output else None,
            "constraint_violations": violations,
            "has_violations": len(violations) > 0,
        }

    def get_trace(self) -> Optional[ExecutionTrace]:
        """Get the execution trace"""
        return self._execution_trace

    def get_step_outputs(self) -> Dict[str, Any]:
        """Get outputs from all completed steps"""
        return self._step_outputs.copy()
