"""Retry orchestration and fallback chains for the conversion graph.

``execute_logic_translator_retry`` is the node handler bound to the
``logic_translator_retry`` graph node. It runs after the QA validator
fails a pass-rate threshold (or after a HITL resume) and re-attempts the
flagged segments, applying any human-supplied corrections before bumping
the retry counter and handing control back to the QA validator.
"""

import logging
from typing import Any, Dict, List

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
        converted = list(state.get("converted_scripts", []))

        corrections = {}
        if hitl_feedback:
            corrections = hitl_feedback.get("corrections", {})

        corrected_count = 0
        corrected_keys: List[str] = []
        for segment_id, correction_data in corrections.items():
            for i, script in enumerate(converted):
                script_key = f"{script.get('type', 'unknown')}_{i}"
                if script_key == segment_id or script.get("name") == segment_id:
                    if isinstance(correction_data, dict):
                        script["data"] = correction_data.get("bedrock_data", script.get("data", {}))
                        script["confidence"] = correction_data.get("confidence", script.get("confidence", 0.95))
                        script["review_flag"] = correction_data.get("review_flag", False)
                        script["corrected"] = True
                    corrected_keys.append(script_key)
                    corrected_count += 1
                    logger.info(f"[{job_id}] Applied HITL correction for segment {segment_id}")

        logger.info(f"[{job_id}] Logic translator retry completed (attempt {retry_count + 1}): "
                     f"{len(interrupted)} segments retried, {corrected_count} corrections applied")
        add_span_attributes(span, {
            "success": "true",
            "retry_count": str(retry_count + 1),
            "segments_retried": str(len(interrupted)),
            "corrections_applied": str(corrected_count),
        })
        end_span(span)

        # Do NOT return converted_scripts here — the Annotated[..., _concat_lists]
        # reducer would duplicate the scripts list on every retry cycle.
        # HITL-corrected scripts are flagged in-place via the 'corrected' key.
        # The corrected flag is checked downstream (output_assembler, final_report).
        return {
            "retry_count": retry_count + 1,
            "corrected_segment_keys": corrected_keys,
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
