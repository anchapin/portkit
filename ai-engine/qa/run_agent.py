import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class StepRubric:
    def __init__(
        self,
        required_actions: Set[str],
        forbidden_actions: Set[str] = None,
        min_duration_ms: int = 0,
        max_retries: int = 3,
        rollback_on_failure: bool = True,
    ):
        self.required_actions = required_actions
        self.forbidden_actions = forbidden_actions or set()
        self.min_duration_ms = min_duration_ms
        self.max_retries = max_retries
        self.rollback_on_failure = rollback_on_failure

    def validate_actions(self, actions: Set[str]) -> tuple[bool, List[str]]:
        errors = []
        missing = self.required_actions - actions
        if missing:
            errors.append(f"Missing required actions: {missing}")
        forbidden = actions & self.forbidden_actions
        if forbidden:
            errors.append(f"Performed forbidden actions: {forbidden}")
        return len(errors) == 0, errors


@dataclass
class StepMetrics:
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    retry_count: int = 0
    actions_performed: Set[str] = field(default_factory=set)

    def start(self):
        self.start_time = datetime.now()

    def stop(self):
        self.end_time = datetime.now()
        if self.start_time:
            self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "actions_performed": list(self.actions_performed),
        }


@dataclass
class ConversionStep:
    step_id: str
    description: str
    required_actions: Set[str]
    validation_fn: Optional[Callable[["StepContext"], bool]] = None
    next_steps: List[str] = field(default_factory=list)
    rubric: Optional[StepRubric] = None
    dependencies: List[str] = field(default_factory=list)
    agent_type: str = "general"
    timeout_seconds: int = 60

    def can_execute(self, completed_steps: Set[str]) -> bool:
        return all(dep in completed_steps for dep in self.dependencies)


@dataclass
class StepContext:
    step: ConversionStep
    state: Dict[str, Any]
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metrics: StepMetrics = field(default_factory=StepMetrics)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step.step_id,
            "description": self.step.description,
            "state": self.state,
            "artifacts": self.artifacts,
            "metrics": self.metrics.to_dict(),
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class StepResult:
    step_id: str
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_ms: int = 0
    retry_count: int = 0
    rollback_performed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "success": self.success,
            "output": self.output,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "rollback_performed": self.rollback_performed,
        }


