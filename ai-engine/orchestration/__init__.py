"""
Multi-Agent Orchestration package for the LangGraph-based conversion pipeline.

The conversion engine runs entirely on LangGraph + LangChain (issue #1201).
The legacy LangChain/LangGraph-coupled bridges (``EnhancedConversionCrew``,
``RunAgentCrewBridge``) have been removed; the ``RunAgent`` constraint
framework remains as a generic step-execution helper that can be wired
into LangGraph nodes when needed.
"""

from .orchestrator import ParallelOrchestrator
from .strategy_selector import OrchestrationStrategy, StrategySelector
from .task_graph import TaskGraph, TaskNode, TaskStatus
from .worker_pool import WorkerPool
from .langgraph import (
    ConversionPipeline,
    ConversionState,
    LangGraphOrchestrator,
    NodeStatus,
    NodeResult,
    create_checkpointer,
    BlockConversionInput,
    EntityConversionInput,
    RecipeConversionInput,
    AssetConversionInput,
    BlockConversionOutput,
    EntityConversionOutput,
)
from .progress import PipelineProgress, PipelineStage, log_pipeline_progress
from .run_agent import (
    RunAgent,
    RunAgentPlan,
    Step,
    StepContext,
    StepStatus as RunAgentStepStatus,
    Constraint,
    StepResult,
)

__all__ = [
    # Legacy task-graph orchestration components (still used by some code paths)
    "TaskGraph",
    "TaskNode",
    "TaskStatus",
    "ParallelOrchestrator",
    "WorkerPool",
    "OrchestrationStrategy",
    "StrategySelector",
    # LangGraph-based conversion pipeline (the canonical path)
    "ConversionPipeline",
    "ConversionState",
    "LangGraphOrchestrator",
    "NodeStatus",
    "NodeResult",
    "create_checkpointer",
    # PydanticAI input/output schemas for typed node calls
    "BlockConversionInput",
    "EntityConversionInput",
    "RecipeConversionInput",
    "AssetConversionInput",
    "BlockConversionOutput",
    "EntityConversionOutput",
    # Progress tracking
    "PipelineProgress",
    "PipelineStage",
    "log_pipeline_progress",
    # RunAgent components (generic constraint-guided step execution)
    "RunAgent",
    "RunAgentPlan",
    "Step",
    "StepContext",
    "StepResult",
    "Constraint",
    "RunAgentStepStatus",
]
