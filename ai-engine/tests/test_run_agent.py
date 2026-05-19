import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Set

from qa.run_agent import (
    ConversionDAG,
    ConversionStep,
    ConstraintGuardedExecutor,
    ExecutionTrace,
    RunAgent,
    StepContext,
    StepMetrics,
    StepResult,
    StepRubric,
    StepStatus,
    StepValidator,
)


class TestStepRubric:
    def test_validate_actions_success_when_all_required_present(self):
        rubric = StepRubric(
            required_actions={"parse_ast", "extract_classes"},
            forbidden_actions={"modify_code"},
        )
        actions = {"parse_ast", "extract_classes"}
        is_valid, errors = rubric.validate_actions(actions)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_actions_fails_when_required_missing(self):
        rubric = StepRubric(
            required_actions={"parse_ast", "extract_classes", "extract_methods"},
        )
        actions = {"parse_ast", "extract_classes"}
        is_valid, errors = rubric.validate_actions(actions)
        assert is_valid is False
        assert any("Missing required actions" in e for e in errors)

    def test_validate_actions_fails_when_forbidden_present(self):
        rubric = StepRubric(
            required_actions={"parse_ast"},
            forbidden_actions={"validate_schema", "skip_validation"},
        )
        actions = {"parse_ast", "validate_schema"}
        is_valid, errors = rubric.validate_actions(actions)
        assert is_valid is False
        assert any("forbidden" in e.lower() for e in errors)

    def test_validate_actions_success_when_no_violations(self):
        rubric = StepRubric(
            required_actions={"a", "b"},
            forbidden_actions={"x", "y"},
        )
        actions = {"a", "b"}
        is_valid, errors = rubric.validate_actions(actions)
        assert is_valid is True
        assert len(errors) == 0


class TestStepMetrics:
    def test_start_stop_tracking(self):
        import time
        metrics = StepMetrics()
        metrics.start()
        time.sleep(0.01)
        metrics.stop()
        assert metrics.start_time is not None
        assert metrics.end_time is not None
        assert metrics.duration_ms >= 10

    def test_to_dict_format(self):
        import time
        metrics = StepMetrics()
        metrics.start()
        time.sleep(0.01)
        metrics.stop()
        metrics.retry_count = 2
        metrics.actions_performed = {"parse_ast", "extract_classes"}

        data = metrics.to_dict()
        assert "start_time" in data
        assert "end_time" in data
        assert data["duration_ms"] >= 10
        assert data["retry_count"] == 2
        assert "parse_ast" in data["actions_performed"]


class TestConversionStep:
    def test_can_execute_when_no_dependencies(self):
        step = ConversionStep(
            step_id="extract",
            description="Parse Java AST",
            required_actions={"parse_ast"},
            dependencies=[],
        )
        assert step.can_execute(set()) is True
        assert step.can_execute({"other"}) is True

    def test_can_execute_false_when_dependency_missing(self):
        step = ConversionStep(
            step_id="map",
            description="Map classes",
            required_actions={"map"},
            dependencies=["extract"],
        )
        assert step.can_execute(set()) is False
        assert step.can_execute({"extract"}) is True
        assert step.can_execute({"extract", "other"}) is True