class ConversionDAG:
    def __init__(self):
        self._steps: Dict[str, ConversionStep] = {}
        self._step_order: List[str] = []

    def add_step(self, step: ConversionStep):
        self._steps[step.step_id] = step
        self._recompute_order()

    def _recompute_order(self):
        visited = set()
        order = []

        def visit(step_id: str):
            if step_id in visited:
                return
            visited.add(step_id)
            step = self._steps.get(step_id)
            if step:
                for dep in step.dependencies:
                    if dep in self._steps:
                        visit(dep)
                order.append(step_id)

        for step_id in self._steps:
            visit(step_id)

        self._step_order = order

    def get_step(self, step_id: str) -> Optional[ConversionStep]:
        return self._steps.get(step_id)

    def get_executable_steps(self, completed: Set[str]) -> List[ConversionStep]:
        return [
            self._steps[step_id]
            for step_id in self._step_order
            if step_id in self._steps
            and self._steps[step_id].can_execute(completed)
            and step_id not in completed
        ]

    def validate(self) -> tuple[bool, List[str]]:
        errors = []

        for step_id, step in self._steps.items():
            for dep in step.dependencies:
                if dep not in self._steps:
                    errors.append(f"Step '{step_id}' depends on unknown step '{dep}'")

        if not self._has_dag_integrity():
            errors.append("DAG contains cycles or invalid dependencies")

        return len(errors) == 0, errors

    def _has_dag_integrity(self) -> bool:
        visited = set()
        rec_stack = set()

        def has_cycle(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)
            step = self._steps.get(step_id)
            if step:
                for dep in step.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.remove(step_id)
            return False

        for step_id in self._steps:
            if step_id not in visited:
                if has_cycle(step_id):
                    return False
        return True

    def get_all_steps(self) -> List[ConversionStep]:
        return [self._steps[step_id] for step_id in self._step_order if step_id in self._steps]

    @classmethod
    def create_java_to_bedrock_dag(cls) -> "ConversionDAG":
        dag = cls()

        dag.add_step(
            ConversionStep(
                step_id="extract",
                description="Parse Java AST and extract components",
                required_actions={
                    "parse_ast",
                    "extract_imports",
                    "extract_classes",
                    "extract_methods",
                },
                dependencies=[],
                agent_type="java_analyzer",
                rubric=StepRubric(
                    required_actions={
                        "parse_ast",
                        "extract_imports",
                        "extract_classes",
                        "extract_methods",
                    },
                    forbidden_actions={"generate_code", "validate_schema"},
                    min_duration_ms=100,
                ),
            )
        )

        dag.add_step(
            ConversionStep(
                step_id="map",
                description="Map Java classes to Bedrock equivalents",
                required_actions={"identify_mappings", "map_classes", "map_methods", "map_events"},
                dependencies=["extract"],
                agent_type="translator",
                rubric=StepRubric(
                    required_actions={
                        "identify_mappings",
                        "map_classes",
                        "map_methods",
                        "map_events",
                    },
                    forbidden_actions={"validate_schema", "generate_bedrock_json"},
                    min_duration_ms=100,
                ),
            )
        )

        dag.add_step(
            ConversionStep(
                step_id="generate",
                description="Generate Bedrock JSON and Script API code",
                required_actions={
                    "generate_json",
                    "generate_scripts",
                    "generate_manifest",
                    "generate_component_files",
                },
                dependencies=["map"],
                agent_type="translator",
                rubric=StepRubric(
                    required_actions={
                        "generate_json",
                        "generate_scripts",
                        "generate_manifest",
                        "generate_component_files",
                    },
                    forbidden_actions={"validate_schema", "repair_errors"},
                    min_duration_ms=100,
                ),
            )
        )

        dag.add_step(
            ConversionStep(
                step_id="validate",
                description="Run schema and semantic validation",
                required_actions={
                    "validate_json_schema",
                    "validate_scripts",
                    "validate_semantics",
                    "check_api_compatibility",
                },
                dependencies=["generate"],
                agent_type="reviewer",
                rubric=StepRubric(
                    required_actions={
                        "validate_json_schema",
                        "validate_scripts",
                        "validate_semantics",
                        "check_api_compatibility",
                    },
                    forbidden_actions={"modify_code", "skip_validation"},
                    min_duration_ms=50,
                ),
            )
        )

        dag.add_step(
            ConversionStep(
                step_id="repair",
                description="Fix any detected issues",
                required_actions={"identify_issues", "apply_fixes", "re_validate", "verify_fixes"},
                dependencies=["validate"],
                agent_type="fixer",
                rubric=StepRubric(
                    required_actions={
                        "identify_issues",
                        "apply_fixes",
                        "re_validate",
                        "verify_fixes",
                    },
                    forbidden_actions={"skip_validation"},
                    min_duration_ms=50,
                    max_retries=2,
                ),
            )
        )

        return dag


class StepValidator:
    def __init__(self, dag: ConversionDAG):
        self.dag = dag

    def validate_step_execution(
        self, step_id: str, actions: Set[str], duration_ms: int
    ) -> tuple[bool, List[str]]:
        step = self.dag.get_step(step_id)
        if not step:
            return False, [f"Unknown step: {step_id}"]

        if not step.rubric:
            return True, []

        rubric_valid, errors = step.rubric.validate_actions(actions)

        if step.rubric.min_duration_ms > 0 and duration_ms < step.rubric.min_duration_ms:
            errors.append(
                f"Step completed too quickly ({duration_ms}ms < {step.rubric.min_duration_ms}ms)"
            )

        is_valid = rubric_valid and len(errors) == 0
        return is_valid, errors

    def validate_dag_completion(self, completed_steps: Set[str]) -> tuple[bool, List[str]]:
        errors = []
        all_steps = set(self.dag._steps.keys())

        if completed_steps != all_steps:
            missing = all_steps - completed_steps
            if missing:
                errors.append(f"Incomplete conversion. Missing steps: {missing}")

        return len(errors) == 0, errors


