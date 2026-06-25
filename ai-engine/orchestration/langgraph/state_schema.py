"""Typed state schemas, enums, and reducers for the LangGraph pipeline.

Holds the purely declarative pieces of the conversion graph: the
``ConversionState`` TypedDict (and its reducer-annotated mergeable fields),
the PydanticAI input/output models, the status enums, and the ``NodeResult``
dataclass. Kept free of any graph-building or agent logic so it can be
imported by every other ``langgraph`` submodule without cycles.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from models.smart_assumptions import ConversionPlan


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