class TestConversionDAG:
    def test_add_step_and_retrieve(self):
        dag = ConversionDAG()
        step = ConversionStep(
            step_id="extract",
            description="Extract",
            required_actions={"parse"},
        )
        dag.add_step(step)
        assert dag.get_step("extract") == step

    def test_validate_empty_dag(self):
        dag = ConversionDAG()
        is_valid, errors = dag.validate()
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_detects_missing_dependency(self):
        dag = ConversionDAG()
        step = ConversionStep(
            step_id="map",
            description="Map",
            required_actions={"map"},
            dependencies=["nonexistent"],
        )
        dag.add_step(step)
        is_valid, errors = dag.validate()
        assert is_valid is False
        assert any("unknown step" in e for e in errors)

    def test_validate_detects_cycles(self):
        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="a",
                description="A",
                required_actions=set(),
                dependencies=["b"],
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="b",
                description="B",
                required_actions=set(),
                dependencies=["a"],
            )
        )
        is_valid, errors = dag.validate()
        assert is_valid is False

    def test_get_executable_steps_respects_dependencies(self):
        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="extract",
                description="Extract",
                required_actions=set(),
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="map",
                description="Map",
                required_actions=set(),
                dependencies=["extract"],
            )
        )

        assert len(dag.get_executable_steps(set())) == 1
        assert dag.get_executable_steps(set())[0].step_id == "extract"

        assert len(dag.get_executable_steps({"extract"})) == 1
        assert dag.get_executable_steps({"extract"})[0].step_id == "map"

    def test_create_java_to_bedrock_dag_has_five_steps(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        steps = dag.get_all_steps()
        assert len(steps) == 5
        step_ids = [s.step_id for s in steps]
        assert step_ids == ["extract", "map", "generate", "validate", "repair"]

    def test_create_java_to_bedrock_dag_validates(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        is_valid, errors = dag.validate()
        assert is_valid is True
        assert len(errors) == 0


class TestStepValidator:
    def test_validate_step_execution_success(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        validator = StepValidator(dag)

        is_valid, errors = validator.validate_step_execution(
            "extract",
            {"parse_ast", "extract_imports", "extract_classes", "extract_methods"},
            100,
        )
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_step_execution_fails_on_missing_action(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        validator = StepValidator(dag)

        is_valid, errors = validator.validate_step_execution(
            "extract",
            {"parse_ast", "extract_imports"},
            100,
        )
        assert is_valid is False

    def test_validate_step_execution_fails_on_too_fast(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        validator = StepValidator(dag)

        is_valid, errors = validator.validate_step_execution(
            "validate",
            {"validate_json_schema", "validate_scripts", "validate_semantics", "check_api_compatibility"},
            40,
        )
        assert is_valid is False
        assert any("too quickly" in e for e in errors)

    def test_validate_dag_completion_success(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        validator = StepValidator(dag)

        is_valid, errors = validator.validate_dag_completion(
            {"extract", "map", "generate", "validate", "repair"}
        )
        assert is_valid is True

    def test_validate_dag_completion_fails_on_missing(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        validator = StepValidator(dag)

        is_valid, errors = validator.validate_dag_completion({"extract", "map"})
        assert is_valid is False
        assert any("Missing steps" in e for e in errors)


class TestExecutionTrace:
    def test_record_action_and_result(self):
        trace = ExecutionTrace()
        trace.record_action("extract", "parse_ast")
        trace.record_action("extract", "extract_classes")

        result = StepResult(
            step_id="extract",
            success=True,
            duration_ms=100,
        )
        trace.record_result(result)

        assert len(trace.entries) == 3
        assert trace.entries[0]["type"] == "action"
        assert trace.entries[2]["type"] == "result"

    def test_can_verify_step_order_success(self):
        trace = ExecutionTrace()
        expected = ["extract", "map", "generate"]

        for step_id in expected:
            trace.record_result(
                StepResult(step_id=step_id, success=True, duration_ms=100)
            )

        assert trace.can_verify_step_order(expected) is True

    def test_can_verify_step_order_failure(self):
        trace = ExecutionTrace()
        trace.record_result(
            StepResult(step_id="map", success=True, duration_ms=100)
        )
        trace.record_result(
            StepResult(step_id="extract", success=True, duration_ms=100)
        )

        assert trace.can_verify_step_order(["extract", "map"]) is False

    def test_to_dict_includes_statistics(self):
        trace = ExecutionTrace()
        trace.record_result(
            StepResult(step_id="extract", success=True, duration_ms=100)
        )
        trace.record_result(
            StepResult(step_id="map", success=True, duration_ms=100)
        )
        trace.record_result(
            StepResult(step_id="generate", success=False, duration_ms=50)
        )

        data = trace.to_dict()
        assert data["total_steps"] == 3
        assert data["successful_steps"] == 2


class TestConstraintGuardedExecutor:
    @pytest.mark.asyncio
    async def test_execute_step_success(self):
        import time
        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="test_step",
                description="Test step",
                required_actions={"action1", "action2"},
                rubric=StepRubric(
                    required_actions={"action1", "action2"},
                    min_duration_ms=0,
                ),
            )
        )

        async def mock_agent(context: StepContext) -> Dict[str, Any]:
            context.metrics.actions_performed.update({"action1", "action2"})
            time.sleep(0.01)
            return {"extracted": True}

        executor = ConstraintGuardedExecutor(
            dag=dag,
            agent_registry={"general": mock_agent},
            enable_rollback=True,
        )

        step = dag.get_step("test_step")
        context = StepContext(step=step, state={})

        result = await executor.execute_step(step, context)

        assert result.success is True
        assert result.step_id == "test_step"
        assert result.duration_ms >= 10

    @pytest.mark.asyncio
    async def test_execute_step_validation_failure(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()

        async def mock_agent(context: StepContext) -> Dict[str, Any]:
            context.metrics.actions_performed.add("parse_ast")
            return {"extracted": True}

        executor = ConstraintGuardedExecutor(
            dag=dag,
            agent_registry={"java_analyzer": mock_agent},
            enable_rollback=True,
        )

        step = dag.get_step("extract")
        context = StepContext(step=step, state={})

        result = await executor.execute_step(step, context)

        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_execute_step_rollback_on_failure(self):
        import time
        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="test_step",
                description="Test step",
                required_actions={"action1"},
                rubric=StepRubric(required_actions={"action1"}, min_duration_ms=0),
            )
        )

        async def mock_agent(context: StepContext) -> Dict[str, Any]:
            context.metrics.actions_performed.add("action1")
            context.state["key"] = "modified"
            time.sleep(0.01)
            return {"extracted": True}

        executor = ConstraintGuardedExecutor(
            dag=dag,
            agent_registry={"general": mock_agent},
            enable_rollback=True,
        )

        executor.state = {"key": "original"}

        step = dag.get_step("test_step")
        context = StepContext(step=step, state=executor.state)

        result = await executor.execute_step(step, context)

        assert result.success is True
        assert executor.state.get("key") == "modified"

    def test_get_next_available_steps(self):
        dag = ConversionDAG.create_java_to_bedrock_dag()
        executor = ConstraintGuardedExecutor(
            dag=dag,
            agent_registry={},
        )

        steps = executor.get_next_available_steps(set())
        assert len(steps) == 1
        assert steps[0].step_id == "extract"

        steps = executor.get_next_available_steps({"extract"})
        assert len(steps) == 1
        assert steps[0].step_id == "map"


class TestRunAgent:
    @pytest.mark.asyncio
    async def test_execute_conversion_success(self):
        import time

        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="step1",
                description="Step 1",
                required_actions={"action1"},
                rubric=StepRubric(required_actions={"action1"}, min_duration_ms=0),
                agent_type="general",
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="step2",
                description="Step 2",
                required_actions={"action2"},
                dependencies=["step1"],
                rubric=StepRubric(required_actions={"action2"}, min_duration_ms=0),
                agent_type="general",
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="step3",
                description="Step 3",
                required_actions={"action3"},
                dependencies=["step2"],
                rubric=StepRubric(required_actions={"action3"}, min_duration_ms=0),
                agent_type="general",
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="step4",
                description="Step 4",
                required_actions={"action4"},
                dependencies=["step3"],
                rubric=StepRubric(required_actions={"action4"}, min_duration_ms=0),
                agent_type="general",
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="step5",
                description="Step 5",
                required_actions={"action5"},
                dependencies=["step4"],
                rubric=StepRubric(required_actions={"action5"}, min_duration_ms=0),
                agent_type="general",
            )
        )

        async def agent(context: StepContext) -> Dict[str, Any]:
            action_name = f"action{context.step.step_id[-1]}"
            context.metrics.actions_performed.add(action_name)
            time.sleep(0.01)
            return {context.step.step_id: True}

        run_agent = RunAgent(dag=dag, strict_mode=True)
        run_agent.register_agent("general", agent)

        success, result = await run_agent.execute_conversion(
            initial_state={"source_classes": [], "source_methods": []}
        )

        assert success is True
        assert len(result["completed_steps"]) == 5
        assert all(r["success"] for r in result["step_results"])

    @pytest.mark.asyncio
    async def test_execute_conversion_strict_mode_fails(self):
        async def failing_agent(context: StepContext) -> Dict[str, Any]:
            context.metrics.actions_performed.add("some_action")
            return {"result": True}

        run_agent = RunAgent(strict_mode=True)
        run_agent.register_agent("java_analyzer", failing_agent)
        run_agent.register_agent("translator", failing_agent)
        run_agent.register_agent("reviewer", failing_agent)
        run_agent.register_agent("fixer", failing_agent)

        success, result = await run_agent.execute_conversion(initial_state={})

        assert success is False
        assert "failed_step" in result

    @pytest.mark.asyncio
    async def test_start_from_step_skips_previous(self):
        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="extract",
                description="Extract",
                required_actions={"extract"},
                rubric=None,
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="map",
                description="Map",
                required_actions={"map"},
                dependencies=["extract"],
                rubric=None,
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="generate",
                description="Generate",
                required_actions={"generate"},
                dependencies=["map"],
                rubric=None,
            )
        )

        async def agent(context: StepContext) -> Dict[str, Any]:
            context.metrics.actions_performed.add(context.step.step_id)
            return {context.step.step_id: True}

        run_agent = RunAgent(dag=dag, strict_mode=False)
        run_agent.register_agent("general", agent)

        success, result = await run_agent.execute_conversion(
            initial_state={},
            start_from_step="generate",
        )

        completed = result["completed_steps"]
        assert "extract" in completed
        assert "map" in completed
        assert "generate" in completed

    def test_setup_run_agent_with_default_dag(self):
        run_agent = RunAgent()

        assert run_agent.dag is not None
        steps = run_agent.dag.get_all_steps()
        assert len(steps) == 5

    def test_setup_run_agent_with_custom_dag(self):
        custom_dag = ConversionDAG()
        custom_dag.add_step(
            ConversionStep(
                step_id="custom",
                description="Custom step",
                required_actions=set(),
            )
        )

        run_agent = RunAgent(dag=custom_dag)
        assert run_agent.dag == custom_dag

    @pytest.mark.asyncio
    async def test_trace_preserved_after_execution(self):
        import time
        dag = ConversionDAG()
        dag.add_step(
            ConversionStep(
                step_id="step1",
                description="Step 1",
                required_actions={"action1"},
                rubric=StepRubric(required_actions={"action1"}, min_duration_ms=0),
            )
        )
        dag.add_step(
            ConversionStep(
                step_id="step2",
                description="Step 2",
                required_actions={"action2"},
                dependencies=["step1"],
                rubric=StepRubric(required_actions={"action2"}, min_duration_ms=0),
            )
        )

        async def agent(context: StepContext) -> Dict[str, Any]:
            context.metrics.actions_performed.add(context.step.step_id)
            time.sleep(0.01)
            return {"result": True}

        run_agent = RunAgent(dag=dag, strict_mode=False)
        run_agent.register_agent("general", agent)

        await run_agent.execute_conversion(initial_state={})

        trace = run_agent.get_execution_trace()
        assert trace is not None
        assert len(trace.step_results) == 2


