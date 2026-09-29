"""query_router — Query intent classification and routing.

Seam: Extracted from AdvancedRagAgent.query() — handles pre-retrieval decisions
about how a query should be expanded and which intent bucket it falls into
(how-to, explanation, example, general). Stateless router that operates on a
search query and session context.

Issue #1709 — Subpackage split for advanced_rag_agent.py (32K).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from schemas.multimodal_schema import ContentType, SearchQuery
from search.query_expansion import ExpansionStrategy, QueryExpansionEngine

logger = logging.getLogger(__name__)

INTENT_HOW_TO = "how_to"
INTENT_EXPLANATION = "explanation"
INTENT_EXAMPLE = "example"
INTENT_GENERAL = "general"

_HOW_TO_KEYWORDS = ("how", "create", "make", "build")
_EXPLANATION_KEYWORDS = ("what", "explain", "definition")
_EXAMPLE_KEYWORDS = ("example", "sample", "demo")


def classify_query_intent(query_text: str) -> str:
    """Classify a query into an answer-style intent bucket.

    Args:
        query_text: The raw user query.

    Returns:
        One of ``INTENT_HOW_TO``, ``INTENT_EXPLANATION``, ``INTENT_EXAMPLE``,
        or ``INTENT_GENERAL``.
    """
    if not query_text:
        return INTENT_GENERAL

    query_lower = query_text.lower()
    if any(word in query_lower for word in _HOW_TO_KEYWORDS):
        return INTENT_HOW_TO
    if any(word in query_lower for word in _EXPLANATION_KEYWORDS):
        return INTENT_EXPLANATION
    if any(word in query_lower for word in _EXAMPLE_KEYWORDS):
        return INTENT_EXAMPLE
    return INTENT_GENERAL


def build_search_query(
    query_text: str,
    content_types: Optional[List[ContentType]],
    project_context: Optional[str],
    config: Dict[str, Any],
    reranker: Optional[Any],
    query_expander: Optional[Any],
) -> SearchQuery:
    """Construct a SearchQuery instance with agent-level defaults applied.

    Args:
        query_text: Raw user query text.
        content_types: Optional content-type filter.
        project_context: Optional project context string.
        config: Agent configuration dictionary.
        reranker: Optional reranker instance (controls enable_reranking).
        query_expander: Optional query expander (controls expand_query).

    Returns:
        A fully configured :class:`SearchQuery`.
    """
    return SearchQuery(
        query_text=query_text,
        content_types=content_types,
        project_context=project_context,
        top_k=config["max_sources"],
        similarity_threshold=config["min_relevance_threshold"],
        use_hybrid_search=True,
        enable_reranking=bool(reranker),
        expand_query=bool(query_expander),
    )


def expand_search_query(
    search_query: SearchQuery,
    query_expander: QueryExpansionEngine,
    session_contexts: Dict[str, Dict[str, Any]],
    session_id: str,
    project_context: Optional[str],
) -> Optional[Any]:
    """Run multi-strategy query expansion and mutate ``search_query.query_text``.

    Args:
        search_query: The :class:`SearchQuery` to expand (mutated in place).
        query_expander: The :class:`QueryExpansionEngine` to use.
        session_contexts: Per-session context dictionary held by the agent.
        session_id: The active session identifier.
        project_context: Optional project context for expansion hints.

    Returns:
        The expansion result object from the engine, or ``None`` if expansion
        was disabled.
    """
    if not query_expander:
        return None

    session_context = session_contexts.get(session_id, {})
    session_context.update({"session_id": session_id, "project_context": project_context})

    expanded_query = query_expander.expand_query(
        search_query,
        strategies=[
            ExpansionStrategy.DOMAIN_EXPANSION,
            ExpansionStrategy.SYNONYM_EXPANSION,
            ExpansionStrategy.CONTEXTUAL_EXPANSION,
        ],
        session_context=session_context,
    )

    search_query.query_text = expanded_query.expanded_query
    return expanded_query


class QueryRouter:
    """Routes incoming queries through intent classification and expansion.

    Stateless facade — the agent supplies dependencies (expander, session
    context map) at call time. Kept free of agent state so the subpackage
    can be imported without circular references to :class:`AdvancedRagAgent`.
    """

    @staticmethod
    def classify(query_text: str) -> str:
        """Return the intent bucket for ``query_text``."""
        return classify_query_intent(query_text)

    @staticmethod
    def build(
        query_text: str,
        content_types: Optional[List[ContentType]],
        project_context: Optional[str],
        config: Dict[str, Any],
        reranker: Optional[Any],
        query_expander: Optional[Any],
    ) -> SearchQuery:
        """Build a configured :class:`SearchQuery` for downstream stages."""
        return build_search_query(
            query_text=query_text,
            content_types=content_types,
            project_context=project_context,
            config=config,
            reranker=reranker,
            query_expander=query_expander,
        )

    @staticmethod
    def expand(
        search_query: SearchQuery,
        query_expander: Optional[QueryExpansionEngine],
        session_contexts: Dict[str, Dict[str, Any]],
        session_id: str,
        project_context: Optional[str],
    ) -> Optional[Any]:
        """Run expansion if enabled and return the expansion result."""
        return expand_search_query(
            search_query=search_query,
            query_expander=query_expander,
            session_contexts=session_contexts,
            session_id=session_id,
            project_context=project_context,
        )


__all__ = [
    "INTENT_HOW_TO",
    "INTENT_EXPLANATION",
    "INTENT_EXAMPLE",
    "INTENT_GENERAL",
    "classify_query_intent",
    "build_search_query",
    "expand_search_query",
    "QueryRouter",
]
