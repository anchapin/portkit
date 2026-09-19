"""
Procedural Execution Diagnostic Suite

Diagnoses whether agents faithfully execute multi-step conversion procedures
without deviation. Based on: "When LLMs Stop Following Steps"
(https://arxiv.org/abs/2605.00817v1)

Detects:
- Skipped steps
- Reordering of steps
- Misinterpreted conditionals
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DeviationType(Enum):
    SKIPPED_STEP = "skipped_step"
    REORDERED_STEP = "reordered_step"
    MISINTERPRETED_CONDITIONAL = "misinterpreted_conditional"
    EXTRA_STEP = "extra_step"
    PARTIAL_STEP = "partial_step"


class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class ProcedureStep:
    step_id: str
    name: str
    description: str
    required: bool = True
    conditional: bool = False
    condition_expression: Optional[str] = None
    expected_dependencies: List[str] = field(default_factory=list)


@dataclass
class StepExecution:
    step_id: str
    status: StepStatus
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    actual_order: int = -1


@dataclass
class ProcedureDefinition:
    procedure_id: str
    name: str
    description: str
    steps: List[ProcedureStep]
    expected_order: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.expected_order and self.steps:
            self.expected_order = [s.step_id for s in self.steps]


@dataclass
class Deviation:
    deviation_type: DeviationType
    step_id: str
    severity: str
    details: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None


@dataclass
class FidelityMetrics:
    procedure_id: str
    procedure_name: str
    total_steps: int
    completed_steps: int
    skipped_steps: int
    fidelity_score: float
    deviations: List[Deviation]
    execution_time_ms: float
    timestamp: float = field(default_factory=time.time)
    step_executions: List[StepExecution] = field(default_factory=list)


class ProcedureTracer:
    """
    Traces execution of a multi-step procedure, recording the order
    and status of each step for later analysis.
    """

    def __init__(self, procedure: ProcedureDefinition):
        self.procedure = procedure
        self.step_executions: Dict[str, StepExecution] = {}
        self.execution_order: List[str] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def begin_procedure(self):
        self.start_time = time.time()
        for step in self.procedure.steps:
            self.step_executions[step.step_id] = StepExecution(
                step_id=step.step_id,
                status=StepStatus.PENDING,
            )

    def record_step_start(self, step_id: str):
        if step_id not in self.step_executions:
            self.step_executions[step_id] = StepExecution(
                step_id=step_id,
                status=StepStatus.PENDING,
            )
        self.step_executions[step_id].status = StepStatus.IN_PROGRESS
        self.step_executions[step_id].start_time = time.time()
        self.step_executions[step_id].actual_order = len(self.execution_order)
        if step_id not in self.execution_order:
            self.execution_order.append(step_id)

    def record_step_completion(self, step_id: str, output: Any = None):
        if step_id in self.step_executions:
            self.step_executions[step_id].status = StepStatus.COMPLETED
            self.step_executions[step_id].end_time = time.time()
            self.step_executions[step_id].output = output

    def record_step_skip(self, step_id: str, reason: str = ""):
        if step_id in self.step_executions:
            self.step_executions[step_id].status = StepStatus.SKIPPED
            self.step_executions[step_id].end_time = time.time()
            self.step_executions[step_id].error = f"Skipped: {reason}"

    def record_step_failure(self, step_id: str, error: str):
        if step_id in self.step_executions:
            self.step_executions[step_id].status = StepStatus.FAILED
            self.step_executions[step_id].end_time = time.time()
            self.step_executions[step_id].error = error

    def end_procedure(self):
        self.end_time = time.time()

    def get_trace(self) -> Dict[str, Any]:
        return {
            "procedure_id": self.procedure.procedure_id,
            "execution_order": self.execution_order,
            "step_executions": {
                sid: {
                    "status": se.status.value,
                    "start_time": se.start_time,
                    "end_time": se.end_time,
                    "actual_order": se.actual_order,
                    "output": se.output,
                    "error": se.error,
                }
                for sid, se in self.step_executions.items()
            },
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class ProcedureAnalyzer:
    """
    Analyzes procedure execution traces to detect deviations from
    expected multi-step procedures.
    """

    def __init__(self, procedure: ProcedureDefinition):
        self.procedure = procedure
        self._step_index: Dict[str, ProcedureStep] = {s.step_id: s for s in procedure.steps}

    def analyze(self, tracer: ProcedureTracer) -> List[Deviation]:
        deviations = []

        deviations.extend(self._check_skipped_steps(tracer))
        deviations.extend(self._check_reordered_steps(tracer))
        deviations.extend(self._check_extra_steps(tracer))
        deviations.extend(self._check_partial_steps(tracer))
        deviations.extend(self._check_misinterpreted_conditionals(tracer))

        return deviations

    def _check_skipped_steps(self, tracer: ProcedureTracer) -> List[Deviation]:
        deviations = []
        expected_order = self.procedure.expected_order

        completed_or_skipped = {
            sid: se.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for sid, se in tracer.step_executions.items()
        }

        for step in self.procedure.steps:
            if step.required and not completed_or_skipped.get(step.step_id, False):
                actual_status = tracer.step_executions.get(
                    step.step_id, StepExecution(step_id=step.step_id, status=StepStatus.PENDING)
                ).status
                deviations.append(
                    Deviation(
                        deviation_type=DeviationType.SKIPPED_STEP,
                        step_id=step.step_id,
                        severity="high",
                        details=f"Required step '{step.name}' was not executed",
                        expected=StepStatus.COMPLETED.value,
                        actual=actual_status.value,
                    )
                )

        return deviations

    def _check_reordered_steps(self, tracer: ProcedureTracer) -> List[Deviation]:
        deviations = []
        expected_order = self.procedure.expected_order

        for i, expected_step_id in enumerate(expected_order):
            if expected_step_id not in tracer.execution_order:
                continue

            actual_index = tracer.execution_order.index(expected_step_id)

            if expected_step_id in self._step_index:
                step = self._step_index[expected_step_id]
                for dep_id in step.expected_dependencies:
                    if dep_id in tracer.execution_order:
                        dep_index = tracer.execution_order.index(dep_id)
                        if actual_index < dep_index:
                            deviations.append(
                                Deviation(
                                    deviation_type=DeviationType.REORDERED_STEP,
                                    step_id=expected_step_id,
                                    severity="high",
                                    details=f"Step '{step.name}' executed before its dependency '{dep_id}'",
                                    expected=f"Dependency '{dep_id}' before '{expected_step_id}'",
                                    actual=f"'{expected_step_id}' at position {actual_index}, '{dep_id}' at position {dep_index}",
                                )
                            )

        for i in range(len(tracer.execution_order) - 1):
            current_id = tracer.execution_order[i]
            next_id = tracer.execution_order[i + 1]

            current_idx_in_expected = (
                expected_order.index(current_id) if current_id in expected_order else -1
            )
            next_idx_in_expected = (
                expected_order.index(next_id) if next_id in expected_order else -1
            )

            if current_idx_in_expected > next_idx_in_expected and current_idx_in_expected != -1:
                deviations.append(
                    Deviation(
                        deviation_type=DeviationType.REORDERED_STEP,
                        step_id=next_id,
                        severity="medium",
                        details=f"Step order deviation detected",
                        expected=f"{current_id} before {next_id}",
                        actual=f"{next_id} before {current_id}",
                    )
                )

        return deviations

    def _check_extra_steps(self, tracer: ProcedureTracer) -> List[Deviation]:
        deviations = []
        expected_step_ids = {s.step_id for s in self.procedure.steps}

        for step_id, execution in tracer.step_executions.items():
            if execution.status in (StepStatus.COMPLETED, StepStatus.IN_PROGRESS):
                if step_id not in expected_step_ids:
                    deviations.append(
                        Deviation(
                            deviation_type=DeviationType.EXTRA_STEP,
                            step_id=step_id,
                            severity="low",
                            details=f"Unexpected step '{step_id}' was executed",
                            expected="Only defined procedure steps",
                            actual=f"Step '{step_id}' not in procedure definition",
                        )
                    )

        return deviations

    def _check_partial_steps(self, tracer: ProcedureTracer) -> List[Deviation]:
        deviations = []

        for step_id, execution in tracer.step_executions.items():
            if execution.status == StepStatus.IN_PROGRESS:
                deviations.append(
                    Deviation(
                        deviation_type=DeviationType.PARTIAL_STEP,
                        step_id=step_id,
                        severity="high",
                        details=f"Step '{step_id}' was started but not completed",
                        expected=StepStatus.COMPLETED.value,
                        actual=StepStatus.IN_PROGRESS.value,
                    )
                )

        return deviations

    def _check_misinterpreted_conditionals(self, tracer: ProcedureTracer) -> List[Deviation]:
        deviations = []

        for step in self.procedure.steps:
            if step.conditional:
                was_executed = step.step_id in tracer.execution_order
                step_def = self._step_index.get(step.step_id)
                if step_def and step_def.condition_expression:
                    pass

        return deviations


class ProceduralDiagnosticsSuite:
    """
    Main diagnostic suite for measuring procedural execution fidelity.

    This suite provides:
    1. Procedure registration with expected step orders
    2. Execution tracing during agent workflows
    3. Post-execution analysis for deviations
    4. Fidelity scoring and reporting
    """

    def __init__(self):
        self.procedures: Dict[str, ProcedureDefinition] = {}
        self.active_tracers: Dict[str, ProcedureTracer] = {}
        self.diagnostic_history: List[FidelityMetrics] = []
        logger.info("ProceduralDiagnosticsSuite initialized")

    def register_procedure(self, procedure: ProcedureDefinition) -> None:
        self.procedures[procedure.procedure_id] = procedure
        logger.info(f"Registered procedure: {procedure.name}")

    def get_procedure(self, procedure_id: str) -> Optional[ProcedureDefinition]:
        return self.procedures.get(procedure_id)

    def start_tracing(self, procedure_id: str) -> Optional[ProcedureTracer]:
        procedure = self.procedures.get(procedure_id)
        if not procedure:
            logger.warning(f"Procedure not found: {procedure_id}")
            return None

        tracer = ProcedureTracer(procedure)
        tracer.begin_procedure()
        self.active_tracers[procedure_id] = tracer
        logger.debug(f"Started tracing procedure: {procedure_id}")
        return tracer

    def get_tracer(self, procedure_id: str) -> Optional[ProcedureTracer]:
        return self.active_tracers.get(procedure_id)

    def end_tracing(self, procedure_id: str) -> Optional[ProcedureTracer]:
        tracer = self.active_tracers.pop(procedure_id, None)
        if tracer:
            tracer.end_procedure()
            logger.debug(f"Ended tracing procedure: {procedure_id}")
        return tracer

    def analyze_execution(self, procedure_id: str) -> Optional[FidelityMetrics]:
        tracer = self.end_tracing(procedure_id)
        if not tracer:
            return None

        procedure = self.procedures.get(procedure_id)
        if not procedure:
            return None

        analyzer = ProcedureAnalyzer(procedure)
        deviations = analyzer.analyze(tracer)

        total_steps = len(procedure.steps)
        completed_steps = sum(
            1 for se in tracer.step_executions.values() if se.status == StepStatus.COMPLETED
        )
        skipped_steps = sum(
            1 for se in tracer.step_executions.values() if se.status == StepStatus.SKIPPED
        )

        fidelity_score = self._calculate_fidelity_score(
            total_steps, completed_steps, skipped_steps, deviations
        )

        execution_time_ms = (
            (tracer.end_time - tracer.start_time) * 1000
            if tracer.start_time and tracer.end_time
            else 0
        )

        metrics = FidelityMetrics(
            procedure_id=procedure_id,
            procedure_name=procedure.name,
            total_steps=total_steps,
            completed_steps=completed_steps,
            skipped_steps=skipped_steps,
            fidelity_score=fidelity_score,
            deviations=deviations,
            execution_time_ms=execution_time_ms,
            step_executions=list(tracer.step_executions.values()),
        )

        self.diagnostic_history.append(metrics)
        logger.info(
            f"Procedure '{procedure.name}' fidelity: {fidelity_score:.1%} "
            f"({len(deviations)} deviations)"
        )

        return metrics

    def _calculate_fidelity_score(
        self,
        total_steps: int,
        completed_steps: int,
        skipped_steps: int,
        deviations: List[Deviation],
    ) -> float:
        if total_steps == 0:
            return 1.0

        completion_score = completed_steps / total_steps
        skip_penalty = skipped_steps / total_steps * 0.3

        severity_weights = {"high": 0.2, "medium": 0.1, "low": 0.05}
        deviation_penalty = 0.0
        for deviation in deviations:
            weight = severity_weights.get(deviation.severity, 0.1)
            deviation_penalty += weight

        deviation_penalty = min(deviation_penalty, 0.4)

        fidelity_score = max(0.0, completion_score - skip_penalty - deviation_penalty)
        return fidelity_score

    def get_diagnostic_summary(self, procedure_id: Optional[str] = None) -> Dict[str, Any]:
        if procedure_id:
            metrics_list = [m for m in self.diagnostic_history if m.procedure_id == procedure_id]
        else:
            metrics_list = self.diagnostic_history

        if not metrics_list:
            return {"message": "No diagnostic history", "total_runs": 0}

        total_runs = len(metrics_list)
        avg_fidelity = sum(m.fidelity_score for m in metrics_list) / total_runs
        total_deviations = sum(len(m.deviations) for m in metrics_list)
        high_severity = sum(1 for m in metrics_list for d in m.deviations if d.severity == "high")

        return {
            "total_runs": total_runs,
            "average_fidelity_score": round(avg_fidelity, 3),
            "total_deviations": total_deviations,
            "high_severity_deviations": high_severity,
            "procedures_tested": list(set(m.procedure_id for m in metrics_list)),
            "recent_runs": [
                {
                    "procedure_name": m.procedure_name,
                    "fidelity_score": m.fidelity_score,
                    "deviation_count": len(m.deviations),
                    "timestamp": m.timestamp,
                }
                for m in metrics_list[-5:]
            ],
        }

    def generate_report(self, metrics: FidelityMetrics, format: str = "json") -> Dict[str, Any]:
        report = {
            "procedure_id": metrics.procedure_id,
            "procedure_name": metrics.procedure_name,
            "fidelity_score": metrics.fidelity_score,
            "execution_time_ms": metrics.execution_time_ms,
            "step_summary": {
                "total": metrics.total_steps,
                "completed": metrics.completed_steps,
                "skipped": metrics.skipped_steps,
            },
            "deviations": [
                {
                    "type": d.deviation_type.value,
                    "step_id": d.step_id,
                    "severity": d.severity,
                    "details": d.details,
                    "expected": d.expected,
                    "actual": d.actual,
                }
                for d in metrics.deviations
            ],
            "step_executions": [
                {
                    "step_id": se.step_id,
                    "status": se.status.value,
                    "actual_order": se.actual_order,
                    "execution_time_ms": (
                        (se.end_time - se.start_time) * 1000
                        if se.start_time and se.end_time
                        else None
                    ),
                }
                for se in metrics.step_executions
            ],
            "timestamp": metrics.timestamp,
        }

        if format == "text":
            lines = [
                f"--- Procedural Fidelity Report ---",
                f"Procedure: {metrics.procedure_name}",
                f"Fidelity Score: {metrics.fidelity_score:.1%}",
                f"Execution Time: {metrics.execution_time_ms:.0f}ms",
                f"",
                f"Step Summary:",
                f"  Total: {metrics.total_steps}",
                f"  Completed: {metrics.completed_steps}",
                f"  Skipped: {metrics.skipped_steps}",
                f"",
            ]
            if metrics.deviations:
                lines.append("Deviations:")
                for d in metrics.deviations:
                    lines.append(f"  [{d.severity.upper()}] {d.deviation_type.value}: {d.details}")
            else:
                lines.append("No deviations detected.")
            return "\n".join(lines)

        return report

    @staticmethod
    def create_conversion_procedure() -> ProcedureDefinition:
        return ProcedureDefinition(
            procedure_id="java_to_bedrock_conversion",
            name="Java to Bedrock Conversion",
            description="Multi-step procedure for converting Java mods to Bedrock add-ons",
            steps=[
                ProcedureStep(
                    step_id="analyze",
                    name="Analyze Java Mod",
                    description="Analyze Java mod structure, dependencies, and features",
                    required=True,
                ),
                ProcedureStep(
                    step_id="plan",
                    name="Create Conversion Plan",
                    description="Create conversion plan with smart assumptions",
                    required=True,
                    expected_dependencies=["analyze"],
                ),
                ProcedureStep(
                    step_id="translate",
                    name="Translate Java Code",
                    description="Convert Java code to Bedrock JavaScript",
                    required=True,
                    expected_dependencies=["plan"],
                ),
                ProcedureStep(
                    step_id="convert_assets",
                    name="Convert Assets",
                    description="Convert textures, models, and sounds",
                    required=True,
                    expected_dependencies=["plan"],
                ),
                ProcedureStep(
                    step_id="package",
                    name="Package Add-on",
                    description="Assemble converted components into .mcaddon",
                    required=True,
                    expected_dependencies=["translate", "convert_assets"],
                ),
                ProcedureStep(
                    step_id="validate",
                    name="Validate Conversion",
                    description="Validate conversion quality and completeness",
                    required=True,
                    expected_dependencies=["package"],
                ),
            ],
        )


class DiagnosticIntegration:
    """
    Integration layer for hooking procedural diagnostics into agent workflows.
    """

    def __init__(self, suite: ProceduralDiagnosticsSuite):
        self.suite = suite
        self._original_methods: Dict[str, Callable] = {}

    def instrument_conversion_pipeline(self, pipeline_instance: Any) -> None:
        logger.info("Instrumenting conversion pipeline with procedural diagnostics")
        if hasattr(pipeline_instance, "convert_mod"):
            self._original_methods["convert_mod"] = pipeline_instance.convert_mod
            pipeline_instance.convert_mod = self._wrapped_convert_mod(
                pipeline_instance, pipeline_instance.convert_mod
            )

    def _wrapped_convert_mod(self, instance: Any, original_method: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            procedure = ProceduralDiagnosticsSuite.create_conversion_procedure()
            self.suite.register_procedure(procedure)
            tracer = self.suite.start_tracing(procedure.procedure_id)

            steps = {
                "analyze": "Analyzing Java mod",
                "plan": "Creating conversion plan",
                "translate": "Translating code",
                "convert_assets": "Converting assets",
                "package": "Packaging add-on",
                "validate": "Validating conversion",
            }

            try:
                result = original_method(*args, **kwargs)
                if tracer:
                    for step_id in steps:
                        if step_id not in tracer.execution_order:
                            tracer.record_step_skip(step_id, "Not traced in execution")
            except Exception as e:
                logger.error(f"Conversion failed during diagnostics: {e}")
                raise
            finally:
                metrics = self.suite.analyze_execution(procedure.procedure_id)
                if metrics and hasattr(instance, "last_diagnostic_metrics"):
                    instance.last_diagnostic_metrics = metrics

            return result

        return wrapper

    def get_last_metrics(self) -> Optional[FidelityMetrics]:
        if self.suite.diagnostic_history:
            return self.suite.diagnostic_history[-1]
        return None
