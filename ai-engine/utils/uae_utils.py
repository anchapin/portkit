"""
Utility-Aligned Embedding (UAE) Module.

This module implements UAE embeddings trained to maximize LLM usefulness
of retrieved documents, not just vector similarity. Based on:
"Aligning Dense Retrievers with LLM Utility via Distillation"
(Sandhu et al., https://arxiv.org/abs/2604.22722v1)

The core idea: standard similarity-based retrieval retrieves documents that
*look* similar to a query but aren't the ones that produce valid outputs.
UAE solves this by distilling a utility signal from LLM perplexity/correctness
into the retriever embeddings.
"""

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


class UtilitySignal(str, Enum):
    """Source of utility signal for training."""

    CORRECT_CONVERSION = "correct_conversion"
    INCORRECT_CONVERSION = "incorrect_conversion"
    LLM_PERPLEXITY = "llm_perplexity"
    HUMAN_FEEDBACK = "human_feedback"
    VALIDATION_PASS = "validation_pass"
    VALIDATION_FAIL = "validation_fail"


@dataclass
class UtilityLabel:
    """Utility label for a query-document pair."""

    query_id: str
    document_id: str
    utility_score: float
    signal_source: UtilitySignal
    metadata: Dict[str, Any]

    def is_positive(self) -> bool:
        return self.utility_score > 0.5


@dataclass
class UAETrainingPair:
    """A training pair for UAE fine-tuning."""

    query: str
    positive_docs: List[str]
    negative_docs: List[str]
    utility_labels: List[UtilityLabel]
    query_id: str = ""

    def __post_init__(self):
        if not self.query_id:
            self.query_id = hashlib.md5(self.query.encode()).hexdigest()[:8]


