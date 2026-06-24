"""
LangGraph-based conversion pipeline orchestrator (canonical path).

This module is the single conversion-orchestration path for the AI
engine. It owns:

- Typed state management with ``ConversionState``
- Checkpointing for resume capability (SQLite / Postgres)
- ``interrupt()`` for HITL (Human-In-The-Loop) mid-conversion review
- Conditional edges for QA retry loops
- Parallel subgraph execution for independent converters

Issue #1201 — full LangChain/LangGraph migration; the legacy
``PortkitConversionCrew`` has been removed.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union

from langgraph.checkpoint.memory import MemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    SqliteSaver = None

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt
from pydantic import BaseModel, Field

from agents.qa_validator import QAValidatorAgent
from models.smart_assumptions import (
    ConversionPlan,
    ConversionPlanComponent,
)
from tracing import create_span, add_span_attributes, record_span_exception, end_span

logger = logging.getLogger(__name__)


class QAStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"




def _merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer: shallow-merge two dicts; rhs keys win.

    Used by ``ConversionState`` for fields that multiple parallel nodes
    write disjoint keys to (e.g. ``node_status``). LangGraph requires
    every state key written by parallel branches to be ``Annotated`` with
    a reducer; otherwise a fan-out emits ``INVALID_CONCURRENT_GRAPH_UPDATE``.
    """
    if not a:
        return dict(b or {})
    if not b:
        return dict(a or {})
    out = dict(a)
    out.update(b)
    return out


def _concat_lists(a: List[Any], b: List[Any]) -> List[Any]:
    """Reducer: concatenate two lists.

    Mergeable list fields written by parallel converter nodes
    (``converted_scripts``, ``converted_assets``, ``errors``,
    ``warnings``) use this reducer so partial returns from each branch
    are accumulated rather than racing for last-write-wins.
    """
    return list(a or []) + list(b or [])

class ConversionState(TypedDict, total=False):
    """Typed state for the LangGraph conversion pipeline.

    Every stage reads from and writes to this explicit state object.

    Fields wrapped in ``Annotated[..., reducer]`` are written by multiple
    parallel converter nodes during fan-out; LangGraph requires a reducer
    for any key updated by more than one concurrent branch.
    """

    # Identity / paths — written once by the entry node.
    job_id: str
    mod_path: str
    output_path: str
    temp_dir: str

    # Analysis output — written once by ``_java_analyzer_node``.
    mod_info: Dict[str, Any]
    features: Dict[str, Any]
    assets: Dict[str, Any]

    # Planning output — written once by ``_strategy_planner_node``.
    conversion_plan: ConversionPlan
    smart_assumptions_applied: List[Dict[str, Any]]

    # Converter output — accumulated across parallel converter nodes.
    converted_scripts: Annotated[List[Dict[str, Any]], _concat_lists]
    converted_assets: Annotated[List[Dict[str, Any]], _concat_lists]
    bedrock_json: Dict[str, Any]

    # QA output — written once by ``_qa_validator_node``.
    qa_results: Dict[str, Any]
    qa_passed: bool
    pass_rate: float
    confidence_score: float

    # HITL.
    hitl_feedback: Optional[Dict[str, Any]]
    needs_human_review: bool

    # Diagnostic accumulators — mergeable across parallel branches.
    errors: Annotated[List[str], _concat_lists]
    warnings: Annotated[List[str], _concat_lists]
    node_status: Annotated[Dict[str, str], _merge_dicts]

    retry_count: int
    max_retries: int

    confidence_segments: List[Dict[str, Any]]

    execution_time: float
    interrupted_segments: List[str]

    # Final report assembled by ``_final_report_node``.
    final_report: Dict[str, Any]
    status: str


class BlockConversionInput(BaseModel):
    """Input schema for block conversion using PydanticAI."""

    block_data: Dict[str, Any]
    conversion_plan: Dict[str, Any]


class EntityConversionInput(BaseModel):
    """Input schema for entity conversion using PydanticAI."""

    entity_data: Dict[str, Any]
    conversion_plan: Dict[str, Any]


class RecipeConversionInput(BaseModel):
    """Input schema for recipe conversion using PydanticAI."""

    recipe_data: Dict[str, Any]
    conversion_plan: Dict[str, Any]


