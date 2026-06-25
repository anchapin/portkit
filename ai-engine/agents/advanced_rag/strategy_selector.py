"""strategy_selector — Fallback strategy and session-context tracking.

Seam: Extracted from AdvancedRagAgent's "no sources found" branch in
_generate_answer and the _update_session_context / get_session_context /
clear_session_context trio. Decides what to do when retrieval yields nothing
and tracks per-session history used to inform future strategy selection.

This module is intentionally distinct from orchestration/strategy_selector.py,
which selects orchestration strategies (sequential/parallel/etc.) for the
multi-agent runtime. That file is a separate concern and is protected by
issue #1709.

Issue #1709 — Subpackage split for advanced_rag_agent.py (32K).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from schemas.multimodal_schema import SearchQuery

logger = logging.getLogger(__name__)

# Maximum number of recent queries kept in session history
MAX_QUERY_HISTORY = 20
# Maximum number of successful (high-confidence) queries remembered
MAX_SUCCESSFUL_HISTORY = 10


def empty_fallback_response() -> Tuple[str, float, Dict[str, Any]]:
    """Return the canonical "no sources found" fallback tuple.

    Returns:
        Tuple of ``(answer, confidence, metadata)`` describing the fallback.
    """
    return (
        "I couldn't find relevant information to answer your question. "
        "Please try rephrasing your query or being more specific.",
        0.1,
        {"source_count": 0, "generation_method": "fallback"},
    )


def init_session_context() -> Dict[str, Any]:
    """Return a fresh session context dictionary."""
    return {
        "queries": [],
        "successful_queries": [],
        "content_preferences": {},
        "topic_interests": {},
    }


def update_session_context(
    session_contexts: Dict[str, Dict[str, Any]],
    session_id: str,
    query: SearchQuery,
    response: Any,
    config: Dict[str, Any],
) -> None:
    """Record query and response telemetry in the per-session context.

    Args:
        session_contexts: Mutable session-context map held by the agent.
        session_id: The active session identifier.
        query: The :class:`SearchQuery` that produced ``response``.
        response: The :class:`RAGResponse` returned to the user (duck-typed
            so the strategy selector doesn't depend on RAGResponse's import
            location).
        config: Agent configuration (used for ``confidence_threshold``).
    """
    if session_id not in session_contexts:
        session_contexts[session_id] = init_session_context()

    context = session_contexts[session_id]

    context["queries"].append(
        {
            "query": query.query_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence": response.confidence,
            "sources_found": len(response.sources),
        }
    )

    if response.confidence > config["confidence_threshold"]:
        context["successful_queries"].append(query.query_text)

    if query.content_types:
        for content_type in query.content_types:
            context["content_preferences"][content_type] = (
                context["content_preferences"].get(content_type, 0) + 1
            )

    # Keep only recent history
    context["queries"] = context["queries"][-MAX_QUERY_HISTORY:]
    context["successful_queries"] = context["successful_queries"][-MAX_SUCCESSFUL_HISTORY:]


def get_session_context(
    session_contexts: Dict[str, Dict[str, Any]],
    session_id: str,
) -> Dict[str, Any]:
    """Return the session context for ``session_id`` (empty dict if absent)."""
    return session_contexts.get(session_id, {})


def clear_session_context(
    session_contexts: Dict[str, Dict[str, Any]],
    session_id: str,
) -> None:
    """Remove the session context for ``session_id`` if present."""
    if session_id in session_contexts:
        del session_contexts[session_id]


class StrategySelector:
    """Selects the fallback response and manages session-aware context.

    Stateless facade — session state lives in the ``session_contexts`` dict
    passed in by the agent. This keeps the selector free of any agent
    reference and avoids the circular import with the subpackage's
    :class:`AdvancedRagAgent`.
    """

    @staticmethod
    def fallback() -> Tuple[str, float, Dict[str, Any]]:
        """Return the fallback answer tuple for empty-retrieval cases."""
        return empty_fallback_response()

    @staticmethod
    def update(
        session_contexts: Dict[str, Dict[str, Any]],
        session_id: str,
        query: SearchQuery,
        response: Any,
        config: Dict[str, Any],
    ) -> None:
        """Update the session context map for ``session_id``."""
        update_session_context(
            session_contexts=session_contexts,
            session_id=session_id,
            query=query,
            response=response,
            config=config,
        )

    @staticmethod
    def get(
        session_contexts: Dict[str, Dict[str, Any]],
        session_id: str,
    ) -> Dict[str, Any]:
        """Return the session context for ``session_id`` (empty if missing)."""
        return get_session_context(session_contexts, session_id)

    @staticmethod
    def clear(
        session_contexts: Dict[str, Dict[str, Any]],
        session_id: str,
    ) -> None:
        """Clear the session context for ``session_id`` if present."""
        clear_session_context(session_contexts, session_id)


__all__ = [
    "empty_fallback_response",
    "init_session_context",
    "update_session_context",
    "get_session_context",
    "clear_session_context",
    "MAX_QUERY_HISTORY",
    "MAX_SUCCESSFUL_HISTORY",
    "StrategySelector",
]
