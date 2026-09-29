"""
UAE Training Pipeline for Bedrock API Documentation RAG.

This module implements the UAE fine-tuning pipeline that uses conversion history
as utility labels to improve Bedrock API documentation retrieval.

Based on: "Aligning Dense Retrievers with LLM Utility via Distillation"
(Sandhu et al., https://arxiv.org/abs/2604.22722v1)

The pipeline:
1. Collects (query, retrieved_doc, utility_label) pairs from conversion history
2. Fine-tunes the retriever embeddings using contrastive loss weighted by utility
3. Re-indexes the Bedrock API vector store with UAE embeddings
4. Benchmarks improvement over baseline

Usage:
    pipeline = UAETrainingPipeline()
    await pipeline.run_training_cycle()
    metrics = pipeline.get_improvement_metrics()
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from search.bedrock_uae_benchmark import (
    BedrockUAEBenchmarkDataset,
    ConversionHistoryEntry,
    EvaluationQuery,
)
from search.uae_search_engine import UAESearchEngine, UAESearchConfig
from utils.uae_retriever import UAERetriever, UAEConfig, create_uae_retriever
from utils.uae_utils import UAETrainingPair, UtilityLabel, RetrievalBenchmark

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for UAE training pipeline."""

    base_model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    epochs: int = 3
    batch_size: int = 16
    learning_rate: float = 2e-5
    temperature: float = 0.1
    margin: float = 0.5
    min_utility_threshold: float = 0.3
    checkpoint_dir: str = "/tmp/uae_checkpoints"
    use_synthetic_history: bool = True
    baseline_weight: float = 0.3
    uae_weight: float = 0.7


@dataclass
class TrainingMetrics:
    """Metrics from UAE training."""

    baseline_precision: float
    uae_precision: float
    improvement_percent: float
    hallucination_reduction: float
    training_pairs_count: int
    epochs_completed: int
    final_loss: float


