"""
Unit tests for orchestration/orchestrator.py - ParallelOrchestrator

Covers ParallelOrchestrator init, agent registration, workflow creation
(sequential/parallel/adaptive/hybrid), spawn-callback factories, complexity
analysis, system-resource detection, performance-metric recording, and the
execution-status snapshot. Worker pools are mocked so the suite stays
fast and isolated.
"""

import json
import os
from unittest.mock import Mock

import pytest

from orchestration.orchestrator import ParallelOrchestrator
from orchestration.strategy_selector import (
    OrchestrationStrategy,
    StrategyConfig,
    StrategySelector,
)
from orchestration.task_graph import TaskGraph, TaskNode


pytestmark = pytest.mark.unit


def _make_jar(tmp_path, size_bytes: int = 100) -> str:
    """Create a fake JAR file of the requested size for mod_path tests."""
    path = os.path.join(str(tmp_path), "fake.jar")
    with open(path, "wb") as f:
        f.write(b"PK\x03\x04")
        f.write(b"\x00" * max(0, size_bytes - 4))
    return path


class TestParallelOrchestratorInit:
    """Cover ParallelOrchestrator.__init__ defaults and custom inputs."""

    def test_init_default_strategy_selector(self):
        orch = ParallelOrchestrator()
        assert isinstance(orch.strategy_selector, StrategySelector)
        assert orch.enable_monitoring is True
        assert orch.task_graph is None
        assert orch.worker_pool is None
        assert orch.current_strategy is None
        assert orch.current_config is None
        assert orch.agent_executors == {}
        assert orch.execution_results == {}

    def test_init_with_custom_selector(self):
        custom_selector = StrategySelector(default_strategy=OrchestrationStrategy.SEQUENTIAL)
        orch = ParallelOrchestrator(strategy_selector=custom_selector)
        assert orch.strategy_selector is custom_selector

    def test_init_with_monitoring_disabled(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        assert orch.enable_monitoring is False


class TestRegisterAgent:
    """Cover register_agent: stores executor under agent_name."""

    def test_register_agent_with_run_method(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        agent = Mock()
        agent.run = Mock(return_value={"result": "ok"})
        orch.register_agent("test_agent", agent)
        assert "test_agent" in orch.agent_executors
        assert callable(orch.agent_executors["test_agent"])

    def test_register_agent_with_execute_method(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        agent = Mock(spec=["execute"])
        agent.execute = Mock(return_value={"r": 1})
        orch.register_agent("exec_agent", agent)
        assert "exec_agent" in orch.agent_executors

    def test_register_agent_callable(self):
        orch = ParallelOrchestrator(enable_monitoring=False)

        def my_agent(task):
            return {"called": True}

        orch.register_agent("callable_agent", my_agent)
        assert "callable_agent" in orch.agent_executors

    def test_register_agent_with_tools_mapping(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        agent = Mock()
        agent.run = Mock(return_value={"ok": True})
        tools = {"tool1": Mock()}
        orch.register_agent("agent_with_tools", agent, tools_mapping=tools)
        assert "agent_with_tools" in orch.agent_executors

    def test_register_multiple_agents(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        for name in ("a", "b", "c"):
            agent = Mock()
            agent.run = Mock(return_value=name)
            orch.register_agent(name, agent)
        assert set(orch.agent_executors.keys()) == {"a", "b", "c"}


class TestCreateConversionWorkflow:
    """Cover create_conversion_workflow: delegates to strategy-specific builders."""

    def test_create_workflow_default_returns_task_graph(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path)
        graph = orch.create_conversion_workflow(
            mod_path=mod_path, output_path="/tmp/out", temp_dir="/tmp/temp"
        )
        assert isinstance(graph, TaskGraph)
        assert "analyze" in graph.nodes
        assert orch.current_strategy is not None
        assert orch.current_config is not None

    def test_create_workflow_base_input_propagation(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path)
        graph = orch.create_conversion_workflow(
            mod_path=mod_path,
            output_path="/tmp/o",
            temp_dir="/tmp/t",
            variant_id="v1",
            smart_assumptions_enabled=False,
            include_dependencies=False,
        )
        analyze_task = graph.nodes["analyze"]
        assert analyze_task.input_data["smart_assumptions_enabled"] is False
        assert analyze_task.input_data["include_dependencies"] is False
        assert analyze_task.input_data["variant_id"] == "v1"
        assert analyze_task.input_data["mod_path"] == mod_path

    def test_create_workflow_sequential_strategy(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path)
        orch.strategy_selector.select_strategy = Mock(
            return_value=(
                OrchestrationStrategy.SEQUENTIAL,
                StrategyConfig(max_parallel_tasks=1),
            )
        )
        graph = orch.create_conversion_workflow(
            mod_path=mod_path, output_path="/tmp/o", temp_dir="/tmp/t"
        )
        for task_id in (
            "analyze",
            "plan",
            "translate",
            "convert_assets",
            "package",
            "validate",
        ):
            assert task_id in graph.nodes

    def test_create_workflow_parallel_basic_strategy(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path)
        orch.strategy_selector.select_strategy = Mock(
            return_value=(
                OrchestrationStrategy.PARALLEL_BASIC,
                StrategyConfig(max_parallel_tasks=4),
            )
        )
        graph = orch.create_conversion_workflow(
            mod_path=mod_path, output_path="/tmp/o", temp_dir="/tmp/t"
        )
        assert len(graph.nodes) == 6

    def test_create_workflow_adaptive_strategy_attaches_spawn_callbacks(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path)
        orch.strategy_selector.select_strategy = Mock(
            return_value=(
                OrchestrationStrategy.PARALLEL_ADAPTIVE,
                StrategyConfig(max_parallel_tasks=4, enable_dynamic_spawning=True),
            )
        )
        graph = orch.create_conversion_workflow(
            mod_path=mod_path, output_path="/tmp/o", temp_dir="/tmp/t"
        )
        # Adaptive workflow attaches spawn callbacks to analyze and plan
        assert graph.nodes["analyze"].spawn_callback is not None
        assert graph.nodes["plan"].spawn_callback is not None

    def test_create_workflow_hybrid_strategy_delegates_to_parallel(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path)
        orch.strategy_selector.select_strategy = Mock(
            return_value=(
                OrchestrationStrategy.HYBRID,
                StrategyConfig(max_parallel_tasks=2),
            )
        )
        graph = orch.create_conversion_workflow(
            mod_path=mod_path, output_path="/tmp/o", temp_dir="/tmp/t"
        )
        # Hybrid delegates to parallel basic: 6 tasks, no spawn callbacks
        assert len(graph.nodes) == 6
        assert graph.nodes["analyze"].spawn_callback is None


class TestSpawnCallbacks:
    """Cover the spawn-callback factories that drive dynamic task generation."""

    def test_analysis_spawn_callback_with_json_string(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        callback = orch._create_analysis_spawn_callback({"base": True})
        analysis_result = json.dumps(
            {
                "features": {
                    "entities": [
                        {"name": "zombie", "complex": True},
                        {"name": "skeleton", "complex": False},
                        {"name": "creeper", "complex": True},
                    ]
                }
            }
        )
        tasks = callback(analysis_result)
        assert len(tasks) == 2
        assert all(t.agent_name == "entity_converter" for t in tasks)
        assert tasks[0].task_id == "convert_entity_0"
        assert tasks[1].task_id == "convert_entity_2"

    def test_analysis_spawn_callback_with_dict(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        callback = orch._create_analysis_spawn_callback({"base": True})
        analysis_result = {"features": {"entities": [{"name": "wither", "complex": True}]}}
        tasks = callback(analysis_result)
        assert len(tasks) == 1
        assert tasks[0].input_data["entity_data"]["name"] == "wither"

    def test_analysis_spawn_callback_unexpected_type(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        callback = orch._create_analysis_spawn_callback({})
        # Non-str, non-dict input is gracefully ignored
        tasks = callback(12345)
        assert tasks == []

    def test_analysis_spawn_callback_handles_bad_json(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        callback = orch._create_analysis_spawn_callback({})
        # Invalid JSON in a string input is gracefully ignored
        tasks = callback("not { valid json")
        assert tasks == []

    def test_planning_spawn_callback_skips_when_no_features(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        callback = orch._create_planning_spawn_callback({"base": True})
        # Plain object with no .complex_features attribute
        tasks = callback({"foo": "bar"})
        assert tasks == []


class TestAnalyzeModComplexity:
    """Cover _analyze_mod_complexity: derives metrics from file size."""

    def test_analyze_small_mod(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path, size_bytes=100)
        complexity = orch._analyze_mod_complexity(mod_path)
        assert complexity["file_size_mb"] < 5
        assert complexity["num_features"] == 5
        assert complexity["estimated_entities"] == 3
        assert complexity["has_complex_assets"] is False

    def test_analyze_medium_mod(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path, size_bytes=6 * 1024 * 1024)
        complexity = orch._analyze_mod_complexity(mod_path)
        assert complexity["file_size_mb"] > 5
        assert complexity["num_features"] == 10
        assert complexity["estimated_entities"] == 5

    def test_analyze_large_mod(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path, size_bytes=11 * 1024 * 1024)
        complexity = orch._analyze_mod_complexity(mod_path)
        assert complexity["file_size_mb"] > 10
        assert complexity["num_features"] == 15
        assert complexity["estimated_entities"] == 8
        assert complexity["has_complex_assets"] is True

    def test_analyze_missing_file_returns_zero(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        complexity = orch._analyze_mod_complexity(str(tmp_path / "nope.jar"))
        assert complexity["file_size_mb"] == 0
        # Defaults are still applied for a non-existent file
        assert complexity["num_features"] == 5


class TestSystemResourcesAndStatus:
    """Cover _get_system_resources and get_execution_status."""

    def test_get_system_resources_shape(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        resources = orch._get_system_resources()
        assert "cpu_count" in resources
        assert "memory_gb" in resources
        assert "is_containerized" in resources
        assert isinstance(resources["cpu_count"], int)
        assert resources["cpu_count"] >= 1

    def test_get_execution_status_initial(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        status = orch.get_execution_status()
        assert status["strategy"] is None
        assert status["is_running"] is False
        assert status["start_time"] is None
        assert status["end_time"] is None
        assert status["duration"] is None

    def test_get_execution_status_with_task_graph(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        # execute_workflow sets self.task_graph, so we simulate that here
        graph = TaskGraph()
        graph.add_task(TaskNode(task_id="t", agent_name="a", agent_type="x", input_data={}))
        orch.task_graph = graph
        status = orch.get_execution_status()
        # The graph was attached, so its stats are merged into status
        assert "total_tasks" in status
        assert status["total_tasks"] == 1

    def test_get_execution_status_running(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        orch.execution_start_time = 1000.0
        orch.execution_end_time = None
        status = orch.get_execution_status()
        assert status["is_running"] is True
        assert status["duration"] is not None

    def test_get_execution_status_complete(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        orch.execution_start_time = 1000.0
        orch.execution_end_time = 1005.0
        status = orch.get_execution_status()
        assert status["is_running"] is False
        assert status["duration"] == pytest.approx(5.0)


class TestRecordPerformanceMetrics:
    """Cover _record_performance_metrics: delegates to strategy_selector."""

    def test_record_performance_metrics_writes_to_selector(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        orch.strategy_selector.record_performance = Mock()
        orch.execution_start_time = 100.0
        orch.execution_end_time = 102.5
        orch.current_strategy = OrchestrationStrategy.PARALLEL_BASIC
        graph = TaskGraph()
        graph.add_task(TaskNode(task_id="t", agent_name="a", agent_type="x", input_data={}))
        graph.mark_task_completed("t", "ok")
        orch._record_performance_metrics(graph, {"t": "ok"})
        orch.strategy_selector.record_performance.assert_called_once()
        call_kwargs = orch.strategy_selector.record_performance.call_args.kwargs
        assert call_kwargs["success_rate"] == 1.0
        assert call_kwargs["task_count"] == 1
        assert call_kwargs["total_duration"] == pytest.approx(2.5)

    def test_record_performance_metrics_no_timestamps(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        orch.strategy_selector.record_performance = Mock()
        orch.execution_start_time = None
        orch.execution_end_time = None
        # Should early-return without calling the selector
        orch._record_performance_metrics(TaskGraph(), {})
        orch.strategy_selector.record_performance.assert_not_called()


class TestAnalyzeModForSelection:
    """Cover that create_conversion_workflow passes computed complexity through."""

    def test_workflow_passes_complexity_to_selector(self, tmp_path):
        orch = ParallelOrchestrator(enable_monitoring=False)
        mod_path = _make_jar(tmp_path, size_bytes=12 * 1024 * 1024)
        orch.strategy_selector.select_strategy = Mock(
            return_value=(
                OrchestrationStrategy.PARALLEL_BASIC,
                StrategyConfig(max_parallel_tasks=4),
            )
        )
        orch.create_conversion_workflow(mod_path=mod_path, output_path="/tmp/o", temp_dir="/tmp/t")
        call_kwargs = orch.strategy_selector.select_strategy.call_args.kwargs
        assert call_kwargs["task_complexity"]["has_complex_assets"] is True
        assert "cpu_count" in call_kwargs["system_resources"]


class TestGetExecutionStatusWithWorkerPool:
    """Cover get_execution_status including worker_stats when a pool is active."""

    def test_status_merges_worker_stats(self):
        orch = ParallelOrchestrator(enable_monitoring=False)
        orch.execution_start_time = 1.0
        orch.execution_end_time = 2.0
        # Mock a worker pool with get_worker_stats
        fake_pool = Mock()
        fake_pool.get_worker_stats = Mock(return_value={"total_completed": 5})
        orch.worker_pool = fake_pool
        status = orch.get_execution_status()
        assert status["worker_stats"]["total_completed"] == 5
