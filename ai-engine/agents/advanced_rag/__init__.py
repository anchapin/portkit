"""advanced_rag — Multi-modal retrieval-augmented generation agent.

Coordinator subpackage extracted from ``agents/advanced_rag_agent.py`` (32K)
for single-responsibility design. The public API is unchanged: existing code
can continue to import :class:`AdvancedRagAgent` and :class:`RAGResponse` from
``agents.advanced_rag_agent`` (the stub re-exports them) or, equivalently,
from ``agents.advanced_rag``.

Submodules:
    - :mod:`.query_router` — Query intent classification + routing
    - :mod:`.retrieval_orchestrator` — Multi-source retrieval coordination
    - :mod:`.result_fuser` — Reranking + token-budgeted context fusion
    - :mod:`.strategy_selector` — Fallback strategy + session context tracking
    - :mod:`.answer_synthesizer` — Answer generation + citation tracking

Issue #1709 — Subpackage split for advanced_rag_agent.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from schemas.multimodal_schema import ContentType, SearchResult
from search.hybrid_search_engine import HybridSearchEngine
from search.query_expansion import QueryExpansionEngine
from search.reranking_engine import EnsembleReRanker
from utils.advanced_chunker import AdvancedChunker
from utils.multimodal_embedding_generator import MultiModalEmbeddingGenerator
from utils.token_optimizer import ContextTrimmer
from utils.vector_db_client import VectorDBClient

from . import (
    answer_synthesizer,
    query_router,
    result_fuser,
    retrieval_orchestrator,
    strategy_selector,
)
from .answer_synthesizer import AnswerSynthesizer
from .query_router import (
    INTENT_EXAMPLE,
    INTENT_EXPLANATION,
    INTENT_GENERAL,
    INTENT_HOW_TO,
    QueryRouter,
    build_search_query,
    classify_query_intent,
    expand_search_query,
)
from .result_fuser import ResultFuser
from .retrieval_orchestrator import RetrievalOrchestrator
from .strategy_selector import StrategySelector

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    """Response from the Advanced RAG Agent."""

    answer: str
    sources: List[SearchResult]
    confidence: float
    processing_time_ms: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "answer": self.answer,
            "sources": [
                {
                    "document_id": source.document.id,
                    "title": source.document.source_path,
                    "content_preview": source.matched_content,
                    "relevance_score": source.final_score,
                    "rank": source.rank,
                }
                for source in self.sources
            ],
            "confidence": self.confidence,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
        }


class AdvancedRagAgent:
    """
    Advanced RAG agent with multi-modal search and intelligent retrieval.

    This agent combines multiple advanced techniques to provide high-quality
    retrieval-augmented generation for Minecraft modding queries.

    The class keeps the public surface of the original
    :class:`AdvancedRagAgent` (constructor signature, ``query``,
    ``get_session_context``, ``clear_session_context``,
    ``get_agent_status``, ``context_trimmer``, ``config``) while delegating
    per-stage work to stateless helpers in the subpackage's modules.
    """

    def __init__(
        self,
        vector_db_client: Optional[VectorDBClient] = None,
        enable_query_expansion: bool = True,
        enable_reranking: bool = True,
        enable_multimodal: bool = True,
    ):
        """
        Initialize the Advanced RAG Agent.

        Args:
            vector_db_client: Vector database client
            enable_query_expansion: Whether to enable query expansion
            enable_reranking: Whether to enable result re-ranking
            enable_multimodal: Whether to enable multi-modal capabilities
        """
        # Core components
        self.vector_db = vector_db_client or VectorDBClient()
        self.hybrid_search = HybridSearchEngine()
        self.embedding_generator = MultiModalEmbeddingGenerator()
        self.chunker = AdvancedChunker()

        # Optional components
        self.query_expander = QueryExpansionEngine() if enable_query_expansion else None
        self.reranker = EnsembleReRanker() if enable_reranking else None

        # Configuration
        self.enable_multimodal = enable_multimodal
        self.config = {
            "max_sources": 10,
            "min_relevance_threshold": 0.3,
            "answer_max_length": 2000,
            "context_window_size": 4000,
            "confidence_threshold": 0.6,
            "default_model": "default",
        }

        # Context trimming (token-based)
        self.context_trimmer = ContextTrimmer(model=self.config["default_model"])

        # Internal state
        self.document_cache: Dict[str, Any] = {}
        self.embedding_cache: Dict[str, Any] = {}
        self.session_contexts: Dict[str, Dict[str, Any]] = {}

        logger.info("Advanced RAG Agent initialized")

    async def query(
        self,
        query_text: str,
        content_types: Optional[List[ContentType]] = None,
        project_context: Optional[str] = None,
        session_id: str = "default",
        **kwargs,
    ) -> RAGResponse:
        """
        Process a query and generate an answer with sources.

        Args:
            query_text: The user's query
            content_types: Preferred content types to search
            project_context: Project context for filtering
            session_id: Session identifier for context
            **kwargs: Additional parameters

        Returns:
            RAG response with answer and sources
        """
        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"Processing RAG query: '{query_text[:100]}...'")

            # Stage 1 — query routing & optional expansion
            search_query = QueryRouter.build(
                query_text=query_text,
                content_types=content_types,
                project_context=project_context,
                config=self.config,
                reranker=self.reranker,
                query_expander=self.query_expander,
            )
            expanded_query = QueryRouter.expand(
                search_query=search_query,
                query_expander=self.query_expander,
                session_contexts=self.session_contexts,
                session_id=session_id,
                project_context=project_context,
            )

            # Stage 2 — multi-source retrieval
            search_results = await RetrievalOrchestrator.retrieve(
                query=search_query,
                embedding_generator=self.embedding_generator,
                hybrid_search=self.hybrid_search,
                document_cache=self.document_cache,
                embedding_cache=self.embedding_cache,
            )

            # Stage 3 — rerank + fuse into token-budgeted context
            search_results, reranking_metadata = ResultFuser.rerank(
                query=search_query,
                search_results=search_results,
                reranker=self.reranker,
                session_id=session_id,
            )
            combined_context, source_info, context_metadata = ResultFuser.build_context(
                sources=search_results,
                config=self.config,
                context_trimmer=self.context_trimmer,
                num_sources=5,
            )

            # Stage 4 — answer synthesis + citation tracking
            answer, confidence, generation_metadata = AnswerSynthesizer.synthesize(
                query=query_text,
                sources=search_results,
                config=self.config,
                context_trimmer=self.context_trimmer,
                combined_context=combined_context,
                source_info=source_info,
                context_metadata=context_metadata,
            )

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            response_metadata = {
                "query_expansion": {
                    "enabled": bool(self.query_expander),
                    "original_query": query_text,
                    "expanded_query": expanded_query.expanded_query
                    if expanded_query
                    else query_text,
                    "expansion_terms_count": len(expanded_query.expansion_terms)
                    if expanded_query
                    else 0,
                    "expansion_confidence": expanded_query.expansion_confidence
                    if expanded_query
                    else 0.0,
                },
                "retrieval": {
                    "total_results": len(search_results),
                    "search_mode": "hybrid",
                    "content_types_searched": content_types or ["all"],
                },
                "reranking": {"enabled": bool(self.reranker), **reranking_metadata},
                "generation": generation_metadata,
                "session_id": session_id,
                "timestamp": start_time.isoformat(),
            }

            response = RAGResponse(
                answer=answer,
                sources=search_results[:5],  # Top 5 sources
                confidence=confidence,
                processing_time_ms=processing_time,
                metadata=response_metadata,
            )

            StrategySelector.update(
                session_contexts=self.session_contexts,
                session_id=session_id,
                query=search_query,
                response=response,
                config=self.config,
            )

            logger.info(
                f"RAG query completed in {processing_time:.1f}ms with confidence {confidence:.2f}"
            )
            return response

        except Exception as e:
            logger.error(f"Error processing RAG query: {e}")
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return RAGResponse(
                answer=f"I apologize, but I encountered an error while processing your query: {str(e)}",
                sources=[],
                confidence=0.0,
                processing_time_ms=processing_time,
                metadata={"error": str(e), "timestamp": start_time.isoformat()},
            )

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get session context information."""
        return StrategySelector.get(self.session_contexts, session_id)

    async def clear_session_context(self, session_id: str) -> None:
        """Clear session context."""
        StrategySelector.clear(self.session_contexts, session_id)

    def get_agent_status(self) -> Dict[str, Any]:
        """Get current agent status and statistics."""
        return {
            "configuration": {
                "multimodal_enabled": self.enable_multimodal,
                "query_expansion_enabled": bool(self.query_expander),
                "reranking_enabled": bool(self.reranker),
                "max_sources": self.config["max_sources"],
                "confidence_threshold": self.config["confidence_threshold"],
            },
            "cache_status": {
                "documents_cached": len(self.document_cache),
                "embeddings_cached": len(self.embedding_cache),
                "active_sessions": len(self.session_contexts),
            },
            "capabilities": [
                "multi_modal_search",
                "hybrid_retrieval",
                "query_expansion",
                "result_reranking",
                "contextual_understanding",
                "session_awareness",
            ],
        }


# Alias to preserve the original public name. The original module declared
# the class as ``AdvancedRAGAgent``; the subpackage uses PEP-8 mixed case
# ``AdvancedRagAgent`` and exposes both spellings for backward compatibility.
AdvancedRAGAgent = AdvancedRagAgent


__all__ = [
    # Submodules
    "answer_synthesizer",
    "query_router",
    "result_fuser",
    "retrieval_orchestrator",
    "strategy_selector",
    # Helpers
    "AnswerSynthesizer",
    "QueryRouter",
    "ResultFuser",
    "RetrievalOrchestrator",
    "StrategySelector",
    "build_search_query",
    "classify_query_intent",
    "expand_search_query",
    "INTENT_HOW_TO",
    "INTENT_EXPLANATION",
    "INTENT_EXAMPLE",
    "INTENT_GENERAL",
    # Public API
    "RAGResponse",
    "AdvancedRagAgent",
    "AdvancedRAGAgent",
]