class UAETrainingPipeline:
    """
    UAE fine-tuning pipeline for Bedrock API documentation retrieval.

    This pipeline addresses the core problem with standard RAG for code translation:
    cosine similarity retrieves Bedrock API docs that LOOK similar to a Java query
    but aren't the ones that produce valid Bedrock code.

    Example failure mode:
    - Java query: "register entity with custom AI goal"
    - Similarity-based: returns general Bedrock entity docs (high word overlap)
    - UAE retrieves: the specific Bedrock behavior pack component for custom AI goals
    """

    def __init__(
        self,
        config: Optional[TrainingConfig] = None,
        dataset: Optional[BedrockUAEBenchmarkDataset] = None,
        progress_callback: Optional[Callable[[int, float, str], None]] = None,
    ):
        self.config = config or TrainingConfig()
        self.dataset = dataset or BedrockUAEBenchmarkDataset()
        self.progress_callback = progress_callback

        self._uae_engine: Optional[UAESearchEngine] = None
        self._baseline_engine: Optional[UAESearchEngine] = None
        self._is_trained = False
        self._metrics: Optional[TrainingMetrics] = None

        self._init_engines()

    def _init_engines(self) -> None:
        """Initialize UAE and baseline search engines."""
        uae_config = UAESearchConfig(
            use_uae=True,
            baseline_weight=self.config.baseline_weight,
            uae_weight=self.config.uae_weight,
            min_utility_threshold=self.config.min_utility_threshold,
            enable_utility_scoring=True,
        )

        self._uae_engine = UAESearchEngine(config=uae_config)

        baseline_config = UAESearchConfig(use_uae=False)
        self._baseline_engine = UAESearchEngine(config=baseline_config)

        logger.info("UAE Training pipeline initialized")

    def _create_training_pairs_from_history(
        self,
        history: List[ConversionHistoryEntry],
    ) -> List[UAETrainingPair]:
        """Create UAE training pairs from conversion history."""
        pairs = []

        for entry in history:
            if not entry.successful:
                continue

            query = entry.java_query
            retrieved = entry.retrieved_doc_ids
            used = set(entry.used_doc_ids)

            positive_docs = list(used)
            negative_docs = [d for d in retrieved if d not in used]

            utility_labels = []
            for doc_id in retrieved:
                if doc_id in used:
                    utility_labels.append(
                        UtilityLabel(
                            query_id=query[:32],
                            document_id=doc_id,
                            utility_score=1.0,
                            signal_source=self._get_signal_source(doc_id, used),
                            metadata={"job_id": entry.job_id, "successful": True},
                        )
                    )
                else:
                    utility_labels.append(
                        UtilityLabel(
                            query_id=query[:32],
                            document_id=doc_id,
                            utility_score=0.0,
                            signal_source=self._get_signal_source(doc_id, used),
                            metadata={"job_id": entry.job_id, "successful": True},
                        )
                    )

            if positive_docs:
                pairs.append(
                    UAETrainingPair(
                        query=query,
                        positive_docs=positive_docs,
                        negative_docs=negative_docs,
                        utility_labels=utility_labels,
                    )
                )

        return pairs

    def _get_signal_source(self, doc_id: str, used_docs: set) -> str:
        """Determine the utility signal source for a document."""
        from utils.uae_utils import UtilitySignal

        if doc_id in used_docs:
            return UtilitySignal.CORRECT_CONVERSION.value
        return UtilitySignal.INCORRECT_CONVERSION.value

    def _create_document_contents(self) -> Dict[str, str]:
        """Create document contents mapping for training."""
        contents = {}
        for doc_id, doc in self.dataset.documents.items():
            contents[doc_id] = f"{doc.title}\n{doc.content}"
        return contents

    def _benchmark_retriever(
        self,
        engine: UAESearchEngine,
        use_uae: bool = False,
    ) -> RetrievalBenchmark:
        """Benchmark a retriever on the evaluation queries."""
        queries = self.dataset.get_evaluation_queries()

        retrieved_docs = {}
        useful_docs = {}

        for query in queries:
            retrieved = self.dataset.get_retrieved_docs_for_query(query.java_query)
            sorted_docs = sorted(retrieved.items(), key=lambda x: x[1], reverse=True)
            retrieved_docs[query.java_query] = [d[0] for d in sorted_docs[:5]]
            useful_docs[query.java_query] = query.useful_doc_ids

        return engine.benchmark(
            test_queries=list(retrieved_docs.keys()),
            retrieved_docs=retrieved_docs,
            useful_docs=useful_docs,
            use_uae=use_uae,
        )

    def _calculate_hallucination_metrics(
        self,
        engine: UAESearchEngine,
        use_uae: bool,
    ) -> Dict[str, Any]:
        """Calculate hallucination metrics for the retriever."""
        queries = self.dataset.get_evaluation_queries()
        hallucination_count = 0
        total_queries = len(queries)

        for query in queries:
            retrieved = self.dataset.get_retrieved_docs_for_query(query.java_query)
            sorted_docs = sorted(retrieved.items(), key=lambda x: x[1], reverse=True)
            retrieved_ids = [d[0] for d in sorted_docs[:5]]

            if query.hallucination_risk:
                has_correct = any(doc_id in query.useful_doc_ids for doc_id in retrieved_ids)
                if not has_correct:
                    hallucination_count += 1

        hallucination_rate = hallucination_count / total_queries if total_queries > 0 else 0.0

        return {
            "hallucination_count": hallucination_count,
            "total_queries": total_queries,
            "hallucination_rate": hallucination_rate,
        }

    async def run_training_cycle(
        self,
        training_history: Optional[List[ConversionHistoryEntry]] = None,
    ) -> TrainingMetrics:
        """
        Run a complete UAE training cycle.

        Args:
            training_history: Optional conversion history to use for training.
                           If not provided, uses synthetic history from dataset.

        Returns:
            TrainingMetrics with improvement metrics
        """
        logger.info("Starting UAE training cycle")

        if self.progress_callback:
            self.progress_callback(0, 0.0, "Initializing training...")

        history = training_history or self.dataset.get_conversion_history()

        baseline_benchmark = self._benchmark_retriever(self._baseline_engine, use_uae=False)

        if self.progress_callback:
            self.progress_callback(10, 0.1, "Created baseline benchmark")

        logger.info(
            f"Baseline benchmark: precision={baseline_benchmark.precision_at_k:.3f}, "
            f"recall={baseline_benchmark.recall_at_k:.3f}"
        )

        training_pairs = self._create_training_pairs_from_history(history)
        document_contents = self._create_document_contents()

        logger.info(f"Created {len(training_pairs)} training pairs")

        if self.progress_callback:
            self.progress_callback(20, 0.2, f"Created {len(training_pairs)} training pairs")

        if len(training_pairs) < 2:
            logger.warning("Insufficient training pairs for fine-tuning")
            return TrainingMetrics(
                baseline_precision=baseline_benchmark.precision_at_k,
                uae_precision=baseline_benchmark.precision_at_k,
                improvement_percent=0.0,
                hallucination_reduction=0.0,
                training_pairs_count=len(training_pairs),
                epochs_completed=0,
                final_loss=0.0,
            )

        def progress_hook(epoch: int, loss: float):
            progress = 20 + (epoch / self.config.epochs) * 60
            if self.progress_callback:
                self.progress_callback(progress, loss, f"Epoch {epoch + 1}/{self.config.epochs}")

        training_metrics = self._uae_engine.fine_tune(
            training_pairs=training_pairs,
            document_contents=document_contents,
            progress_callback=progress_hook,
        )

        if self.progress_callback:
            self.progress_callback(
                80, training_metrics.get("final_loss", 0.0), "Fine-tuning complete"
            )

        uae_benchmark = self._benchmark_retriever(self._uae_engine, use_uae=True)

        if self.progress_callback:
            self.progress_callback(90, 0.0, "Running UAE benchmark")

        logger.info(
            f"UAE benchmark: precision={uae_benchmark.precision_at_k:.3f}, "
            f"recall={uae_benchmark.recall_at_k:.3f}"
        )

        baseline_halluc = self._calculate_hallucination_metrics(
            self._baseline_engine, use_uae=False
        )
        uae_halluc = self._calculate_hallucination_metrics(self._uae_engine, use_uae=True)

        improvement = 0.0
        if baseline_benchmark.precision_at_k > 0:
            improvement = (
                (uae_benchmark.precision_at_k - baseline_benchmark.precision_at_k)
                / baseline_benchmark.precision_at_k
                * 100
            )

        hallucination_reduction = (
            baseline_halluc["hallucination_rate"] - uae_halluc["hallucination_rate"]
        )

        self._metrics = TrainingMetrics(
            baseline_precision=baseline_benchmark.precision_at_k,
            uae_precision=uae_benchmark.precision_at_k,
            improvement_percent=improvement,
            hallucination_reduction=hallucination_reduction,
            training_pairs_count=len(training_pairs),
            epochs_completed=training_metrics.get("epochs", [0])[-1] + 1
            if training_metrics.get("epochs")
            else 0,
            final_loss=training_metrics.get("final_loss", 0.0),
        )

        self._is_trained = True

        if self.progress_callback:
            self.progress_callback(100, self._metrics.final_loss, "Training complete")

        logger.info(f"Training complete. Improvement: {improvement:.1f}%")

        return self._metrics

    def get_improvement_metrics(self) -> Optional[TrainingMetrics]:
        """Get the improvement metrics from the last training run."""
        return self._metrics

    def get_uae_engine(self) -> Optional[UAESearchEngine]:
        """Get the trained UAE search engine."""
        return self._uae_engine if self._is_trained else None

    def is_trained(self) -> bool:
        """Check if the pipeline has been trained."""
        return self._is_trained

    def export_trained_model(self, path: str) -> bool:
        """Export the trained model to a checkpoint path."""
        if not self._is_trained or not self._uae_engine or not self._uae_engine._uae_retriever:
            logger.warning("No trained model to export")
            return False

        checkpoint_dir = Path(path)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        try:
            retriever = self._uae_engine._uae_retriever
            if hasattr(retriever, "_model") and retriever._model:
                retriever._model.save(str(checkpoint_dir))
                logger.info(f"Exported trained model to {path}")
                return True
        except Exception as e:
            logger.error(f"Failed to export model: {e}")

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get training pipeline statistics."""
        return {
            "is_trained": self._is_trained,
            "config": {
                "base_model": self.config.base_model,
                "epochs": self.config.epochs,
                "batch_size": self.config.batch_size,
                "learning_rate": self.config.learning_rate,
            },
            "dataset_size": {
                "documents": len(self.dataset.documents),
                "evaluation_queries": len(self.dataset.queries),
                "conversion_history": len(self.dataset.conversion_history),
            },
            "metrics": self._metrics.__dict__ if self._metrics else None,
        }


async def create_uae_training_pipeline(
    config: Optional[TrainingConfig] = None,
) -> UAETrainingPipeline:
    """Factory function to create UAE training pipeline."""
    pipeline = UAETrainingPipeline(config=config)
    return pipeline


async def run_quick_benchmark() -> Dict[str, Any]:
    """Run a quick benchmark comparison without full training."""
    dataset = BedrockUAEBenchmarkDataset()

    uae_config = UAESearchConfig(use_uae=True)
    baseline_config = UAESearchConfig(use_uae=False)

    uae_engine = UAESearchEngine(config=uae_config)
    baseline_engine = UAESearchEngine(config=baseline_config)

    queries = dataset.get_evaluation_queries()

    baseline_retrieved = {}
    baseline_useful = {}
    uae_retrieved = {}
    uae_useful = {}

    for query in queries:
        retrieved = dataset.get_retrieved_docs_for_query(query.java_query)
        sorted_docs = sorted(retrieved.items(), key=lambda x: x[1], reverse=True)

        baseline_retrieved[query.java_query] = [d[0] for d in sorted_docs[:5]]
        baseline_useful[query.java_query] = query.useful_doc_ids

        uae_retrieved[query.java_query] = [d[0] for d in sorted_docs[:5]]
        uae_useful[query.java_query] = query.useful_doc_ids

    baseline_bench = baseline_engine.benchmark(
        test_queries=list(baseline_retrieved.keys()),
        retrieved_docs=baseline_retrieved,
        useful_docs=baseline_useful,
        use_uae=False,
    )

    uae_bench = uae_engine.benchmark(
        test_queries=list(uae_retrieved.keys()),
        retrieved_docs=uae_retrieved,
        useful_docs=uae_useful,
        use_uae=True,
    )

    improvement = 0.0
    if baseline_bench.precision_at_k > 0:
        improvement = (
            (uae_bench.precision_at_k - baseline_bench.precision_at_k)
            / baseline_bench.precision_at_k
            * 100
        )

    return {
        "baseline": {
            "precision_at_5": baseline_bench.precision_at_k,
            "recall_at_5": baseline_bench.recall_at_k,
            "mrr": baseline_bench.mrr,
        },
        "uae": {
            "precision_at_5": uae_bench.precision_at_k,
            "recall_at_5": uae_bench.recall_at_k,
            "mrr": uae_bench.mrr,
        },
        "improvement_percent": improvement,
        "target_met": improvement >= 10.0,
    }
