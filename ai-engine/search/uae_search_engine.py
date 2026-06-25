"""
UAE (Utility-Aligned Embeddings) Search Engine for RAG Pipeline.

This module provides a UAE-aware search engine that replaces standard
similarity-based retrieval with utility-weighted embeddings trained
to maximize LLM usefulness for Bedrock API code generation.

Based on: "Aligning Dense Retrievers with LLM Utility via Distillation"
(Sandhu et al., https://arxiv.org/abs/2604.22722v1)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

import numpy as np

from schemas.multimodal_schema import MultiModalDocument, SearchQuery, SearchResult
from search.hybrid_search_engine import HybridSearchEngine, SearchMode, SearchCandidate
from utils.uae_retriever import UAERetriever, UAEConfig, create_uae_retriever
from utils.uae_utils import RetrievalBenchmark
from utils.embedding_generator import LocalEmbeddingGenerator

logger = logging.getLogger(__name__)


@dataclass
class UAESearchConfig:
    """Configuration for UAE-enhanced search."""

    use_uae: bool = True
    uae_config: Optional[UAEConfig] = None
    baseline_weight: float = 0.3
    uae_weight: float = 0.7
    min_utility_threshold: float = 0.3
    enable_utility_scoring: bool = True
    benchmark_interval: int = 100


class UAESearchEngine:
    """
    UAE-enhanced search engine that combines utility-aligned embeddings
    with standard similarity search for improved Bedrock API retrieval.

    This engine addresses the core problem: cosine similarity retrieves docs
    that LOOK similar but aren't useful for generating valid Bedrock code.
    UAE solves this by distilling utility signal from LLM perplexity/correctness
    into the retriever embeddings.
    """

    def __init__(
        self,
        config: Optional[UAESearchConfig] = None,
        hybrid_engine: Optional[HybridSearchEngine] = None,
        db_session: Optional[Any] = None,
    ):
        self.config = config or UAESearchConfig()
        self.hybrid_engine = hybrid_engine or HybridSearchEngine(db_session=db_session)

        self._uae_retriever: Optional[UAERetriever] = None
        self._embedding_generator = LocalEmbeddingGenerator()
        self._is_fine_tuned = False
        self._search_count = 0
        self._baseline_metrics: List[RetrievalBenchmark] = []
        self._uae_metrics: List[RetrievalBenchmark] = []

        if self.config.use_uae:
            self._init_uae_retriever()

        logger.info(
            f"UAESearchEngine initialized with UAE={'enabled' if self.config.use_uae else 'disabled'}"
        )

    def _init_uae_retriever(self) -> None:
        """Initialize the UAE retriever."""
        uae_config = self.config.uae_config or UAEConfig()
        self._uae_retriever = create_uae_retriever(
            config=uae_config,
            embedding_generator=self._embedding_generator,
        )
        logger.info(f"UAE retriever initialized with base model: {uae_config.base_model}")

    def compute_utility_similarity(
        self,
        query_embedding: np.ndarray,
        doc_embedding: np.ndarray,
        utility_weight: float = 1.0,
    ) -> float:
        """
        Compute utility-weighted similarity score.

        Unlike standard cosine similarity, this incorporates the utility
        weight learned during fine-tuning to prioritize docs that lead
        to successful conversions.
        """
        if self._uae_retriever:
            return self._uae_retriever.compute_utility_score(
                query_embedding, doc_embedding, utility_weight
            )

        base_similarity = np.dot(query_embedding, doc_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding) + 1e-8
        )
        return float(base_similarity)

    async def search(
        self,
        query: SearchQuery,
        documents: Dict[str, MultiModalDocument],
        embeddings: Dict[str, List],
        query_embedding: List[float],
        search_mode: SearchMode = SearchMode.HYBRID,
        user_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Perform UAE-enhanced search across documents.

        Args:
            query: Search query with parameters
            documents: Available documents to search
            embeddings: Document embeddings
            query_embedding: Query embedding vector
            search_mode: Search mode to use
            user_id: Optional user ID for personalized feedback

        Returns:
            Ranked list of search results with utility-aware scoring
        """
        self._search_count += 1

        if not self.config.use_uae or not self._uae_retriever:
            return await self.hybrid_engine.search(
                query=query,
                documents=documents,
                embeddings=embeddings,
                query_embedding=query_embedding,
                search_mode=search_mode,
                user_id=user_id,
            )

        candidates = []
        query_vec = np.array(query_embedding)
        query_keywords = self.hybrid_engine.keyword_engine.extract_keywords(query.query_text)

        for doc_id, document in documents.items():
            if not self._passes_filters(document, query):
                continue

            candidate = SearchCandidate(document=document)
            doc_emb = embeddings.get(doc_id, [])

            if doc_emb and query_embedding:
                base_similarity = self._calculate_vector_similarity(query_embedding, doc_emb)
                candidate.vector_score = base_similarity

                if self._is_fine_tuned and self.config.enable_utility_scoring:
                    doc_vec = np.array(doc_emb[0]) if len(doc_emb) > 0 else None
                    if doc_vec is not None:
                        utility_weight = self._estimate_utility_weight(query.query_text, doc_id)
                        candidate.semantic_score = self.compute_utility_similarity(
                            query_vec, doc_vec, utility_weight
                        )
                        candidate.explanation.append(
                            f"UAE utility score: {candidate.semantic_score:.3f} (weight={utility_weight:.2f})"
                        )
                else:
                    candidate.semantic_score = base_similarity

            if document.content_text:
                keyword_score, keyword_explanation = (
                    self.hybrid_engine.keyword_engine.calculate_keyword_similarity(
                        query_keywords, document.content_text
                    )
                )
                candidate.keyword_score = keyword_score
                candidate.explanation.append(f"Keyword score: {keyword_score:.3f}")

            candidate.context_score = self._calculate_context_score(document, query)
            if candidate.context_score > 0:
                candidate.explanation.append(f"Context bonus: {candidate.context_score:.3f}")

            self._score_candidate(candidate, is_uae=self._is_fine_tuned)
            candidates.append(candidate)

        candidates.sort(key=lambda x: x.final_score, reverse=True)

        results = []
        for i, candidate in enumerate(candidates[: query.top_k]):
            result = SearchResult(
                document=candidate.document,
                similarity_score=candidate.vector_score,
                keyword_score=candidate.keyword_score,
                final_score=candidate.final_score,
                rank=i + 1,
                embedding_model_used="UAE-all-MiniLM-L6-v2"
                if self._is_fine_tuned
                else "all-MiniLM-L6-v2",
                matched_content=candidate.document.content_text[:200]
                if candidate.document.content_text
                else None,
                match_explanation="; ".join(candidate.explanation),
            )
            results.append(result)

        logger.info(f"UAE search returned {len(results)} results (search #{self._search_count})")
        return results

    def _calculate_vector_similarity(
        self, query_embedding: List[float], doc_embeddings: List
    ) -> float:
        """Calculate vector similarity score."""
        if not doc_embeddings:
            return 0.0

        max_similarity = 0.0
        query_vector = np.array(query_embedding)

        if (
            doc_embeddings
            and not hasattr(doc_embeddings[0], "embedding")
            and not hasattr(doc_embeddings[0], "embedding_vector")
        ):
            doc_vector = np.array(doc_embeddings)
            if doc_vector.size > 0 and query_vector.shape[0] == doc_vector.shape[0]:
                dot_product = np.dot(query_vector, doc_vector)
                norm_query = np.linalg.norm(query_vector)
                norm_doc = np.linalg.norm(doc_vector)
                if norm_query > 0 and norm_doc > 0:
                    return dot_product / (norm_query * norm_doc)
            return 0.0

        for embedding_data in doc_embeddings:
            if hasattr(embedding_data, "embedding"):
                doc_vector = np.array(embedding_data.embedding)
            elif hasattr(embedding_data, "embedding_vector"):
                doc_vector = np.array(embedding_data.embedding_vector)
            else:
                doc_vector = np.array(embedding_data)

            if doc_vector.size == 0 or query_vector.shape[0] != doc_vector.shape[0]:
                continue

            dot_product = np.dot(query_vector, doc_vector)
            norm_query = np.linalg.norm(query_vector)
            norm_doc = np.linalg.norm(doc_vector)

            if norm_query > 0 and norm_doc > 0:
                similarity = dot_product / (norm_query * norm_doc)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _estimate_utility_weight(self, query: str, doc_id: str) -> float:
        """
        Estimate utility weight for query-document pair.

        In production, this would be learned from conversion history.
        For now, we use heuristic based on query characteristics.
        """
        query_lower = query.lower()
        utility_indicators = [
            "api",
            "script",
            "command",
            "event",
            "handler",
            "entity",
            "block",
            "item",
            "component",
            "module",
        ]

        indicator_count = sum(1 for ind in utility_indicators if ind in query_lower)

        if indicator_count >= 3:
            return 0.9
        elif indicator_count >= 1:
            return 0.7
        else:
            return 0.5

    def _score_candidate(self, candidate: SearchCandidate, is_uae: bool = False) -> None:
        """Score a candidate document."""
        if is_uae:
            vector_weight = self.config.uae_weight
            semantic_weight = self.config.uae_weight * 0.8
            keyword_weight = self.config.baseline_weight
        else:
            vector_weight = 0.7
            semantic_weight = 0.0
            keyword_weight = 0.3

        context_weight = 0.1

        candidate.final_score = (
            vector_weight * candidate.vector_score
            + semantic_weight * candidate.semantic_score
            + keyword_weight * candidate.keyword_score
            + context_weight * candidate.context_score
        )

        candidate.explanation.append(
            f"Final: {candidate.final_score:.3f} = "
            f"{vector_weight:.1f}*{candidate.vector_score:.3f} + "
            f"{keyword_weight:.1f}*{candidate.keyword_score:.3f} + "
            f"{context_weight:.1f}*{candidate.context_score:.3f}"
        )

    def _passes_filters(self, document: MultiModalDocument, query: SearchQuery) -> bool:
        """Check if document passes query filters."""
        if query.content_types and document.content_type not in query.content_types:
            return False

        if query.tags and not any(tag in document.tags for tag in query.tags):
            return False

        if query.project_context and document.project_context != query.project_context:
            return False

        return True

    def _calculate_context_score(self, document: MultiModalDocument, query: SearchQuery) -> float:
        """Calculate context-aware relevance score."""
        context_score = 0.0

        if document.content_metadata:
            metadata = document.content_metadata

            if query.query_context:
                query_context_lower = query.query_context.lower()
                for key, value in metadata.items():
                    if isinstance(value, str) and query_context_lower in value.lower():
                        context_score += 0.1

            if "minecraft_version" in metadata or "mod_loader" in metadata:
                context_score += 0.05

            if "class_name" in metadata or "method_name" in metadata:
                context_score += 0.05

        return min(context_score, 0.3)

    def fine_tune(
        self,
        training_pairs: List[Any],
        document_contents: Dict[str, str],
        validation_pairs: Optional[List[Any]] = None,
        progress_callback: Optional[Callable[[int, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Fine-tune the UAE retriever using utility-aligned contrastive learning.

        Args:
            training_pairs: Training pairs with utility labels
            document_contents: Dict mapping doc_id to content
            validation_pairs: Optional validation pairs
            progress_callback: Optional callback(epoch, loss)

        Returns:
            Training metrics
        """
        if not self._uae_retriever:
            logger.warning("UAE retriever not initialized")
            return {"status": "no_retriever"}

        metrics = self._uae_retriever.fine_tune(
            training_pairs=training_pairs,
            document_contents=document_contents,
            validation_pairs=validation_pairs,
            progress_callback=progress_callback,
        )

        self._is_fine_tuned = self._uae_retriever.is_fine_tuned
        logger.info(f"UAE fine-tuning completed: {metrics.get('status', 'unknown')}")

        return metrics

    def benchmark(
        self,
        test_queries: List[str],
        retrieved_docs: Dict[str, List[str]],
        useful_docs: Dict[str, List[str]],
        use_uae: bool = True,
    ) -> RetrievalBenchmark:
        """
        Benchmark retrieval performance.

        Args:
            test_queries: List of test queries
            retrieved_docs: Retrieved doc IDs per query
            useful_docs: Actually useful doc IDs per query
            use_uae: Whether to use UAE scoring

        Returns:
            Benchmark metrics
        """
        if use_uae and self._uae_retriever:
            benchmark = self._uae_retriever.benchmark_retrieval(
                test_queries=test_queries,
                retrieved_docs=retrieved_docs,
                useful_docs=useful_docs,
            )
            self._uae_metrics.append(benchmark)
        else:
            from utils.uae_utils import RetrievalBenchmarker

            benchmarker = RetrievalBenchmarker(k=5)
            benchmark = benchmarker.benchmark(
                queries=test_queries,
                retrieved_docs_per_query=retrieved_docs,
                useful_docs_per_query=useful_docs,
            )
            self._baseline_metrics.append(benchmark)

        return benchmark

    def compare_uae_vs_baseline(self) -> Dict[str, Any]:
        """
        Compare UAE vs baseline retrieval performance.

        Returns:
            Comparison metrics showing improvement from UAE
        """
        if not self._baseline_metrics or not self._uae_metrics:
            return {"status": "insufficient_data"}

        baseline = self._baseline_metrics[-1]
        uae = self._uae_metrics[-1]

        precision_improvement = (
            ((uae.precision_at_k - baseline.precision_at_k) / baseline.precision_at_k * 100)
            if baseline.precision_at_k > 0
            else 0
        )
        recall_improvement = (
            ((uae.recall_at_k - baseline.recall_at_k) / baseline.recall_at_k * 100)
            if baseline.recall_at_k > 0
            else 0
        )
        mrr_improvement = ((uae.mrr - baseline.mrr) / baseline.mrr * 100) if baseline.mrr > 0 else 0

        return {
            "baseline": baseline.to_dict(),
            "uae": uae.to_dict(),
            "improvement": {
                "precision_at_5": f"+{precision_improvement:.1f}%",
                "recall_at_5": f"+{recall_improvement:.1f}%",
                "mrr": f"+{mrr_improvement:.1f}%",
            },
            "status": "compared",
        }

    @property
    def is_fine_tuned(self) -> bool:
        """Check if the retriever has been fine-tuned."""
        return self._is_fine_tuned

    def get_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        stats = {
            "uae_enabled": self.config.use_uae,
            "is_fine_tuned": self._is_fine_tuned,
            "search_count": self._search_count,
            "baseline_metrics_count": len(self._baseline_metrics),
            "uae_metrics_count": len(self._uae_metrics),
        }

        if self._uae_retriever:
            stats["training_history"] = self._uae_retriever.training_history

        return stats
