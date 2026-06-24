"""
Parallel Orchestrator for managing multi-agent conversion workflows.
Part of Phase 2: Core Orchestration Engine Implementation

Extracted from ``orchestration/orchestrator.py`` as part of issue #1767.
The orchestrator combines the workflow-builder and executor mixins:

- :mod:`orchestration.core.workflows`  — workflow-graph construction
- :mod:`orchestration.core.execution` — workflow execution loops
"""

import logging
import multiprocessing
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..pool import WorkerPool, create_agent_executor
from ..strategy_selector import OrchestrationStrategy, StrategyConfig, StrategySelector
from ..task_graph import TaskGraph
from .execution import WorkflowExecutorMixin
from .workflows import WorkflowBuilderMixin

logger = logging.getLogger(__name__)


class ParallelOrchestrator(WorkflowBuilderMixin, WorkflowExecutorMixin):
    """
    Main orchestrator for parallel multi-agent conversion workflows.
    Manages task graphs, worker pools, and execution strategies.
    """

    def __init__(
        self, strategy_selector: Optional[StrategySelector] = None, enable_monitoring: bool = True
    ):
        """
        Initialize the parallel orchestrator

        Args:
            strategy_selector: Strategy selector for choosing execution approaches
            enable_monitoring: Enable performance monitoring and logging
        """
        self.strategy_selector = strategy_selector or StrategySelector()
        self.enable_monitoring = enable_monitoring

        # Core components
        self.task_graph: Optional[TaskGraph] = None
        self.worker_pool: Optional[WorkerPool] = None
        self.current_strategy: Optional[OrchestrationStrategy] = None
        self.current_config: Optional[StrategyConfig] = None

        # Agent executors mapping
        self.agent_executors: Dict[str, Callable] = {}

        # Execution state
        self.execution_start_time: Optional[float] = None
        self.execution_end_time: Optional[float] = None
        self.execution_results: Dict[str, Any] = {}

        logger.info("ParallelOrchestrator initialized")

    def register_agent(
        self, agent_name: str, agent_instance: Any, tools_mapping: Optional[Dict] = None
    ):
        """
        Register an agent for execution

        Args:
            agent_name: Unique identifier for the agent
            agent_instance: The agent instance to execute
            tools_mapping: Optional tools mapping for the agent
        """
        executor = create_agent_executor(agent_instance, tools_mapping)
        self.agent_executors[agent_name] = executor
        logger.debug(f"Registered agent: {agent_name}")

    def create_conversion_workflow(
        self,
        mod_path: str,
        output_path: str,
        temp_dir: str,
        variant_id: Optional[str] = None,
        smart_assumptions_enabled: bool = True,
        include_dependencies: bool = True,
    ) -> TaskGraph:
        """
        Create the conversion workflow task graph

        Args:
            mod_path: Path to the Java mod file
            output_path: Output path for conversion
            temp_dir: Temporary directory for intermediate files
            variant_id: A/B testing variant identifier
            smart_assumptions_enabled: Enable smart assumption processing
            include_dependencies: Include dependency analysis

        Returns:
            TaskGraph representing the conversion workflow
        """

        # Select execution strategy
        task_complexity = self._analyze_mod_complexity(mod_path)
        system_resources = self._get_system_resources()

        strategy, config = self.strategy_selector.select_strategy(
            variant_id=variant_id,
            task_complexity=task_complexity,
            system_resources=system_resources,
        )

        self.current_strategy = strategy
        self.current_config = config

        logger.info(f"Creating workflow with strategy: {strategy.value}")

        # Create task graph
        task_graph = TaskGraph()

        # Common input data for all tasks
        base_input = {
            "mod_path": mod_path,
            "output_path": output_path,
            "temp_dir": temp_dir,
            "smart_assumptions_enabled": smart_assumptions_enabled,
            "include_dependencies": include_dependencies,
            "strategy": strategy.value,
            "variant_id": variant_id,
        }

        # Create tasks based on strategy
        if strategy == OrchestrationStrategy.SEQUENTIAL:
            return self._create_sequential_workflow(task_graph, base_input)
        elif strategy == OrchestrationStrategy.PARALLEL_BASIC:
            return self._create_parallel_basic_workflow(task_graph, base_input)
        elif strategy == OrchestrationStrategy.PARALLEL_ADAPTIVE:
            return self._create_adaptive_workflow(task_graph, base_input)
        elif strategy == OrchestrationStrategy.HYBRID:
            return self._create_hybrid_workflow(task_graph, base_input)
        else:
            raise ValueError(f"Unsupported strategy: {strategy}")

    def _analyze_mod_complexity(self, mod_path: str) -> Dict[str, Any]:
        """Analyze mod complexity for strategy selection"""
        # This is a simplified analysis - in practice, you'd examine the mod file

        mod_file = Path(mod_path)

        # Basic complexity metrics
        complexity = {
            "file_size_mb": mod_file.stat().st_size / (1024 * 1024) if mod_file.exists() else 0,
            "num_features": 5,  # Default estimate
            "num_dependencies": 2,  # Default estimate
            "has_complex_assets": False,
            "estimated_entities": 3,
        }

        # Estimate based on file size
        if complexity["file_size_mb"] > 10:
            complexity["num_features"] = 15
            complexity["estimated_entities"] = 8
            complexity["has_complex_assets"] = True
        elif complexity["file_size_mb"] > 5:
            complexity["num_features"] = 10
            complexity["estimated_entities"] = 5

        return complexity

    def _get_system_resources(self) -> Dict[str, Any]:
        """Get current system resource information"""
        return {
            "cpu_count": multiprocessing.cpu_count(),
            "memory_gb": 8,  # Default estimate - could use psutil if available
            "is_containerized": os.path.exists("/.dockerenv"),
        }

    def _record_performance_metrics(self, task_graph: TaskGraph, results: Dict[str, Any]):
        """Record performance metrics for strategy optimization"""

        if not self.execution_start_time or not self.execution_end_time:
            return

        stats = task_graph.get_completion_stats()
        total_duration = self.execution_end_time - self.execution_start_time
        success_rate = stats["completion_rate"]

        # Record in strategy selector
        self.strategy_selector.record_performance(
            strategy=self.current_strategy,
            success_rate=success_rate,
            total_duration=total_duration,
            task_count=stats["total_tasks"],
            additional_metrics={
                "failed_tasks": stats["failed_tasks"],
                "average_task_duration": stats["average_task_duration"],
                "parallel_efficiency": stats["total_duration"] / total_duration
                if total_duration > 0
                else 0,
            },
        )

        logger.info(
            f"Recorded performance: strategy={self.current_strategy.value}, "
            f"success_rate={success_rate:.2%}, duration={total_duration:.2f}s"
        )

    def get_execution_status(self) -> Dict[str, Any]:
        """Get current execution status"""

        status = {
            "strategy": self.current_strategy.value if self.current_strategy else None,
            "is_running": self.execution_start_time is not None and self.execution_end_time is None,
            "start_time": self.execution_start_time,
            "end_time": self.execution_end_time,
            "duration": (
                (self.execution_end_time or time.time()) - self.execution_start_time
                if self.execution_start_time
                else None
            ),
        }

        if self.task_graph:
            status.update(self.task_graph.get_completion_stats())

        if self.worker_pool:
            status["worker_stats"] = self.worker_pool.get_worker_stats()

        return status
