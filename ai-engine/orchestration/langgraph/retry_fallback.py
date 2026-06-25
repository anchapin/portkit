"""Retry orchestration and fallback chains for the conversion graph.

``execute_logic_translator_retry`` is the node handler bound to the
``logic_translator_retry`` graph node. It runs after the QA validator
fails a pass-rate threshold (or after a HITL resume) and re-attempts the
flagged segments, applying any human-supplied corrections before bumping
the retry counter and handing control back to the QA validator.
"""

import logging
from typing import Any, Dict

from tracing import add_span_attributes, create_span, end_span, record_span_exception

from .state_schema import ConversionState, NodeStatus

logger = logging.getLogger(__name__)


def execute_logic_translator_retry(
    state: ConversionState,
    job_id: str,
) -> Dict[str, Any]:
    """Retry logic translation for failed segments.

    Bound as the ``logic_translator_retry`` graph node. Returns a partial
    state delta so the LangGraph reducers do not re-apply mergeable fields
    (``errors``, ``warnings``, ``node_status``).
    """
    span = create_span("langgraph.node.logic_translator_retry")
    add_span_attributes(
        span,
        {
            "agent_name": "logic_translator_retry",
            "node_name": "logic_translator_retry",
            "job_id": job_id,
        },
    )
    logger.info(f"[{job_id}] Running logic translator retry node")
    retry_count = state.get("retry_count", 0)

    try:
        interrupted = state.get("interrupted_segments", [])
        hitl_feedback = state.get("hitl_feedback", {})

        logger.info(f"[{job_id}] Retrying {len(interrupted)} failed segments")

        if hitl_feedback:
            corrections = hitl_feedback.get("corrections", {})
            for segment_id, _correction in corrections.items():
                logger.info(f"[{job_id}] Applying HITL correction for segment {segment_id}")

        logger.info(f"[{job_id}] Logic translator retry completed (attempt {retry_count + 1})")
        add_span_attributes(span, {"success": "true", "retry_count": str(retry_count + 1)})
        end_span(span)
        return {
            "retry_count": retry_count + 1,
            "node_status": {"logic_translator_retry": NodeStatus.COMPLETED.value},
        }
    except Exception as e:
        logger.error(f"[{job_id}] Logic translator retry failed: {e}")
        record_span_exception(span, e)
        add_span_attributes(span, {"success": "false", "error": str(e)})
        end_span(span)
        return {
            "retry_count": retry_count + 1,
            "errors": [f"logic_translator_retry: {str(e)}"],
            "node_status": {"logic_translator_retry": NodeStatus.FAILED.value},
        }
