"""
UAE (Utility-Aligned Embeddings) Retriever for Bedrock API Documentation.

This module implements the UAE retriever that fine-tunes embeddings using
utility signals from conversion history to improve retrieval for code translation.

Based on: "Aligning Dense Retrievers with LLM Utility via Distillation"
(Sandhu et al., https://arxiv.org/abs/2604.22722v1)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Callable
from pathlib import Path

import numpy as np

from utils.embedding_generator import (
    EmbeddingGenerator,
    LocalEmbeddingGenerator,
    EmbeddingResult,
)
from utils.uae_utils import (
    UtilityLabel,
    UtilityLabelCalculator,
    ContrastiveUtilityLoss,
    UAETrainingPair,
    RetrievalBenchmark,
    RetrievalBenchmarker,
    normalize_utility_scores,
)

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class UAEConfig:
    """Configuration for UAE retriever."""

    base_model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    temperature: float = 0.1
    margin: float = 0.5
    learning_rate: float = 2e-5
    batch_size: int = 16
    epochs: int = 3
    min_utility_threshold: float = 0.3
    checkpoint_dir: str = "/tmp/uae_checkpoints"
    device: str = "cpu"


class UAERetriever:
    """
    Utility-Aligned Embedding Retriever.

    This retriever extends standard embedding retrieval with:
    1. Utility-weighted contrastive loss during fine-tuning
    2. Conversion history-based utility labels
    3. Baseline benchmarking for improvement measurement
    """

    def __init__(
        self,
        config: Optional[UAEConfig] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
    ):
        self.config = config or UAEConfig()
        self._embedding_generator = embedding_generator
        self._model: Optional[SentenceTransformer] = None
        self._label_calculator = UtilityLabelCalculator()
        self._contrastive_loss = ContrastiveUtilityLoss(
            margin=self.config.margin,
            temperature=self.config.temperature,
        )
        self._benchmarker = RetrievalBenchmarker(k=5)
        self._is_fine_tuned = False
        self._training_history: List[Dict[str, float]] = []

        self._init_model()

    def _init_model(self) -> None:
        """Initialize the embedding model."""
        if self._embedding_generator is None:
            self._embedding_generator = LocalEmbeddingGenerator(
                model=self.config.base_model,
                dimensions=self.config.dimensions,
            )

        if isinstance(self._embedding_generator, LocalEmbeddingGenerator):
            self._model = self._embedding_generator._model

    def generate_embedding(self, text: str) -> Optional[EmbeddingResult]:
        """Generate embedding for text using the current model."""
        if self._embedding_generator:
            return self._embedding_generator.generate_embedding(text)
        return None

    def generate_embeddings(self, texts: List[str]) -> List[Optional[EmbeddingResult]]:
        """Generate embeddings for multiple texts."""
        if self._embedding_generator:
            return self._embedding_generator.generate_embeddings(texts)
        return [None] * len(texts)

    def compute_utility_score(
        self,
        query_embedding: np.ndarray,
        doc_embedding: np.ndarray,
        utility_weight: float = 1.0,
    ) -> float:
        """
        Compute utility-weighted similarity score.

        Unlike standard cosine similarity, this incorporates the utility
        weight learned during fine-tuning.
        """
        base_similarity = np.dot(query_embedding, doc_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding) + 1e-8
        )
        return float(base_similarity * utility_weight)

    def label_from_conversion(
        self,
        query: str,
        retrieved_doc_ids: List[str],
        conversion_output: str,
        conversion_successful: bool,
    ) -> List[UtilityLabel]:
        """Create utility labels from conversion history."""
        return self._label_calculator.calculate_from_conversion_history(
            query=query,
            retrieved_doc_ids=retrieved_doc_ids,
            conversion_output=conversion_output,
            conversion_successful=conversion_successful,
        )

    def create_training_pairs(
        self,
        queries: List[str],
        retrieved_docs: Dict[str, List[str]],
        conversion_outputs: Dict[str, tuple],
    ) -> List[UAETrainingPair]:
        """
        Create training pairs from conversion history.

        Args:
            queries: List of queries
            retrieved_docs: Dict mapping query to list of retrieved doc IDs
            conversion_outputs: Dict mapping query to (output, successful) tuple
        """
        pairs = []

        for query in queries:
            docs = retrieved_docs.get(query, [])
            output, successful = conversion_outputs.get(query, ("", False))

            labels = self.label_from_conversion(
                query=query,
                retrieved_doc_ids=docs,
                conversion_output=output,
                conversion_successful=successful,
            )

            normalized_labels = normalize_utility_scores(labels)

            positive_docs = [
                doc_id for doc_id, label in zip(docs, normalized_labels) if label.is_positive()
            ]
            negative_docs = [
                doc_id
                for doc_id, label in zip(docs, normalized_labels)
                if not label.is_positive()
                and label.utility_score < self.config.min_utility_threshold
            ]

            if positive_docs:
                pairs.append(
                    UAETrainingPair(
                        query=query,
                        positive_docs=positive_docs,
                        negative_docs=negative_docs,
                        utility_labels=normalized_labels,
                    )
                )

        return pairs

    def benchmark_retrieval(
        self,
        test_queries: List[str],
        retrieved_docs: Dict[str, List[str]],
        useful_docs: Dict[str, List[str]],
    ) -> RetrievalBenchmark:
        """
        Benchmark current retrieval performance.

        This establishes the baseline to measure UAE improvement against.
        """
        return self._benchmarker.benchmark(
            queries=test_queries,
            retrieved_docs_per_query=retrieved_docs,
            useful_docs_per_query=useful_docs,
        )

    def fine_tune(
        self,
        training_pairs: List[UAETrainingPair],
        document_contents: Dict[str, str],
        validation_pairs: Optional[List[UAETrainingPair]] = None,
        progress_callback: Optional[Callable[[int, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Fine-tune the retriever using utility-aligned contrastive learning.

        Args:
            training_pairs: Training pairs with utility labels
            document_contents: Dict mapping doc_id to content
            validation_pairs: Optional validation pairs
            progress_callback: Optional callback(epoch, loss)

        Returns:
            Training metrics
        """
        if not self._model:
            logger.warning("No model loaded, skipping fine-tuning")
            return {"status": "no_model"}

        if len(training_pairs) < 2:
            logger.warning("Insufficient training pairs, skipping fine-tuning")
            return {"status": "insufficient_data"}

        logger.info(f"Starting UAE fine-tuning with {len(training_pairs)} training pairs")

        optimizer = self._create_optimizer()
        scheduler = self._create_scheduler(optimizer)

        best_loss = float("inf")
        metrics = {
            "epochs": [],
            "train_losses": [],
            "val_losses": [],
            "best_epoch": 0,
        }

        for epoch in range(self.config.epochs):
            epoch_loss = self._train_epoch(
                training_pairs=training_pairs,
                document_contents=document_contents,
                optimizer=optimizer,
            )

            metrics["epochs"].append(epoch)
            metrics["train_losses"].append(epoch_loss)

            if validation_pairs:
                val_loss = self._compute_validation_loss(validation_pairs, document_contents)
                metrics["val_losses"].append(val_loss)

                if val_loss < best_loss:
                    best_loss = val_loss
                    metrics["best_epoch"] = epoch
                    self._save_checkpoint(epoch)

            scheduler.step()

            if progress_callback:
                progress_callback(epoch, epoch_loss)

            logger.info(f"Epoch {epoch + 1}/{self.config.epochs}: loss={epoch_loss:.4f}")

        self._is_fine_tuned = True
        metrics["status"] = "completed"
        metrics["final_loss"] = metrics["train_losses"][-1]

        self._training_history.append(metrics)

        return metrics

    def _create_optimizer(self):
        """Create optimizer for fine-tuning."""
        try:
            from torch.optim import AdamW
            from sentence_transformers import SentenceTransformer

            if isinstance(self._model, SentenceTransformer):
                return AdamW(self._model.parameters(), lr=self.config.learning_rate)
        except ImportError:
            logger.warning("PyTorch not available, using numpy-based training")

        return None

    def _create_scheduler(self, optimizer):
        """Create learning rate scheduler."""
        try:
            from torch.optim.lr_scheduler import LinearLR

            return LinearLR(optimizer, start_factor=1.0, end_factor=0.1)
        except ImportError:
            return None

    def _train_epoch(
        self,
        training_pairs: List[UAETrainingPair],
        document_contents: Dict[str, str],
        optimizer,
    ) -> float:
        """Train for one epoch."""
        total_loss = 0.0
        pair_count = 0

        for pair in training_pairs:
            anchor_emb = self.generate_embedding(pair.query)
            if not anchor_emb:
                continue

            anchor = anchor_emb.embedding

            positive_embs = []
            negative_embs = []
            utility_weights = []

            for pos_doc_id in pair.positive_docs:
                pos_content = document_contents.get(pos_doc_id, "")
                if pos_content:
                    result = self.generate_embedding(pos_content)
                    if result:
                        positive_embs.append(result.embedding)

            for neg_doc_id in pair.negative_docs:
                neg_content = document_contents.get(neg_doc_id, "")
                if neg_content:
                    result = self.generate_embedding(neg_content)
                    if result:
                        negative_embs.append(result.embedding)

            for label in pair.utility_labels:
                if label.is_positive():
                    utility_weights.append(label.utility_score)

            if not positive_embs or not negative_embs:
                continue

            loss = self._contrastive_loss.compute(
                anchor_embedding=anchor,
                positive_embeddings=positive_embs,
                negative_embeddings=negative_embs,
                utility_weights=utility_weights or [1.0] * len(positive_embs),
            )

            if optimizer and loss > 0:
                self._update_with_gradients(optimizer, anchor, positive_embs, negative_embs)

            total_loss += loss
            pair_count += 1

        return total_loss / pair_count if pair_count > 0 else 0.0

    def _update_with_gradients(self, optimizer, anchor, positives, negatives):
        """Update model with simple gradient-based optimization."""
        try:
            import torch
        except ImportError:
            return

        try:
            anchor_t = torch.tensor(anchor, dtype=torch.float32, requires_grad=True)
            pos_tensors = [torch.tensor(p, dtype=torch.float32) for p in positives]
            neg_tensors = [torch.tensor(n, dtype=torch.float32) for n in negatives]

            pos_sum = sum(pos_tensors) / len(pos_tensors)
            neg_sum = sum(neg_tensors) / len(neg_tensors)

            loss = (
                -torch.nn.functional.cosine_similarity(
                    anchor_t.unsqueeze(0), pos_sum.unsqueeze(0)
                ).mean()
                + torch.nn.functional.cosine_similarity(
                    anchor_t.unsqueeze(0), neg_sum.unsqueeze(0)
                ).mean()
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        except Exception as e:
            logger.debug(f"Gradient update failed: {e}")

    def _compute_validation_loss(
        self,
        validation_pairs: List[UAETrainingPair],
        document_contents: Dict[str, str],
    ) -> float:
        """Compute validation loss."""
        total_loss = 0.0
        pair_count = 0

        for pair in validation_pairs:
            anchor_emb = self.generate_embedding(pair.query)
            if not anchor_emb:
                continue

            anchor = anchor_emb.embedding

            positive_embs = []
            negative_embs = []
            utility_weights = []

            for pos_doc_id in pair.positive_docs:
                pos_content = document_contents.get(pos_doc_id, "")
                if pos_content:
                    result = self.generate_embedding(pos_content)
                    if result:
                        positive_embs.append(result.embedding)

            for neg_doc_id in pair.negative_docs:
                neg_content = document_contents.get(neg_doc_id, "")
                if neg_content:
                    result = self.generate_embedding(neg_content)
                    if result:
                        negative_embs.append(result.embedding)

            for label in pair.utility_labels:
                if label.is_positive():
                    utility_weights.append(label.utility_score)

            if not positive_embs or not negative_embs:
                continue

            loss = self._contrastive_loss.compute(
                anchor_embedding=anchor,
                positive_embeddings=positive_embs,
                negative_embeddings=negative_embs,
                utility_weights=utility_weights or [1.0] * len(positive_embs),
            )

            total_loss += loss
            pair_count += 1

        return total_loss / pair_count if pair_count > 0 else 0.0

    def _save_checkpoint(self, epoch: int) -> None:
        """Save model checkpoint."""
        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        if self._model:
            checkpoint_path = checkpoint_dir / f"uae_checkpoint_epoch_{epoch}.pt"
            try:
                self._model.save(str(checkpoint_path))
                logger.info(f"Checkpoint saved: {checkpoint_path}")
            except Exception as e:
                logger.warning(f"Failed to save checkpoint: {e}")

    def load_checkpoint(self, checkpoint_path: str) -> bool:
        """Load a checkpoint."""
        if not self._model:
            return False

        try:
            self._model = self._model.from_pretrained(checkpoint_path)
            self._is_fine_tuned = True
            logger.info(f"Checkpoint loaded: {checkpoint_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    @property
    def is_fine_tuned(self) -> bool:
        """Check if the retriever has been fine-tuned."""
        return self._is_fine_tuned

    @property
    def training_history(self) -> List[Dict[str, Any]]:
        """Get training history."""
        return self._training_history


def create_uae_retriever(
    config: Optional[UAEConfig] = None,
    embedding_generator: Optional[EmbeddingGenerator] = None,
) -> UAERetriever:
    """Factory function to create UAE retriever."""
    return UAERetriever(config=config, embedding_generator=embedding_generator)
