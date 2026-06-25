"""
Hybrid search engine combining vector similarity and keyword-based search.

Extracted from the original ``hybrid_search_engine.py`` (issue #1741).
This module provides the HybridSearchEngine that fuses dense+sparse retrieval
and is independent of the unified routing layer in unified_engine.py.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from schemas.multimodal_schema import MultiModalDocument, SearchQuery, SearchResult
from search.search_types import RankingStrategy, SearchCandidate, SearchMode

logger = logging.getLogger(__name__)

try:
    from search.feedback_reranker import FeedbackReranker

    FEEDBACK_RERANKER_AVAILABLE = True
except ImportError:
    FEEDBACK_RERANKER_AVAILABLE = False
    logger.warning("FeedbackReranker not available")


class HybridSearchEngine:
    """
    Main hybrid search engine that combines vector and keyword search.

    This engine provides sophisticated search capabilities by combining
    semantic vector similarity with keyword-based relevance scoring.
    """

    def __init__(self, db_session=None):
        from search.keyword_engine import KeywordSearchEngine

        self.keyword_engine = KeywordSearchEngine()
        self.ranking_strategies = {
            RankingStrategy.WEIGHTED_SUM: self._weighted_sum_ranking,
            RankingStrategy.RECIPROCAL_RANK_FUSION: self._reciprocal_rank_fusion,
            RankingStrategy.BAYESIAN_COMBINATION: self._bayesian_combination,
        }
        self._bm25_built = False
        self._db_session = db_session
        self._feedback_reranker = None
        if db_session and FEEDBACK_RERANKER_AVAILABLE:
            self._feedback_reranker = FeedbackReranker(db_session=db_session)

    def build_index(self, documents: Dict[str, MultiModalDocument]) -> bool:
        """
        Build search indexes for the documents.

        Args:
            documents: Dictionary of document_id to MultiModalDocument

        Returns:
            True if index was built successfully
        """
        self._bm25_built = self.keyword_engine.build_bm25_index(documents)
        if self._bm25_built:
            logger.info("BM25 index built successfully")
        else:
            logger.warning("Failed to build BM25 index, will use basic keyword search")

        return True

    async def search(  # noqa: C901
        self,
        query: SearchQuery,
        documents: Dict[str, MultiModalDocument],
        embeddings: Dict[str, List],
        query_embedding: List[float],
        search_mode: SearchMode = SearchMode.HYBRID,
        ranking_strategy: RankingStrategy = RankingStrategy.WEIGHTED_SUM,
        use_feedback_boost: bool = True,
        user_id: Optional[str] = None,
        include_related: bool = True,
    ) -> List[SearchResult]:
        """
        Perform hybrid search across documents.

        Args:
            query: Search query with parameters
            documents: Available documents to search
            embeddings: Document embeddings
            query_embedding: Query embedding vector
            search_mode: Search mode to use
            ranking_strategy: Ranking strategy for combining scores
            use_feedback_boost: Whether to apply feedback-based re-ranking
            user_id: Optional user ID for personalized feedback
            include_related: Whether to include related concepts in results

        Returns:
            Ranked list of search results
        """
        logger.info(f"Performing {search_mode} search for: {query.query_text}")

        if search_mode in [SearchMode.KEYWORD_ONLY, SearchMode.HYBRID, SearchMode.ADAPTIVE]:
            if not self._bm25_built:
                logger.info("Building BM25 index on first search...")
                self.build_index(documents)

        candidates = []
        query_keywords = self.keyword_engine.extract_keywords(query.query_text)

        for doc_id, document in documents.items():
            if not self._passes_filters(document, query):
                continue

            candidate = SearchCandidate(document=document)

            if search_mode in [SearchMode.VECTOR_ONLY, SearchMode.HYBRID, SearchMode.ADAPTIVE]:
                doc_embeddings = embeddings.get(doc_id, [])
                if doc_embeddings and query_embedding:
                    candidate.vector_score = self._calculate_vector_similarity(
                        query_embedding, doc_embeddings
                    )
                    candidate.explanation.append(f"Vector similarity: {candidate.vector_score:.3f}")

            if search_mode in [SearchMode.KEYWORD_ONLY, SearchMode.HYBRID, SearchMode.ADAPTIVE]:
                if document.content_text:
                    if self.keyword_engine._bm25_index is not None:
                        bm25_results = self.keyword_engine.search_bm25(
                            query.query_text, documents, top_k=len(documents)
                        )
                        doc_bm25_score = 0.0
                        for result_doc_id, score in bm25_results:
                            if result_doc_id == doc_id:
                                doc_bm25_score = score
                                break
                        candidate.keyword_score = doc_bm25_score
                        candidate.explanation.append(f"BM25 score: {doc_bm25_score:.3f}")
                    else:
                        keyword_score, keyword_explanation = (
                            self.keyword_engine.calculate_keyword_similarity(
                                query_keywords, document.content_text
                            )
                        )
                        candidate.keyword_score = keyword_score
                        candidate.explanation.append(f"Keyword similarity: {keyword_score:.3f}")
                        candidate.explanation.append(
                            f"Matched terms: {len(keyword_explanation.get('matched_terms', []))}"
                        )

            should_skip = False

            if search_mode == SearchMode.VECTOR_ONLY:
                doc_embeddings = embeddings.get(doc_id, [])
                if not doc_embeddings:
                    should_skip = True

            elif search_mode == SearchMode.KEYWORD_ONLY:
                if not document.content_text:
                    should_skip = True

            if not should_skip:
                has_vector_score = search_mode != SearchMode.KEYWORD_ONLY and embeddings.get(
                    doc_id, []
                )
                has_keyword_score = search_mode != SearchMode.VECTOR_ONLY and document.content_text

                if search_mode in [SearchMode.HYBRID, SearchMode.ADAPTIVE]:
                    if candidate.vector_score < 0.01 and candidate.keyword_score == 0:
                        should_skip = True
                elif search_mode == SearchMode.VECTOR_ONLY:
                    if not has_vector_score or candidate.vector_score < 0.01:
                        should_skip = True
                elif search_mode == SearchMode.KEYWORD_ONLY:
                    if not has_keyword_score:
                        should_skip = True

            if should_skip:
                continue

            candidate.context_score = self._calculate_context_score(document, query)
            if candidate.context_score > 0:
                candidate.explanation.append(f"Context bonus: {candidate.context_score:.3f}")

            candidates.append(candidate)

        ranked_candidates = self.ranking_strategies[ranking_strategy](
            candidates, query, search_mode
        )

        results = []
        for i, candidate in enumerate(ranked_candidates[: query.top_k]):
            result = SearchResult(
                document=candidate.document,
                similarity_score=candidate.vector_score,
                keyword_score=candidate.keyword_score,
                final_score=candidate.final_score,
                rank=i + 1,
                embedding_model_used="sentence-transformers/all-MiniLM-L6-v2",
                matched_content=candidate.document.content_text[:200]
                if candidate.document.content_text
                else None,
                match_explanation="; ".join(candidate.explanation),
            )
            results.append(result)

        if include_related and self._db_session:
            try:
                from knowledge.cross_reference import CrossReferenceDetector

                detector = CrossReferenceDetector(db_session=self._db_session)
                await detector.initialize(self._db_session)

                for result in results:
                    doc_id = result.document.id
                    related = await detector.find_related_chunks(
                        chunk_id=doc_id,
                        limit=5,
                    )
                    if related:
                        if not hasattr(result, "metadata"):
                            result.metadata = {}
                        result.metadata["related_concepts"] = related

                logger.info(f"Added related concepts to {len(results)} results")
            except Exception as e:
                logger.warning(f"Failed to add related concepts: {e}")

        if use_feedback_boost and FEEDBACK_RERANKER_AVAILABLE:
            try:
                if self._feedback_reranker:
                    results = await self._feedback_reranker.rerank_with_feedback(
                        query.query_text, results, user_id
                    )
                else:
                    feedback_reranker = FeedbackReranker()
                    results = await feedback_reranker.rerank_with_feedback(
                        query.query_text, results, user_id
                    )
                logger.info("Applied feedback-based re-ranking")
            except Exception as e:
                logger.warning(f"Feedback re-ranking failed: {e}")

        logger.info(f"Returning {len(results)} results")
        return results

    def _passes_filters(self, document: MultiModalDocument, query: SearchQuery) -> bool:
        """Check if document passes the query filters."""
        if query.content_types and document.content_type not in query.content_types:
            return False

        if query.tags and not any(tag in document.tags for tag in query.tags):
            return False

        if query.project_context and document.project_context != query.project_context:
            return False

        if query.date_range:
            pass

        return True

    def _calculate_vector_similarity(
        self, query_embedding: List[float], doc_embeddings: List
    ) -> float:
        """Calculate the best vector similarity score for a document."""
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

        if hasattr(document, "updated_at") and document.updated_at:
            from datetime import datetime, timedelta, timezone

            doc_time = document.updated_at
            if doc_time.tzinfo is None:
                doc_time = doc_time.replace(tzinfo=timezone.utc)

            if doc_time > datetime.now(timezone.utc) - timedelta(days=30):
                context_score += 0.02

        return min(context_score, 0.3)

    def _weighted_sum_ranking(
        self, candidates: List[SearchCandidate], query: SearchQuery, search_mode: SearchMode
    ) -> List[SearchCandidate]:
        """Rank candidates using weighted sum of scores."""
        vector_weight = 0.7
        keyword_weight = 0.3
        context_weight = 0.1

        if search_mode == SearchMode.VECTOR_ONLY:
            vector_weight, keyword_weight = 1.0, 0.0
        elif search_mode == SearchMode.KEYWORD_ONLY:
            vector_weight, keyword_weight = 0.0, 1.0
        elif search_mode == SearchMode.ADAPTIVE:
            query_length = len(query.query_text.split())
            if query_length <= 3:
                vector_weight, keyword_weight = 0.5, 0.5
            else:
                vector_weight, keyword_weight = 0.8, 0.2

        for candidate in candidates:
            candidate.final_score = (
                vector_weight * candidate.vector_score
                + keyword_weight * candidate.keyword_score
                + context_weight * candidate.context_score
            )

            candidate.explanation.append(
                f"Final: {candidate.final_score:.3f} = "
                f"{vector_weight}*{candidate.vector_score:.3f} + "
                f"{keyword_weight}*{candidate.keyword_score:.3f} + "
                f"{context_weight}*{candidate.context_score:.3f}"
            )

        candidates.sort(key=lambda x: x.final_score, reverse=True)
        return candidates

    def _reciprocal_rank_fusion(
        self, candidates: List[SearchCandidate], query: SearchQuery, search_mode: SearchMode
    ) -> List[SearchCandidate]:
        """Rank candidates using Reciprocal Rank Fusion."""
        vector_ranking = sorted(candidates, key=lambda x: x.vector_score, reverse=True)
        keyword_ranking = sorted(candidates, key=lambda x: x.keyword_score, reverse=True)
        context_ranking = sorted(candidates, key=lambda x: x.context_score, reverse=True)

        k = 60
        candidate_scores = defaultdict(float)

        for i, candidate in enumerate(vector_ranking):
            candidate_scores[candidate.document.id] += 1.0 / (k + i + 1)

        for i, candidate in enumerate(keyword_ranking):
            candidate_scores[candidate.document.id] += 1.0 / (k + i + 1)

        for i, candidate in enumerate(context_ranking):
            candidate_scores[candidate.document.id] += 0.5 / (k + i + 1)

        for candidate in candidates:
            candidate.final_score = candidate_scores[candidate.document.id]
            candidate.explanation.append(f"RRF score: {candidate.final_score:.3f}")

        candidates.sort(key=lambda x: x.final_score, reverse=True)
        return candidates

    def _bayesian_combination(
        self, candidates: List[SearchCandidate], query: SearchQuery, search_mode: SearchMode
    ) -> List[SearchCandidate]:
        """Rank candidates using Bayesian score combination."""
        prior_relevance = 0.1

        for candidate in candidates:
            vector_likelihood = candidate.vector_score
            keyword_likelihood = candidate.keyword_score
            context_likelihood = candidate.context_score if candidate.context_score > 0 else 0.1

            combined_likelihood = vector_likelihood * keyword_likelihood * context_likelihood

            candidate.final_score = combined_likelihood * prior_relevance
            candidate.explanation.append(f"Bayesian score: {candidate.final_score:.3f}")

        candidates.sort(key=lambda x: x.final_score, reverse=True)
        return candidates
