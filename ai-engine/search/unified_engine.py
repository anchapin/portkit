"""
Unified search engine combining hybrid search with query expansion and reranking.

Extracted from the original ``hybrid_search_engine.py`` (issue #1741).
This engine provides a complete RAG search pipeline:
1. Query expansion for better recall
2. Hybrid search combining vector and keyword search
3. Cross-encoder reranking for improved precision
"""

import logging
from typing import Any, Dict, List, Optional

from schemas.multimodal_schema import SearchQuery, SearchResult
from search.search_types import SearchCandidate, SearchMode

logger = logging.getLogger(__name__)


class UnifiedSearchEngine:
    """
    Unified search engine that combines hybrid search with query expansion and reranking.

    Attributes:
        hybrid_engine: The underlying hybrid search engine
        reranker: Optional reranker for post-processing results
        query_expander: Optional query expander for improving recall
    """

    def __init__(
        self,
        vector_store: Any = None,
        document_index: Any = None,
        reranker: Any = None,
        query_expander: Any = None,
        embedding_model: str = "all-MiniLM-L6-v2",
        search_mode: SearchMode = SearchMode.HYBRID,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.5,
        rerank_top_k: int = 50,
        enable_query_expansion: bool = True,
        enable_reranking: bool = True,
    ):
        """
        Initialize the unified search engine.

        Args:
            vector_store: Vector store for semantic search
            document_index: Document index for keyword search
            reranker: Reranker instance for post-processing results
            query_expander: Query expander for improving recall
            embedding_model: Name of the embedding model to use
            search_mode: Search mode to use (HYBRID, KEYWORD_ONLY, VECTOR_ONLY)
            keyword_weight: Weight for keyword search scores (0-1)
            vector_weight: Weight for vector search scores (0-1)
            rerank_top_k: Number of top results to rerank
            enable_query_expansion: Whether to enable query expansion
            enable_reranking: Whether to enable reranking
        """
        from search.hybrid_engine import HybridSearchEngine

        self.hybrid_engine = HybridSearchEngine(
            vector_store=vector_store,
            document_index=document_index,
            embedding_model=embedding_model,
            search_mode=search_mode,
            keyword_weight=keyword_weight,
            vector_weight=vector_weight,
        )

        self.reranker = reranker
        self.query_expander = query_expander
        self.rerank_top_k = rerank_top_k
        self.enable_query_expansion = enable_query_expansion
        self.enable_reranking = enable_reranking

        logger.info(
            f"UnifiedSearchEngine initialized with mode={search_mode}, "
            f"reranking={enable_reranking}, query_expansion={enable_query_expansion}"
        )

    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        expand_queries: bool = None,
        rerank_results: bool = None,
        search_mode: SearchMode = None,
    ) -> List[SearchCandidate]:
        """
        Perform unified search with optional query expansion and reranking.

        Args:
            query: The search query string
            filters: Optional filters to apply to search results
            top_k: Number of results to return
            expand_queries: Override for query expansion (default: use instance setting)
            rerank_results: Override for reranking (default: use instance setting)
            search_mode: Override for search mode (default: use instance setting)

        Returns:
            List of search candidates sorted by relevance
        """
        do_expand = expand_queries if expand_queries is not None else self.enable_query_expansion
        do_rerank = rerank_results if rerank_results is not None else self.enable_reranking
        mode = search_mode if search_mode else self.hybrid_engine.search_mode

        expanded_queries = [query]
        if do_expand and self.query_expander:
            try:
                expanded = self.query_expander.expand(query)
                expanded_queries = [eq.text for eq in expanded.expanded_terms]
                logger.info(f"Query expanded to: {expanded_queries}")
            except Exception as e:
                logger.warning(f"Query expansion failed: {e}, using original query")
                expanded_queries = [query]

        all_candidates = []
        for eq in expanded_queries:
            search_query = SearchQuery(text=eq, filters=filters or {}, mode=mode, top_k=top_k)
            candidates = await self.hybrid_engine.search(search_query)
            all_candidates.extend(candidates)

        candidates_dict = {}
        for candidate in all_candidates:
            doc_id = candidate.document.id
            if doc_id not in candidates_dict:
                candidates_dict[doc_id] = candidate
            else:
                existing = candidates_dict[doc_id]
                existing.final_score = max(existing.final_score, candidate.final_score)
                existing.explanation.append(f"Combined from: {eq}")

        candidates = list(candidates_dict.values())
        candidates.sort(key=lambda x: x.final_score, reverse=True)

        candidates = candidates[: self.rerank_top_k]

        if do_rerank and self.reranker:
            try:
                search_results = [
                    SearchResult(
                        document=candidate.document,
                        similarity_score=candidate.vector_score,
                        keyword_score=candidate.keyword_score,
                        final_score=candidate.final_score,
                        rank=i + 1,
                        matched_content=candidate.matched_content,
                        match_explanation="; ".join(candidate.explanation),
                    )
                    for i, candidate in enumerate(candidates)
                ]

                reranked = self.reranker.rerank(query, search_results)

                for i, result in enumerate(reranked):
                    if i < len(candidates):
                        candidates[i].final_score = result.final_score
                        candidates[i].rank = result.rank
                        candidates[i].explanation.append(
                            f"Reranked score: {result.final_score:.3f}"
                        )

                candidates.sort(key=lambda x: x.final_score, reverse=True)
                logger.info(
                    f"Results reranked, top score: {candidates[0].final_score if candidates else 0}"
                )

            except Exception as e:
                logger.warning(f"Reranking failed: {e}, using original rankings")

        return candidates[:top_k]

    def set_reranker(self, reranker: Any) -> None:
        """Set or update the reranker."""
        self.reranker = reranker
        logger.info("Reranker updated")

    def set_query_expander(self, query_expander: Any) -> None:
        """Set or update the query expander."""
        self.query_expander = query_expander
        logger.info("Query expander updated")

    def enable_features(self, query_expansion: bool = None, reranking: bool = None) -> None:
        """Enable or disable features dynamically."""
        if query_expansion is not None:
            self.enable_query_expansion = query_expansion
            logger.info(f"Query expansion {'enabled' if query_expansion else 'disabled'}")

        if reranking is not None:
            self.enable_reranking = reranking
            logger.info(f"Reranking {'enabled' if reranking else 'disabled'}")