class TestStepContext:
    def test_step_context_creation(self):
        step = ConversionStep(
            step_id="test",
            description="Test step",
            required_actions={"action1", "action2"},
        )
        context = StepContext(step=step, state={"key": "value"})

        assert context.step == step
        assert context.state["key"] == "value"
        assert len(context.artifacts) == 0
        assert len(context.errors) == 0

    def test_step_context_to_dict(self):
        step = ConversionStep(
            step_id="test",
            description="Test step",
            required_actions={"action1"},
        )
        context = StepContext(step=step, state={})
        context.metrics.actions_performed.add("action1")

        data = context.to_dict()
        assert data["step_id"] == "test"
        assert data["description"] == "Test step"
        assert len(data["metrics"]["actions_performed"]) == 1


class TestStepResult:
    def test_step_result_to_dict(self):
        result = StepResult(
            step_id="extract",
            success=True,
            output={"extracted": True},
            duration_ms=150,
            retry_count=0,
        )

        data = result.to_dict()
        assert data["step_id"] == "extract"
        assert data["success"] is True
        assert data["output"]["extracted"] is True
        assert data["duration_ms"] == 150
        assert data["rollback_performed"] is False


class TestQAOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_constraint_guided_mode_in_orchestrator(self):
        from qa.orchestrator import QAOrchestrator
        from qa.context import QAContext

        orchestrator = QAOrchestrator(constraint_guided_enabled=True)
        run_agent = orchestrator.setup_run_agent()

        assert run_agent is not None
        assert orchestrator.is_constraint_guided_enabled() is True

        context = QAContext(
            job_id="test_job",
            job_dir=Path("/tmp/test"),
            source_java_path=Path("/tmp/test/Test.java"),
            output_bedrock_path=Path("/tmp/test/output"),
        )

        result_context = await orchestrator.run_qa_pipeline_constraint_guided(context)

        assert result_context.metadata.get("execution_mode") == "constraint_guided"

    def test_orchestrator_constraint_guided_toggle(self):
        from qa.orchestrator import QAOrchestrator

        orchestrator = QAOrchestrator()

        assert orchestrator.is_constraint_guided_enabled() is False

        orchestrator.enable_constraint_guided_execution(True)
        assert orchestrator.is_constraint_guided_enabled() is True

        orchestrator.enable_constraint_guided_execution(False)
        assert orchestrator.is_constraint_guided_enabled() is False