class ExecutionTrace:
    def __init__(self):
        self.entries: List[Dict[str, Any]] = []
        self.step_results: Dict[str, StepResult] = {}

    def record_action(self, step_id: str, action: str, timestamp: datetime = None):
        self.entries.append(
            {
                "type": "action",
                "step_id": step_id,
                "action": action,
                "timestamp": (timestamp or datetime.now()).isoformat(),
            }
        )

    def record_state_change(self, step_id: str, old_state: Dict, new_state: Dict):
        self.entries.append(
            {
                "type": "state_change",
                "step_id": step_id,
                "old_state": old_state,
                "new_state": new_state,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def record_result(self, result: StepResult):
        self.step_results[result.step_id] = result
        self.entries.append(
            {
                "type": "result",
                "step_id": result.step_id,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def can_verify_step_order(self, expected_order: List[str]) -> bool:
        actual_order = [
            e["step_id"]
            for e in self.entries
            if e["type"] == "result" and e["step_id"] in expected_order
        ]
        return actual_order == expected_order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": self.entries,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "total_steps": len(self.step_results),
            "successful_steps": sum(1 for v in self.step_results.values() if v.success),
        }


class ConstraintGuardedExecutor:
    def __init__(
        self,
        dag: ConversionDAG,
        agent_registry: Dict[str, Callable],
        state: Dict[str, Any] = None,
        enable_rollback: bool = True,
    ):
        self.dag = dag
        self.agent_registry = agent_registry
        self.state = state or {}
        self.enable_rollback = enable_rollback
        self.validator = StepValidator(dag)
        self.trace = ExecutionTrace()
        self._snapshots: Dict[str, Dict[str, Any]] = {}

    async def execute_step(
        self,
        step: ConversionStep,
        context: StepContext,
        dry_run: bool = False,
    ) -> StepResult:
        retry_count = 0
        max_retries = step.rubric.max_retries if step.rubric else 1

        while retry_count < max_retries:
            step_start_time = time.time()
            context.metrics.start()
            context.errors = []
            context.metrics.actions_performed = set()

            self.trace.record_action(step.step_id, "step_started")
            logger.info("Executing step", step_id=step.step_id, description=step.description)

            if dry_run:
                context.metrics.stop()
                return StepResult(
                    step_id=step.step_id,
                    success=True,
                    output={"dry_run": True, "description": step.description},
                    duration_ms=context.metrics.duration_ms,
                )

            if retry_count == 0 and step.rubric and self.enable_rollback:
                self._take_snapshot(step.step_id)

            try:
                agent = self.agent_registry.get(step.agent_type)
                if not agent:
                    raise ValueError(f"No agent registered for type: {step.agent_type}")

                if asyncio.iscoroutinefunction(agent):
                    output = await agent(context)
                else:
                    output = agent(context)

                context.metrics.stop()
                actions_performed = set(context.metrics.actions_performed)
                duration_ms = context.metrics.duration_ms

                if step.rubric:
                    is_valid, errors = self.validator.validate_step_execution(
                        step.step_id,
                        actions_performed,
                        duration_ms,
                    )
                    if not is_valid:
                        context.errors.extend(errors)
                        raise ValueError(f"Step validation failed: {errors}")

                result = StepResult(
                    step_id=step.step_id,
                    success=True,
                    output=output or {},
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                )

                self.state.update(result.output)
                self.trace.record_result(result)
                logger.info("Step completed", step_id=step.step_id, duration_ms=result.duration_ms)
                return result

            except Exception as e:
                context.metrics.stop()
                duration_ms = context.metrics.duration_ms
                retry_count += 1
                context.metrics.retry_count = retry_count
                context.errors.append(str(e))
                logger.warning(
                    "Step failed, retrying",
                    step_id=step.step_id,
                    retry=retry_count,
                    max_retries=max_retries,
                    error=str(e),
                )

                if retry_count >= max_retries:
                    result = StepResult(
                        step_id=step.step_id,
                        success=False,
                        errors=[str(e)],
                        duration_ms=duration_ms,
                        retry_count=retry_count,
                        rollback_performed=False,
                    )

                    if self.enable_rollback and step.rubric and step.rubric.rollback_on_failure:
                        result.rollback_performed = self._rollback(step.step_id)
                        logger.info(
                            "Step failed, rollback performed",
                            step_id=step.step_id,
                            rollback=result.rollback_performed,
                        )

                    self.trace.record_result(result)
                    return result

        context.metrics.stop()
        return StepResult(
            step_id=step.step_id,
            success=False,
            errors=["Max retries exceeded"],
            duration_ms=context.metrics.duration_ms,
            retry_count=retry_count,
        )

    def _take_snapshot(self, step_id: str):
        self._snapshots[step_id] = {
            "state": dict(self.state),
            "timestamp": datetime.now().isoformat(),
        }

    def _rollback(self, step_id: str) -> bool:
        if step_id not in self._snapshots:
            logger.warning("No snapshot available for rollback", step_id=step_id)
            return False

        snapshot = self._snapshots[step_id]
        self.state.clear()
        self.state.update(snapshot["state"])
        self.trace.record_state_change(step_id, snapshot, self.state)
        logger.info("Rollback successful", step_id=step_id)
        return True

    def get_next_available_steps(self, completed: Set[str]) -> List[ConversionStep]:
        return self.dag.get_executable_steps(completed)


class RunAgent:
    def __init__(
        self,
        dag: Optional[ConversionDAG] = None,
        enable_rollback: bool = True,
        strict_mode: bool = True,
    ):
        self.dag = dag or ConversionDAG.create_java_to_bedrock_dag()
        self.enable_rollback = enable_rollback
        self.strict_mode = strict_mode
        self.executor: Optional[ConstraintGuardedExecutor] = None
        self._agent_registry: Dict[str, Callable] = {}

    def register_agent(self, agent_type: str, agent_fn: Callable):
        self._agent_registry[agent_type] = agent_fn

    async def execute_conversion(
        self,
        initial_state: Dict[str, Any],
        max_steps: Optional[int] = None,
        start_from_step: Optional[str] = None,
    ) -> tuple[bool, Dict[str, Any]]:
        is_valid, errors = self.dag.validate()
        if not is_valid:
            logger.error("DAG validation failed", errors=errors)
            return False, {"validation_errors": errors}

        self.executor = ConstraintGuardedExecutor(
            dag=self.dag,
            agent_registry=self._agent_registry,
            state=initial_state,
            enable_rollback=self.enable_rollback,
        )

        completed_steps: Set[str] = set()
        step_history: List[StepResult] = []

        if start_from_step:
            for step_id in self.dag._step_order:
                if step_id == start_from_step:
                    break
                completed_steps.add(step_id)

        max_steps = max_steps or len(self.dag._steps)

        for _ in range(max_steps):
            available = self.executor.get_next_available_steps(completed_steps)
            if not available:
                break

            step = available[0]
            context = StepContext(
                step=step,
                state=self.executor.state,
            )

            result = await self.executor.execute_step(step, context)

            step_history.append(result)
            if result.success:
                completed_steps.add(step.step_id)
                self.executor.state.update(result.output)
            else:
                if self.strict_mode:
                    logger.error(
                        "Conversion failed at step, strict mode enabled",
                        step_id=step.step_id,
                        errors=result.errors,
                    )
                    return False, {
                        "failed_step": step.step_id,
                        "errors": result.errors,
                        "completed_steps": list(completed_steps),
                        "trace": self.executor.trace.to_dict(),
                    }
                else:
                    completed_steps.add(step.step_id)

        is_complete, completion_errors = self.validator.validate_dag_completion(completed_steps)

        return is_complete, {
            "completed_steps": list(completed_steps),
            "step_results": [r.to_dict() for r in step_history],
            "final_state": self.executor.state,
            "trace": self.executor.trace.to_dict(),
            "completion_errors": completion_errors,
        }

    @property
    def validator(self) -> StepValidator:
        return StepValidator(self.dag)

    def get_execution_trace(self) -> Optional[ExecutionTrace]:
        return self.executor.trace if self.executor else None
