"""
Workflow construction for :class:`ParallelOrchestrator`.

Extracted from ``orchestration/orchestrator.py`` as part of issue #1767.
Exposed as the :class:`WorkflowBuilderMixin`; the orchestrator class combines
this with :class:`WorkflowExecutorMixin` (see :mod:`core.execution`).
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List

from ..task_graph import TaskGraph, TaskNode

logger = logging.getLogger(__name__)


class WorkflowBuilderMixin:
    """
    Mixin providing workflow-graph construction strategies.

    These methods operate on ``self``, which must supply the strategy/config
    attributes managed by :class:`ParallelOrchestrator`.
    """

    def _create_sequential_workflow(
        self, task_graph: TaskGraph, base_input: Dict[str, Any]
    ) -> TaskGraph:
        """Create sequential workflow (baseline single-threaded execution)"""

        # Create tasks in sequential order
        analyze_task = TaskNode(
            task_id="analyze",
            agent_name="java_analyzer",
            agent_type="analyzer",
            input_data=base_input.copy(),
            priority=5,
        )
        task_graph.add_task(analyze_task)

        plan_task = TaskNode(
            task_id="plan",
            agent_name="bedrock_architect",
            agent_type="planner",
            input_data=base_input.copy(),
            priority=4,
        )
        task_graph.add_task(plan_task)
        task_graph.add_dependency("plan", "analyze")

        translate_task = TaskNode(
            task_id="translate",
            agent_name="logic_translator",
            agent_type="translator",
            input_data=base_input.copy(),
            priority=3,
        )
        task_graph.add_task(translate_task)
        task_graph.add_dependency("translate", "plan")

        convert_assets_task = TaskNode(
            task_id="convert_assets",
            agent_name="asset_converter",
            agent_type="converter",
            input_data=base_input.copy(),
            priority=3,
        )
        task_graph.add_task(convert_assets_task)
        task_graph.add_dependency("convert_assets", "plan")

        package_task = TaskNode(
            task_id="package",
            agent_name="packaging_agent",
            agent_type="packager",
            input_data=base_input.copy(),
            priority=2,
        )
        task_graph.add_task(package_task)
        task_graph.add_dependency("package", "translate")
        task_graph.add_dependency("package", "convert_assets")

        validate_task = TaskNode(
            task_id="validate",
            agent_name="qa_validator",
            agent_type="validator",
            input_data=base_input.copy(),
            priority=1,
        )
        task_graph.add_task(validate_task)
        task_graph.add_dependency("validate", "package")

        return task_graph

    def _create_parallel_basic_workflow(
        self, task_graph: TaskGraph, base_input: Dict[str, Any]
    ) -> TaskGraph:
        """Create basic parallel workflow"""

        # Analysis task first (required by all others)
        analyze_task = TaskNode(
            task_id="analyze",
            agent_name="java_analyzer",
            agent_type="analyzer",
            input_data=base_input.copy(),
            priority=5,
        )
        task_graph.add_task(analyze_task)

        # Planning task depends on analysis
        plan_task = TaskNode(
            task_id="plan",
            agent_name="bedrock_architect",
            agent_type="planner",
            input_data=base_input.copy(),
            priority=4,
        )
        task_graph.add_task(plan_task)
        task_graph.add_dependency("plan", "analyze")

        # Translation and asset conversion can run in parallel after planning
        translate_task = TaskNode(
            task_id="translate",
            agent_name="logic_translator",
            agent_type="translator",
            input_data=base_input.copy(),
            priority=3,
        )
        task_graph.add_task(translate_task)
        task_graph.add_dependency("translate", "plan")

        convert_assets_task = TaskNode(
            task_id="convert_assets",
            agent_name="asset_converter",
            agent_type="converter",
            input_data=base_input.copy(),
            priority=3,
        )
        task_graph.add_task(convert_assets_task)
        task_graph.add_dependency("convert_assets", "plan")

        # Packaging waits for both translation and asset conversion
        package_task = TaskNode(
            task_id="package",
            agent_name="packaging_agent",
            agent_type="packager",
            input_data=base_input.copy(),
            priority=2,
        )
        task_graph.add_task(package_task)
        task_graph.add_dependency("package", "translate")
        task_graph.add_dependency("package", "convert_assets")

        # Validation runs after packaging
        validate_task = TaskNode(
            task_id="validate",
            agent_name="qa_validator",
            agent_type="validator",
            input_data=base_input.copy(),
            priority=1,
        )
        task_graph.add_task(validate_task)
        task_graph.add_dependency("validate", "package")

        return task_graph

    def _create_adaptive_workflow(
        self, task_graph: TaskGraph, base_input: Dict[str, Any]
    ) -> TaskGraph:
        """Create adaptive workflow with dynamic spawning"""

        # Start with basic parallel structure
        task_graph = self._create_parallel_basic_workflow(task_graph, base_input)

        # Add dynamic spawning callbacks
        analyze_task = task_graph.nodes["analyze"]
        analyze_task.spawn_callback = self._create_analysis_spawn_callback(base_input)

        plan_task = task_graph.nodes["plan"]
        plan_task.spawn_callback = self._create_planning_spawn_callback(base_input)

        return task_graph

    def _create_hybrid_workflow(
        self, task_graph: TaskGraph, base_input: Dict[str, Any]
    ) -> TaskGraph:
        """Create hybrid workflow mixing sequential and parallel approaches"""

        # NOTE: Hybrid workflow optimization not yet implemented.
        # Currently delegates to parallel workflow as a fallback.
        # In future iterations, this should analyze dependencies and complexity
        # to decide on parallelization strategy.
        return self._create_parallel_basic_workflow(task_graph, base_input)

    def _create_analysis_spawn_callback(self, base_input: Dict[str, Any]) -> Callable:
        """Create callback for dynamic task spawning after analysis"""

        def spawn_callback(analysis_result: Any) -> List[TaskNode]:
            """Spawn additional tasks based on analysis results"""
            spawned_tasks = []

            try:
                # Parse analysis result to determine what to spawn
                if isinstance(analysis_result, str):
                    result_data = json.loads(analysis_result)
                elif isinstance(analysis_result, dict):
                    result_data = analysis_result
                else:
                    logger.warning(f"Unexpected analysis result type: {type(analysis_result)}")
                    return spawned_tasks

                # Example: Spawn specialized entity converters for each entity type
                entities = result_data.get("features", {}).get("entities", [])
                for i, entity in enumerate(entities):
                    if isinstance(entity, dict) and entity.get("complex", False):
                        entity_task = TaskNode(
                            task_id=f"convert_entity_{i}",
                            agent_name="entity_converter",
                            agent_type="entity_converter",
                            input_data={**base_input, "entity_data": entity, "entity_index": i},
                            priority=3,
                        )
                        spawned_tasks.append(entity_task)

                logger.info(f"Spawned {len(spawned_tasks)} entity conversion tasks")

            except asyncio.CancelledError:
                raise  # Always re-raise CancelledError — never swallow it
            except TimeoutError:
                raise  # Re-raise timeouts too
            except Exception as e:
                logger.error(f"Error in analysis spawn callback: {e}")

            return spawned_tasks

        return spawn_callback

    def _create_planning_spawn_callback(self, base_input: Dict[str, Any]) -> Callable:
        """Create callback for dynamic task spawning after planning"""

        def spawn_callback(planning_result: Any) -> List[TaskNode]:
            """Spawn additional tasks based on planning results"""
            spawned_tasks = []

            try:
                # Example: Spawn specialized tasks for complex conversions
                if hasattr(planning_result, "complex_features"):
                    for feature in planning_result.complex_features:
                        if feature.requires_specialized_processing:
                            specialized_task = TaskNode(
                                task_id=f"specialized_{feature.id}",
                                agent_name="specialized_converter",
                                agent_type="specialized_converter",
                                input_data={
                                    **base_input,
                                    "feature_data": feature,
                                },
                                priority=3,
                            )
                            spawned_tasks.append(specialized_task)

                logger.info(f"Spawned {len(spawned_tasks)} specialized conversion tasks")

            except asyncio.CancelledError:
                raise  # Always re-raise CancelledError — never swallow it
            except TimeoutError:
                raise  # Re-raise timeouts too
            except Exception as e:
                logger.error(f"Error in planning spawn callback: {e}")

            return spawned_tasks

        return spawn_callback