class UtilityLabelCalculator:
    """
    Calculates utility labels from conversion history.

    A document has high utility for a query if it was actually used
    in a successful conversion output.
    """

    def __init__(self, positive_weight: float = 1.0, negative_weight: float = -0.5):
        self.positive_weight = positive_weight
        self.negative_weight = negative_weight

    def calculate_from_conversion_history(
        self,
        query: str,
        retrieved_doc_ids: List[str],
        conversion_output: str,
        conversion_successful: bool,
    ) -> List[UtilityLabel]:
        """
        Calculate utility labels based on conversion history.

        A document is "useful" if it appears in the correct conversion output.
        """
        labels = []

        if conversion_successful:
            for doc_id in retrieved_doc_ids:
                doc_in_output = self._doc_appears_in_output(doc_id, conversion_output)
                utility = self.positive_weight if doc_in_output else 0.0
                labels.append(
                    UtilityLabel(
                        query_id=self._hash_query(query),
                        document_id=doc_id,
                        utility_score=utility,
                        signal_source=(
                            UtilitySignal.CORRECT_CONVERSION
                            if doc_in_output
                            else UtilitySignal.VALIDATION_PASS
                        ),
                        metadata={
                            "conversion_successful": True,
                            "doc_in_output": doc_in_output,
                        },
                    )
                )
        else:
            for doc_id in retrieved_doc_ids:
                labels.append(
                    UtilityLabel(
                        query_id=self._hash_query(query),
                        document_id=doc_id,
                        utility_score=self.negative_weight,
                        signal_source=UtilitySignal.VALIDATION_FAIL,
                        metadata={"conversion_successful": False},
                    )
                )

        return labels

    def calculate_from_llm_perplexity(
        self,
        query: str,
        doc_content: str,
        perplexity_score: float,
    ) -> UtilityLabel:
        """
        Calculate utility based on LLM perplexity when the doc is used.

        Lower perplexity = higher utility (the doc helped the LLM generate better output).
        """
        normalized_utility = 1.0 - min(perplexity_score, 1.0)

        return UtilityLabel(
            query_id=self._hash_query(query),
            document_id=self._hash_content(doc_content[:100]),
            utility_score=normalized_utility,
            signal_source=UtilitySignal.LLM_PERPLEXITY,
            metadata={"perplexity_score": perplexity_score},
        )

    def _hash_query(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()[:12]

    def _hash_content(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _doc_appears_in_output(self, doc_id: str, output: str) -> bool:
        if not output:
            return False
        return doc_id in output or len(output) > 50


class ContrastiveUtilityLoss:
    """
    Contrastive loss weighted by utility scores for UAE training.

    Unlike standard contrastive loss which treats all positives equally,
    this loss gives higher weight to documents with higher utility scores.
    """

    def __init__(self, margin: float = 0.5, temperature: float = 0.1):
        self.margin = margin
        self.temperature = temperature

    def compute(
        self,
        anchor_embedding: np.ndarray,
        positive_embeddings: List[np.ndarray],
        negative_embeddings: List[np.ndarray],
        utility_weights: List[float],
    ) -> float:
        """
        Compute utility-weighted contrastive loss.

        Args:
            anchor_embedding: Query embedding
            positive_embeddings: Embeddings of positive (useful) documents
            negative_embeddings: Embeddings of negative (useless) documents
            utility_weights: Utility score for each positive (0-1 range)

        Returns:
            Loss value
        """
        if not positive_embeddings or not negative_embeddings:
            return 0.0

        pos_emb = np.array(positive_embeddings)
        neg_emb = np.array(negative_embeddings)
        weights = np.array(utility_weights)

        pos_similarities = self._cosine_similarity_batch(anchor_embedding, pos_emb)
        neg_similarities = self._cosine_similarity_batch(anchor_embedding, neg_emb)

        pos_exp = np.exp(pos_similarities / self.temperature)
        neg_exp = np.exp(neg_similarities / self.temperature)

        weighted_pos = np.sum(weights * pos_exp)
        total_exp = weighted_pos + np.sum(neg_exp)

        loss = -np.log(weighted_pos / (total_exp + 1e-8))

        for i, pos_sim in enumerate(pos_similarities):
            for neg_sim in neg_similarities:
                diff = neg_sim - pos_sim + self.margin
                if diff > 0:
                    loss += diff

        return float(loss)

    def _cosine_similarity_batch(self, anchor: np.ndarray, targets: np.ndarray) -> np.ndarray:
        anchor_norm = anchor / (np.linalg.norm(anchor) + 1e-8)
        targets_norm = targets / (np.linalg.norm(targets, axis=1, keepdims=True) + 1e-8)
        return np.dot(targets_norm, anchor_norm)


class UAEEarlyStopping:
    """Early stopping for UAE training based on retrieval metrics."""

    def __init__(
        self,
        patience: int = 3,
        min_improvement: float = 0.01,
        metric: str = "precision_at_5",
    ):
        self.patience = patience
        self.min_improvement = min_improvement
        self.metric = metric
        self.best_score = 0.0
        self.counter = 0
        self.best_epoch = 0

    def should_stop(self, current_score: float, current_epoch: int) -> bool:
        """Check if training should stop."""
        if current_score > self.best_score + self.min_improvement:
            self.best_score = current_score
            self.counter = 0
            self.best_epoch = current_epoch
            return False

        self.counter += 1
        if self.counter >= self.patience:
            return True

        return False


@dataclass
class RetrievalBenchmark:
    """Benchmark metrics for retrieval evaluation."""

    precision_at_k: float
    recall_at_k: float
    mrr: float
    ndcg: float
    total_queries: int
    useful_docs_retrieved: int
    total_useful_docs: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "precision_at_5": self.precision_at_k,
            "recall_at_5": self.recall_at_k,
            "mrr": self.mrr,
            "ndcg": self.ndcg,
            "total_queries": self.total_queries,
            "useful_docs_retrieved": self.useful_docs_retrieved,
            "total_useful_docs": self.total_useful_docs,
        }


class RetrievalBenchmarker:
    """Benchmark current retriever to establish baseline for UAE improvement."""

    def __init__(self, k: int = 5):
        self.k = k
        self.results: List[RetrievalBenchmark] = []

    def benchmark(
        self,
        queries: List[str],
        retrieved_docs_per_query: Dict[str, List[str]],
        useful_docs_per_query: Dict[str, List[str]],
    ) -> RetrievalBenchmark:
        """
        Calculate retrieval metrics.

        Args:
            queries: List of queries
            retrieved_docs_per_query: Dict mapping query to retrieved doc IDs
            useful_docs_per_query: Dict mapping query to actually useful doc IDs
        """
        total_precision = 0.0
        total_recall = 0.0
        total_mrr = 0.0
        total_ndcg = 0.0
        total_useful_retrieved = 0
        total_useful = 0

        for query in queries:
            retrieved = set(retrieved_docs_per_query.get(query, [])[: self.k])
            useful = set(useful_docs_per_query.get(query, []))

            if not useful:
                continue

            retrieved_useful = retrieved & useful
            precision = len(retrieved_useful) / len(retrieved) if retrieved else 0.0
            recall = len(retrieved_useful) / len(useful) if useful else 0.0

            rr = 0.0
            for i, doc in enumerate(retrieved_docs_per_query.get(query, [])[: self.k]):
                if doc in useful:
                    rr = 1.0 / (i + 1)
                    break

            ndcg = self._ndcg_at_k(retrieved, useful, self.k)

            total_precision += precision
            total_recall += recall
            total_mrr += rr
            total_ndcg += ndcg
            total_useful_retrieved += len(retrieved_useful)
            total_useful += len(useful)

        n = len(queries)
        avg_precision = total_precision / n if n > 0 else 0.0
        avg_recall = total_recall / n if n > 0 else 0.0
        avg_mrr = total_mrr / n if n > 0 else 0.0
        avg_ndcg = total_ndcg / n if n > 0 else 0.0

        benchmark = RetrievalBenchmark(
            precision_at_k=avg_precision,
            recall_at_k=avg_recall,
            mrr=avg_mrr,
            ndcg=avg_ndcg,
            total_queries=n,
            useful_docs_retrieved=total_useful_retrieved,
            total_useful_docs=total_useful,
        )

        self.results.append(benchmark)
        return benchmark

    def _ndcg_at_k(self, retrieved: set, useful: set, k: int) -> float:
        """Calculate NDCG@k."""
        dcg = 0.0
        for i, doc in enumerate(list(retrieved)[:k]):
            if doc in useful:
                dcg += 1.0 / np.log2(i + 2)

        idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(useful), k)))

        return dcg / idcg if idcg > 0 else 0.0


def normalize_utility_scores(labels: List[UtilityLabel]) -> List[UtilityLabel]:
    """Normalize utility scores to 0-1 range."""
    if not labels:
        return labels

    scores = [label.utility_score for label in labels]
    min_score = min(scores)
    max_score = max(scores)

    if max_score - min_score < 1e-8:
        return labels

    normalized = []
    for label in labels:
        normalized_score = (label.utility_score - min_score) / (max_score - min_score)
        normalized.append(
            UtilityLabel(
                query_id=label.query_id,
                document_id=label.document_id,
                utility_score=normalized_score,
                signal_source=label.signal_source,
                metadata=label.metadata,
            )
        )

    return normalized
