"""result_fuser — Reranking and context fusion.

Seam: Extracted from AdvancedRagAgent.query() reranking call and the
context-combination block inside _generate_answer. Takes raw retrieval output
and a query, runs the optional reranker, then builds a token-budgeted,
source-cited context string ready for the synthesizer.

Issue #1709 — Subpackage split for advanced_rag_agent.py (32K).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from schemas.multimodal_schema import SearchQuery, SearchResult
from search.reranking_engine import EnsembleReRanker
from utils.token_optimizer import ContextTrimmer

logger = logging.getLogger(__name__)


def rerank_results(
    query: SearchQuery,
    search_results: List[SearchResult],
    reranker: EnsembleReRanker,
    session_id: str,
) -> Tuple[List[SearchResult], Dict[str, Any]]:
    """Apply the ensemble reranker to ``search_results`` if available.

    Args:
        query: The :class:`SearchQuery` driving the search.
        search_results: Initial retrieval results.
        reranker: :class:`EnsembleReRanker` instance.
        session_id: Session identifier passed through to the reranker.

    Returns:
        Tuple of (possibly reranked results, reranking metadata dict).
    """
    if not reranker or not search_results:
        return search_results, {}

    return reranker.ensemble_rerank(query, search_results, session_id)


def build_fused_context(
    sources: List[SearchResult],
    config: Dict[str, Any],
    context_trimmer: ContextTrimmer,
    num_sources: int = 5,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Build a token-budgeted, source-cited context string from sources.

    Args:
        sources: The ranked :class:`SearchResult` list to fuse.
        config: Agent configuration providing ``context_window_size``.
        context_trimmer: Token estimator used for budget logging.
        num_sources: Maximum number of sources to include in the context.

    Returns:
        Tuple of ``(combined_context, source_info, metadata)``:
            * ``combined_context`` is the joined text block to feed the
              synthesizer.
            * ``source_info`` is a list of source descriptor dicts (rank,
              relevance, content_type, source_path).
            * ``metadata`` carries token usage and budget diagnostics.
    """
    max_context_tokens = config["context_window_size"]
    reserve_tokens = 500
    available_tokens = max_context_tokens - reserve_tokens
    used_sources = min(num_sources, len(sources))
    tokens_per_source = available_tokens // max(1, used_sources)
    chars_per_source = tokens_per_source * 4

    context_parts: List[str] = []
    source_info: List[Dict[str, Any]] = []

    for i, source in enumerate(sources[:used_sources]):
        if not source.document.content_text:
            continue
        content = source.document.content_text[:chars_per_source]
        if len(source.document.content_text) > chars_per_source:
            content += " [...]"
        context_parts.append(f"Source {i + 1} ({source.document.source_path}):\n{content}")
        source_info.append(
            {
                "rank": source.rank,
                "relevance": source.final_score,
                "content_type": source.document.content_type,
                "source_path": source.document.source_path,
            }
        )

    combined_context = "\n\n".join(context_parts)
    estimated_tokens = context_trimmer.estimate_tokens(combined_context)
    logger.debug(f"Context built with ~{estimated_tokens} tokens (budget: {available_tokens})")

    metadata = {
        "context_length": len(combined_context),
        "context_tokens": estimated_tokens,
        "context_token_budget": available_tokens,
    }
    return combined_context, source_info, metadata


class ResultFuser:
    """Fuses retrieval results through reranking and context aggregation.

    Stateless facade — the agent supplies the reranker and context trimmer
    at call time. Returning the metadata dict separately lets the agent
    merge it into the final :class:`RAGResponse` without leaking state.
    """

    @staticmethod
    def rerank(
        query: SearchQuery,
        search_results: List[SearchResult],
        reranker: EnsembleReRanker,
        session_id: str,
    ) -> Tuple[List[SearchResult], Dict[str, Any]]:
        """Rerank ``search_results`` using the supplied ensemble reranker."""
        return rerank_results(query, search_results, reranker, session_id)

    @staticmethod
    def build_context(
        sources: List[SearchResult],
        config: Dict[str, Any],
        context_trimmer: ContextTrimmer,
        num_sources: int = 5,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """Build the fused context block from ranked sources."""
        return build_fused_context(
            sources=sources,
            config=config,
            context_trimmer=context_trimmer,
            num_sources=num_sources,
        )


__all__ = [
    "rerank_results",
    "build_fused_context",
    "ResultFuser",
]