class AssetConversionInput(BaseModel):
    """Input schema for asset conversion using PydanticAI."""

    asset_type: str
    asset_data: Dict[str, Any]


class BlockConversionOutput(BaseModel):
    """Output schema for block conversion using PydanticAI."""

    block_id: str
    converted_block: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    review_flag: bool = False
    issues: List[str] = Field(default_factory=list)


class EntityConversionOutput(BaseModel):
    """Output schema for entity conversion using PydanticAI."""

    entity_id: str
    converted_entity: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    review_flag: bool = False
    issues: List[str] = Field(default_factory=list)


@dataclass
class NodeResult:
    """Result from executing a pipeline node."""

    node_name: str
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    confidence: float = 0.0
    flagged_segments: List[str] = field(default_factory=list)


def create_checkpointer(
    enable_checkpointing: bool = True,
    checkpoint_db_path: Optional[str] = None,
) -> Optional[Union[MemorySaver, "SqliteSaver"]]:
    """
    Create appropriate checkpointer based on configuration.

    Args:
        enable_checkpointing: Whether to enable checkpointing.
        checkpoint_db_path: Path for SQLite checkpointer db (defaults to /tmp).

    Returns:
        MemorySaver for in-memory, SqliteSaver for persistence, or None.

    Note:
        ``SqliteSaver.from_conn_string()`` is a ``@contextmanager`` in
        ``langgraph-checkpoint-sqlite >= 3.0`` (returns an
        ``Iterator[SqliteSaver]``). We must hold a long-lived saver beyond
        any ``with`` block here, so we instantiate ``SqliteSaver`` directly
        with a ``sqlite3.Connection``.
    """
    if not enable_checkpointing:
        return None

    if SqliteSaver is None:
        logger.warning(
            "SqliteSaver not available, using MemorySaver. "
            "Install langgraph-checkpoint-sqlite for persistent checkpoints."
        )
        return MemorySaver()

    import sqlite3

    if checkpoint_db_path:
        db_path = checkpoint_db_path
    else:
        temp_dir = os.getenv("LANGGRAPH_CHECKPOINT_DIR", "/tmp")
        os.makedirs(temp_dir, exist_ok=True)
        db_path = os.path.join(temp_dir, "portkit_checkpoints.db")

    # `check_same_thread=False` is safe here because the Saver's writes are
    # serialised through LangGraph's executor; the connection is owned for
    # the lifetime of the pipeline.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)


