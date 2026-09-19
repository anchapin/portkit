"""LangGraph conversion pipeline subpackage (issue #1728).

Splits the former ``orchestration.langgraph_pipeline`` monolith (39K) into
focused modules while preserving the entire public API via re-exports:

- :mod:`state_schema`   — ``ConversionState`` TypedDict, status enums,
  PydanticAI input/output models, reducers, ``NodeResult``.
- :mod:`checkpointing`  — ``create_checkpointer`` (Memory/SQLite savers).
- :mod:`routing`        — conditional-edge decisions (QA route, fan-out).
- :mod:`retry_fallback` — the ``logic_translator_retry`` node handler.
- :mod:`graph_builder`  — ``ConversionPipeline`` + ``LangGraphOrchestrator``.

The canonical entry point is :class:`ConversionPipeline`; build and compile
a graph via ``pipeline.build_graph()`` then ``pipeline.compile()``.
"""

from .checkpointing import create_checkpointer
from .graph_builder import ConversionPipeline, LangGraphOrchestrator
from .retry_fallback import execute_logic_translator_retry
from .routing import decide_qa_route, fan_out_converters
from .state_schema import (
    AssetConversionInput,
    BlockConversionInput,
    BlockConversionOutput,
    ConversionState,
    EntityConversionInput,
    EntityConversionOutput,
    NodeResult,
    NodeStatus,
    QAStatus,
    RecipeConversionInput,
)

__all__ = [
    # Pipeline + orchestration
    "ConversionPipeline",
    "LangGraphOrchestrator",
    "create_checkpointer",
    # State schema + enums
    "ConversionState",
    "NodeStatus",
    "QAStatus",
    "NodeResult",
    # PydanticAI input/output schemas
    "BlockConversionInput",
    "EntityConversionInput",
    "RecipeConversionInput",
    "AssetConversionInput",
    "BlockConversionOutput",
    "EntityConversionOutput",
    # Routing + retry (re-exported for direct unit testing)
    "decide_qa_route",
    "fan_out_converters",
    "execute_logic_translator_retry",
]
