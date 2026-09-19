"""Conditional branch logic for the LangGraph conversion graph.

Two pure functions consumed by ``graph_builder.ConversionPipeline`` when
wiring ``add_conditional_edges``:

- ``fan_out_converters`` — emits one ``Send`` per parallel converter node
  after the strategy planner completes.
- ``decide_qa_route`` — chooses the edge leaving the QA validator
  (``retry`` / ``hitl`` / ``complete``) based on pass rate, retry budget,
  and the human-review flag.
"""

import logging
from typing import List

from langgraph.types import Send

from .state_schema import ConversionState

logger = logging.getLogger(__name__)


def fan_out_converters(state: ConversionState) -> List[Send]:
    """Fan out to parallel converter subgraphs using LangGraph Send.

    Stateless: the same set of converter nodes runs for every job. Each
    ``Send`` carries the full state so the converter can read the planner
    output without an explicit join step.
    """
    return [
        Send("block_converter", state),
        Send("entity_converter", state),
        Send("recipe_converter", state),
        Send("asset_converter", state),
    ]


def decide_qa_route(
    state: ConversionState,
    pass_threshold: float,
    max_retries: int,
    job_id: str,
) -> str:
    """Decide the edge leaving the QA validator node.

    Returns one of ``"retry"``, ``"hitl"``, or ``"complete"``:

    - ``hitl`` — a segment was hard-flagged; interrupt for Human-In-The-Loop.
    - ``complete`` — pass rate met, or the retry budget is exhausted.
    - ``retry`` — pass rate below threshold with retries remaining.
    """
    pass_rate = state.get("pass_rate", 0.0)
    needs_human_review = state.get("needs_human_review", False)
    retry_count = state.get("retry_count", 0)

    if needs_human_review:
        logger.info(f"[{job_id}] QA needs human review - interrupting for HITL")
        return "hitl"

    if pass_rate >= pass_threshold:
        logger.info(f"[{job_id}] QA passed with {pass_rate:.2%} pass rate")
        return "complete"

    if retry_count >= max_retries:
        logger.warning(f"[{job_id}] Max retries ({max_retries}) exceeded")
        return "complete"

    logger.info(
        f"[{job_id}] QA failed ({pass_rate:.2%}), routing to retry "
        f"(attempt {retry_count + 1}/{max_retries})"
    )
    return "retry"