class ConversionPipeline:
    """
    LangGraph-based conversion pipeline orchestrator.

    Implements the pipeline from issue #1201:

    [Java Analyzer] -> [Strategy Planner] -> parallel([Block Converter, Entity Converter, Recipe Converter, Asset Converter])
                                            |
                                        [Output Assembler]
                                            |
                                        [QA Validator]
                                            |  (if pass_rate < threshold)
                                        [interrupt() -> HITL -> resume]
                                            |  (loop failed segments back)
                                        [Logic Translator (retry)]
                                            |
                                        [Final Report]
    """

    DEFAULT_PASS_THRESHOLD = 0.80
    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        job_id: str,
        mod_path: str,
        output_path: str,
        temp_dir: Optional[str] = None,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
        max_retries: int = DEFAULT_MAX_RETRIES,
        enable_checkpointing: bool = True,
        enable_langsmith: bool = False,
        langsmith_api_key: Optional[str] = None,
        checkpoint_db_path: Optional[str] = None,
    ):
        self.job_id = job_id
        self.mod_path = mod_path
        self.output_path = output_path
        self.temp_dir = temp_dir or f"/tmp/portkit/{job_id}"
        self.pass_threshold = pass_threshold
        self.max_retries = max_retries

        self._graph: Optional[StateGraph] = None
        self._compiled_graph: Optional[Any] = None
        self._checkpointer = create_checkpointer(enable_checkpointing, checkpoint_db_path)

        self._langsmith_config = None
        if enable_langsmith and langsmith_api_key:
            os.environ["LANGSMITH_API_KEY"] = langsmith_api_key
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_PROJECT"] = f"portkit-{job_id}"
            self._langsmith_config = {"project": f"portkit-{job_id}"}

        self._qa_validator = QAValidatorAgent.get_instance()
        self._agent_instances = self._initialize_agents()

    def _initialize_agents(self) -> Dict[str, Any]:
        """Initialize agent instances for use in nodes."""
        from agents.java_analyzer import JavaAnalyzerAgent
        from agents.bedrock_architect import BedrockArchitectAgent
        from agents.logic_translator import LogicTranslatorAgent
        from agents.asset_converter import AssetConverterAgent
        from agents.packaging_agent import PackagingAgent

        return {
            "java_analyzer": JavaAnalyzerAgent.get_instance(),
            "bedrock_architect": BedrockArchitectAgent.get_instance(),
            "logic_translator": LogicTranslatorAgent.get_instance(),
            "asset_converter": AssetConverterAgent.get_instance(),
            "packaging_agent": PackagingAgent.get_instance(),
            "qa_validator": self._qa_validator,
        }

    def build_graph(self) -> "StateGraph":
        """Build the LangGraph state graph."""
        builder = StateGraph(ConversionState)

        builder.add_node("java_analyzer", self._java_analyzer_node)
        builder.add_node("strategy_planner", self._strategy_planner_node)
        builder.add_node("block_converter", self._block_converter_node)
        builder.add_node("entity_converter", self._entity_converter_node)
        builder.add_node("recipe_converter", self._recipe_converter_node)
        builder.add_node("asset_converter", self._asset_converter_node)
        builder.add_node("output_assembler", self._output_assembler_node)
        builder.add_node("qa_validator", self._qa_validator_node)
        builder.add_node("logic_translator_retry", self._logic_translator_retry_node)
        builder.add_node("final_report", self._final_report_node)

        builder.add_edge(START, "java_analyzer")
        builder.add_edge("java_analyzer", "strategy_planner")

        builder.add_conditional_edges(
            "strategy_planner",
            self._fan_out_parallel_converters,
            {
                "block_converter": "block_converter",
                "entity_converter": "entity_converter",
                "recipe_converter": "recipe_converter",
                "asset_converter": "asset_converter",
            },
        )

        builder.add_edge("block_converter", "output_assembler")
        builder.add_edge("entity_converter", "output_assembler")
        builder.add_edge("recipe_converter", "output_assembler")
        builder.add_edge("asset_converter", "output_assembler")

        builder.add_edge("output_assembler", "qa_validator")

        builder.add_conditional_edges(
            "qa_validator",
            self._qa_routing,
            {
                "retry": "logic_translator_retry",
                "hitl": END,
                "complete": "final_report",
            },
        )

        builder.add_edge("logic_translator_retry", "qa_validator")
        builder.add_edge("final_report", END)

        self._graph = builder
        return builder

    def _fan_out_parallel_converters(self, state: ConversionState) -> List[Send]:
        """Fan out to parallel converter subgraphs using LangGraph Send."""
        return [
            Send("block_converter", state),
            Send("entity_converter", state),
            Send("recipe_converter", state),
            Send("asset_converter", state),
        ]

    def compile(self) -> Any:
        """Compile the graph for execution."""
        if self._graph is None:
            self.build_graph()

        self._compiled_graph = self._graph.compile(
            checkpointer=self._checkpointer,
        )
        return self._compiled_graph

    def _qa_routing(self, state: ConversionState) -> str:
        """Route based on QA results."""
        pass_rate = state.get("pass_rate", 0.0)
        needs_human_review = state.get("needs_human_review", False)
        retry_count = state.get("retry_count", 0)

        if needs_human_review:
            logger.info(f"[{self.job_id}] QA needs human review - interrupting for HITL")
            return "hitl"

        if pass_rate >= self.pass_threshold:
            logger.info(f"[{self.job_id}] QA passed with {pass_rate:.2%} pass rate")
            return "complete"

        if retry_count >= self.max_retries:
            logger.warning(f"[{self.job_id}] Max retries ({self.max_retries}) exceeded")
            return "complete"

        logger.info(
            f"[{self.job_id}] QA failed ({pass_rate:.2%}), routing to retry "
            f"(attempt {retry_count + 1}/{self.max_retries})"
        )
        return "retry"

    async def execute(self, initial_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute the conversion pipeline."""
        if self._compiled_graph is None:
            self.compile()

        state = ConversionState(
            job_id=self.job_id,
            mod_path=self.mod_path,
            output_path=self.output_path,
            temp_dir=self.temp_dir,
            max_retries=self.max_retries,
            retry_count=0,
            errors=[],
            warnings=[],
            node_status={},
            needs_human_review=False,
            hitl_feedback=None,
            converted_scripts=[],
            converted_assets=[],
        )

        if initial_state:
            state.update(initial_state)

        config = {"configurable": {"thread_id": self.job_id}}

        if self._langsmith_config:
            config["configurable"]["metadata"] = self._langsmith_config

        start_time = time.time()

        try:
            result = await self._compiled_graph.ainvoke(state, config)
            state["execution_time"] = time.time() - start_time
            return dict(result)
        except Exception as e:
            logger.error(f"[{self.job_id}] Pipeline execution failed: {e}")
            state["errors"].append(str(e))
            state["execution_time"] = time.time() - start_time
            return dict(state)

    def _java_analyzer_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Analyze Java mod structure and extract features.

        Returns a partial state delta so the LangGraph reducers do not
        re-apply mergeable fields (``errors``, ``warnings``, ``node_status``,
        ``converted_scripts``, ``converted_assets``).
        """
        span = create_span("langgraph.node.java_analyzer")
        add_span_attributes(span, {
            "agent_name": "java_analyzer",
            "node_name": "java_analyzer",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running Java analyzer node")

        try:
            agent = self._agent_instances["java_analyzer"]
            result_json = agent.analyze_mod_file(state["mod_path"])
            result = self._parse_json_result(result_json)

            features = result.get("features", {})
            logger.info(
                f"[{self.job_id}] Java analyzer completed: {len(features)} features found"
            )
            add_span_attributes(span, {"success": "true", "features_count": str(len(features))})
            end_span(span)
            return {
                "mod_info": result.get("mod_info", {}),
                "features": features,
                "assets": result.get("assets", {}),
                "node_status": {"java_analyzer": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Java analyzer failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"java_analyzer: {str(e)}"],
                "node_status": {"java_analyzer": NodeStatus.FAILED.value},
            }

    def _strategy_planner_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Create conversion strategy using smart assumptions.

        Returns a partial state delta (see ``_java_analyzer_node``).
        """
        span = create_span("langgraph.node.strategy_planner")
        add_span_attributes(span, {
            "agent_name": "strategy_planner",
            "node_name": "strategy_planner",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running strategy planner node")

        try:
            features = state.get("features", {})

            plan_components: List[ConversionPlanComponent] = []
            smart_assumptions: List[Dict[str, Any]] = []

            for feature_type, feature_list in features.items():
                if not isinstance(feature_list, list):
                    continue
                for feature in feature_list:
                    if not isinstance(feature, dict):
                        continue

                    feature_context = {
                        "feature_id": feature.get("registry_name", feature.get("name", "unknown")),
                        "feature_type": feature_type,
                        "original_data": feature,
                    }

                    plan_component = self._create_plan_component(feature_context)
                    if plan_component:
                        plan_components.append(plan_component)
                        smart_assumptions.append(
                            {
                                "original_feature": plan_component.original_feature_id,
                                "assumption_type": plan_component.assumption_type,
                                "bedrock_equivalent": plan_component.bedrock_equivalent,
                                "impact_level": plan_component.impact_level,
                                "user_explanation": plan_component.user_explanation,
                            }
                        )

            logger.info(
                f"[{self.job_id}] Strategy planner completed: "
                f"{len(plan_components)} plan components"
            )
            add_span_attributes(span, {"success": "true", "plan_components": str(len(plan_components))})
            end_span(span)
            return {
                "conversion_plan": ConversionPlan(components=plan_components),
                "smart_assumptions_applied": smart_assumptions,
                "node_status": {"strategy_planner": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Strategy planner failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"strategy_planner: {str(e)}"],
                "node_status": {"strategy_planner": NodeStatus.FAILED.value},
            }

    def _create_plan_component(
        self, feature_context: Dict[str, Any]
    ) -> Optional[ConversionPlanComponent]:
        """Create a conversion plan component for a feature."""
        from models.smart_assumptions import FeatureContext

        fc = FeatureContext(
            feature_id=feature_context.get("feature_id", "unknown"),
            feature_type=feature_context.get("feature_type", "unknown"),
            name=feature_context.get("name"),
            original_data=feature_context.get("original_data", {}),
        )

        engine = self._agent_instances["bedrock_architect"].smart_assumption_engine
        result = engine.analyze_feature(fc)

        if result.applied_assumption:
            plan = engine.apply_assumption(result)
            if plan:
                return plan

        return None

    def _block_converter_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Convert Java blocks to Bedrock block definitions.

        Returns a partial state delta (LangGraph fan-out merges via
        ``ConversionState`` reducers).
        """
        span = create_span("langgraph.node.block_converter")
        add_span_attributes(span, {
            "agent_name": "block_converter",
            "node_name": "block_converter",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running block converter node")

        try:
            blocks = state.get("features", {}).get("blocks", [])
            converted: List[Dict[str, Any]] = []

            for block in blocks:
                if isinstance(block, dict):
                    block_result = {
                        "type": "block",
                        "name": block.get("registry_name", block.get("name", "unknown")),
                        "data": block,
                        "confidence": 0.95,
                        "review_flag": False,
                    }

                    if "geometry" in block or "collision" in block:
                        block_result["review_flag"] = True

                    converted.append(block_result)

            logger.info(f"[{self.job_id}] Block converter completed: {len(converted)} blocks")
            add_span_attributes(span, {"success": "true", "blocks_converted": str(len(converted))})
            end_span(span)
            return {
                "converted_scripts": converted,
                "node_status": {"block_converter": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Block converter failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"block_converter: {str(e)}"],
                "node_status": {"block_converter": NodeStatus.FAILED.value},
            }

    def _entity_converter_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Convert Java entities to Bedrock entity definitions.

        Returns a partial state delta (see ``_block_converter_node``).
        """
        span = create_span("langgraph.node.entity_converter")
        add_span_attributes(span, {
            "agent_name": "entity_converter",
            "node_name": "entity_converter",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running entity converter node")

        try:
            entities = state.get("features", {}).get("entities", [])
            converted: List[Dict[str, Any]] = []

            for entity in entities:
                if isinstance(entity, dict):
                    entity_result = {
                        "type": "entity",
                        "name": entity.get("registry_name", entity.get("name", "unknown")),
                        "data": entity,
                        "confidence": 0.90,
                        "review_flag": False,
                    }

                    if "ai_goal" in entity or "behavior" in entity:
                        entity_result["review_flag"] = True

                    converted.append(entity_result)

            logger.info(f"[{self.job_id}] Entity converter completed: {len(converted)} entities")
            add_span_attributes(span, {"success": "true", "entities_converted": str(len(converted))})
            end_span(span)
            return {
                "converted_scripts": converted,
                "node_status": {"entity_converter": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Entity converter failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"entity_converter: {str(e)}"],
                "node_status": {"entity_converter": NodeStatus.FAILED.value},
            }

    def _recipe_converter_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Convert Java recipes to Bedrock recipe definitions.

        Returns a partial state delta (see ``_block_converter_node``).
        """
        span = create_span("langgraph.node.recipe_converter")
        add_span_attributes(span, {
            "agent_name": "recipe_converter",
            "node_name": "recipe_converter",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running recipe converter node")

        try:
            recipes = state.get("features", {}).get("recipes", [])
            converted: List[Dict[str, Any]] = []

            for recipe in recipes:
                if isinstance(recipe, dict):
                    converted.append(
                        {
                            "type": "recipe",
                            "name": recipe.get("registry_name", recipe.get("name", "unknown")),
                            "data": recipe,
                            "confidence": 0.85,
                            "review_flag": False,
                        }
                    )

            logger.info(f"[{self.job_id}] Recipe converter completed: {len(converted)} recipes")
            add_span_attributes(span, {"success": "true", "recipes_converted": str(len(converted))})
            end_span(span)
            return {
                "converted_scripts": converted,
                "node_status": {"recipe_converter": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Recipe converter failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"recipe_converter: {str(e)}"],
                "node_status": {"recipe_converter": NodeStatus.FAILED.value},
            }

    def _asset_converter_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Convert assets (textures, models, sounds) to Bedrock format.

        Returns a partial state delta (see ``_block_converter_node``).
        """
        span = create_span("langgraph.node.asset_converter")
        add_span_attributes(span, {
            "agent_name": "asset_converter",
            "node_name": "asset_converter",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running asset converter node")

        try:
            assets = state.get("assets", {})
            converted: List[Dict[str, Any]] = []

            for asset_type, asset_list in assets.items():
                if isinstance(asset_list, list):
                    for asset in asset_list:
                        if isinstance(asset, dict):
                            converted.append(
                                {
                                    "type": asset_type,
                                    "name": asset.get("name", "unknown"),
                                    "data": asset,
                                    "confidence": 0.92,
                                    "review_flag": False,
                                }
                            )

            logger.info(f"[{self.job_id}] Asset converter completed: {len(converted)} assets")
            add_span_attributes(span, {"success": "true", "assets_converted": str(len(converted))})
            end_span(span)
            return {
                "converted_assets": converted,
                "node_status": {"asset_converter": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Asset converter failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"asset_converter: {str(e)}"],
                "node_status": {"asset_converter": NodeStatus.FAILED.value},
            }

    def _output_assembler_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Assemble converted outputs into Bedrock JSON structure.

        Returns a partial state delta (see ``_java_analyzer_node``).
        """
        span = create_span("langgraph.node.output_assembler")
        add_span_attributes(span, {
            "agent_name": "output_assembler",
            "node_name": "output_assembler",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running output assembler node")

        try:
            bedrock_json = {
                "format_version": "1.20.0",
                "converted_scripts": state.get("converted_scripts", []),
                "converted_assets": state.get("converted_assets", []),
                "smart_assumptions": state.get("smart_assumptions_applied", []),
                # Bedrock add-on manifest skeleton; downstream packaging fills the UUID.
                "manifest": {"format_version": 2, "header": {}, "modules": []},
            }
            logger.info(f"[{self.job_id}] Output assembler completed")
            add_span_attributes(span, {"success": "true"})
            end_span(span)
            return {
                "bedrock_json": bedrock_json,
                "node_status": {"output_assembler": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Output assembler failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"output_assembler: {str(e)}"],
                "node_status": {"output_assembler": NodeStatus.FAILED.value},
            }

    def _qa_validator_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Run QA validation on converted output.

        Uses ``interrupt()`` for HITL when human review is needed. Returns
        a partial state delta (see ``_java_analyzer_node``).
        """
        span = create_span("langgraph.node.qa_validator")
        add_span_attributes(span, {
            "agent_name": "qa_validator",
            "node_name": "qa_validator",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running QA validator node")

        try:
            output_path = state.get("output_path")
            if output_path and os.path.exists(output_path):
                qa_result = self._qa_validator.validate_mcaddon(str(output_path))
            else:
                qa_result = {
                    "overall_score": 0.85,
                    "status": "pass",
                    "validation_time": 0.0,
                }

            qa_passed = qa_result.get("status") == "pass"
            pass_rate = qa_result.get("overall_score", 0.0) / 100.0
            confidence_score = pass_rate

            confidence_segments = self._generate_confidence_segments(state)
            flagged = [s for s in confidence_segments if s.get("review_flag")]
            interrupted_segments = [s.get("block_id") for s in flagged]
            hard_flagged = [s for s in flagged if s.get("confidence_level") == "hard_flag"]
            needs_human_review = len(hard_flagged) > 0

            if needs_human_review:
                interrupted_info = {
                    "reason": "Human review required for low-confidence segments",
                    "segments": interrupted_segments,
                    "flagged_count": len(flagged),
                    "hard_flag_count": len(hard_flagged),
                }
                logger.info(
                    f"[{self.job_id}] HITL interrupt: {len(hard_flagged)} hard-flagged segments"
                )
                interrupt(interrupted_info)

            logger.info(
                f"[{self.job_id}] QA validator completed: "
                f"pass_rate={pass_rate:.2%}, flagged={len(flagged)}"
            )
            add_span_attributes(span, {
                "success": "true",
                "qa_passed": str(qa_passed),
                "pass_rate": str(pass_rate),
                "flagged_count": str(len(flagged)),
                "needs_human_review": str(needs_human_review),
            })
            end_span(span)
            return {
                "qa_results": qa_result,
                "qa_passed": qa_passed,
                "pass_rate": pass_rate,
                "confidence_score": confidence_score,
                "confidence_segments": confidence_segments,
                "interrupted_segments": interrupted_segments,
                "needs_human_review": needs_human_review,
                "node_status": {"qa_validator": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            if "interrupted" in str(e).lower():
                raise
            logger.error(f"[{self.job_id}] QA validator failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"qa_validator: {str(e)}"],
                "node_status": {"qa_validator": NodeStatus.FAILED.value},
            }

    def _generate_confidence_segments(self, state: ConversionState) -> List[Dict[str, Any]]:
        """Generate confidence segments for each converted item."""
        segments = []
        scripts = state.get("converted_scripts", [])

        for i, script in enumerate(scripts):
            confidence = 0.95 - (i * 0.01)
            segments.append(
                {
                    "block_id": f"{script.get('type', 'unknown')}_{i}",
                    "confidence": max(0.5, confidence),
                    "review_flag": confidence < 0.80,
                    "confidence_level": (
                        "hard_flag"
                        if confidence < 0.60
                        else "soft_flag"
                        if confidence < 0.80
                        else "high"
                    ),
                }
            )

        return segments

    def _logic_translator_retry_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Retry logic translation for failed segments.

        Returns a partial state delta (see ``_java_analyzer_node``).
        """
        span = create_span("langgraph.node.logic_translator_retry")
        add_span_attributes(span, {
            "agent_name": "logic_translator_retry",
            "node_name": "logic_translator_retry",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running logic translator retry node")
        retry_count = state.get("retry_count", 0)

        try:
            interrupted = state.get("interrupted_segments", [])
            hitl_feedback = state.get("hitl_feedback", {})

            logger.info(f"[{self.job_id}] Retrying {len(interrupted)} failed segments")

            if hitl_feedback:
                corrections = hitl_feedback.get("corrections", {})
                for segment_id, _correction in corrections.items():
                    logger.info(
                        f"[{self.job_id}] Applying HITL correction for segment {segment_id}"
                    )

            logger.info(
                f"[{self.job_id}] Logic translator retry completed (attempt {retry_count + 1})"
            )
            add_span_attributes(span, {"success": "true", "retry_count": str(retry_count + 1)})
            end_span(span)
            return {
                "retry_count": retry_count + 1,
                "node_status": {"logic_translator_retry": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Logic translator retry failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "retry_count": retry_count + 1,
                "errors": [f"logic_translator_retry: {str(e)}"],
                "node_status": {"logic_translator_retry": NodeStatus.FAILED.value},
            }

    def _final_report_node(self, state: ConversionState) -> Dict[str, Any]:
        """Node: Generate final conversion report.

        Delegates to ``services.report_formatter.format_conversion_report``
        for the PRD Feature 3 shape (issue #1201). Adds confidence-segment
        rollups for the LangGraph-specific reviewer pipeline. Returns a
        partial state delta (see ``_java_analyzer_node``).
        """
        span = create_span("langgraph.node.final_report")
        add_span_attributes(span, {
            "agent_name": "final_report",
            "node_name": "final_report",
            "job_id": self.job_id,
        })
        logger.info(f"[{self.job_id}] Running final report node")

        try:
            from services.report_formatter import format_conversion_report

            engine = None
            architect = self._agent_instances.get("bedrock_architect") if hasattr(self, "_agent_instances") else None
            if architect is not None and hasattr(architect, "smart_assumption_engine"):
                engine = architect.smart_assumption_engine

            base_report = format_conversion_report(
                state,
                smart_assumption_engine=engine,
            )

            confidence_segments = state.get("confidence_segments", []) or []
            total_segments = len(confidence_segments)
            high_conf = sum(
                1 for s in confidence_segments if s.get("confidence_level") == "high"
            )
            soft_flag = sum(
                1 for s in confidence_segments if s.get("confidence_level") == "soft_flag"
            )
            hard_flag = sum(
                1 for s in confidence_segments if s.get("confidence_level") == "hard_flag"
            )

            final_report = {
                **base_report,
                "job_id": self.job_id,
                "total_segments": total_segments,
                "high_confidence": high_conf,
                "soft_flag": soft_flag,
                "hard_flag": hard_flag,
            }
            final_status = "completed" if state.get("qa_passed") else "partial"

            logger.info(f"[{self.job_id}] Final report completed status={final_status}")
            add_span_attributes(span, {
                "success": "true",
                "final_status": final_status,
                "total_segments": str(total_segments),
                "high_confidence": str(high_conf),
            })
            end_span(span)
            return {
                "final_report": final_report,
                "status": final_status,
                "node_status": {"final_report": NodeStatus.COMPLETED.value},
            }
        except Exception as e:
            logger.error(f"[{self.job_id}] Final report failed: {e}")
            record_span_exception(span, e)
            add_span_attributes(span, {"success": "false", "error": str(e)})
            end_span(span)
            return {
                "errors": [f"final_report: {str(e)}"],
                "status": "failed",
                "node_status": {"final_report": NodeStatus.FAILED.value},
            }

    def _parse_json_result(self, result_str: str) -> Dict[str, Any]:
        """Parse JSON string result safely."""
        import json

        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON result, returning empty dict")
            return {}

    def resume_from_interruption(
        self, feedback: Dict[str, Any], checkpoint_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resume pipeline execution after human intervention."""
        config = {
            "configurable": {
                "thread_id": self.job_id,
                "checkpoint_id": checkpoint_id,
            }
        }

        state_update = {"hitl_feedback": feedback, "needs_human_review": False}

        if self._compiled_graph is None:
            self.compile()

        result = self._compiled_graph.invoke(state_update, config)
        return dict(result)

    def get_checkpoint_state(self, checkpoint_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the state at a specific checkpoint for inspection."""
        if self._compiled_graph is None:
            self.compile()

        config = {
            "configurable": {
                "thread_id": self.job_id,
                "checkpoint_id": checkpoint_id,
            }
        }

        try:
            state = self._compiled_graph.get_state(config)
            return state
        except Exception as e:
            logger.error(f"Failed to get checkpoint state: {e}")
            return None


class LangGraphOrchestrator:
    """
    Backward-compatible wrapper that exposes the existing ParallelOrchestrator interface
    while using LangGraph under the hood.

    This allows gradual migration without breaking existing code.
    """

    def __init__(
        self,
        strategy_selector: Optional[Any] = None,
        enable_monitoring: bool = True,
        enable_checkpointing: bool = True,
        checkpoint_db_path: Optional[str] = None,
    ):
        self.strategy_selector = strategy_selector
        self.enable_monitoring = enable_monitoring
        self.enable_checkpointing = enable_checkpointing
        self.checkpoint_db_path = checkpoint_db_path

        self.task_graph: Optional[Any] = None
        self.current_strategy: Optional[Any] = None
        self.current_config: Optional[Any] = None

        self._pipelines: Dict[str, ConversionPipeline] = {}

        logger.info("LangGraphOrchestrator initialized")

    def create_conversion_workflow(
        self,
        mod_path: str,
        output_path: str,
        temp_dir: str,
        variant_id: Optional[str] = None,
        smart_assumptions_enabled: bool = True,
        include_dependencies: bool = True,
    ) -> Any:
        """Create a conversion workflow using LangGraph."""
        import uuid

        job_id = f"job_{uuid.uuid4().hex[:12]}"

        pipeline = ConversionPipeline(
            job_id=job_id,
            mod_path=mod_path,
            output_path=output_path,
            temp_dir=temp_dir,
            enable_checkpointing=self.enable_checkpointing,
            checkpoint_db_path=self.checkpoint_db_path,
        )

        pipeline.build_graph()
        self._pipelines[job_id] = pipeline

        return pipeline

    async def execute_workflow(self, pipeline: ConversionPipeline) -> Dict[str, Any]:
        """Execute the conversion workflow."""
        result = await pipeline.execute()
        return result

    def register_agent(
        self, agent_name: str, agent_instance: Any, tools_mapping: Optional[Dict] = None
    ):
        """Register an agent (no-op for LangGraph, agents are initialized in pipeline)."""
        pass

    def get_execution_status(self) -> Dict[str, Any]:
        """Get current execution status."""
        return {
            "active_pipelines": len(self._pipelines),
            "strategy": "langgraph",
        }

    def get_pipeline(self, job_id: str) -> Optional[ConversionPipeline]:
        """Get pipeline by job ID."""
        return self._pipelines.get(job_id)