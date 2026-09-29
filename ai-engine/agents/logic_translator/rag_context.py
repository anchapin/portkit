"""RAG context augmentation for logic translation.

Split out from ``translator.py`` per Issue #1746. Provides retrieval-augmented
generation context for Java-to-Bedrock translation.

The :class:`RAGContextMixin` is composed into :class:`LogicTranslatorAgent` and
assumes the host class initializes ``self._conversion_rag_pipeline`` and
``self._rag_context_enabled``.
"""

from utils.logging_config import get_agent_logger

logger = get_agent_logger("logic_translator")


class RAGContextMixin:
    """RAG pipeline integration for the LogicTranslatorAgent."""

    def set_rag_pipeline(self, pipeline) -> None:
        """Set the ConversionRAGPipeline for context-augmented translation.

        Args:
            pipeline: ConversionRAGPipeline instance.
        """
        self._conversion_rag_pipeline = pipeline
        self._rag_context_enabled = pipeline is not None
        logger.info(f"RAG context {'enabled' if self._rag_context_enabled else 'disabled'}")

    def enable_rag_context(self, enabled: bool = True) -> None:
        """Enable or disable RAG context retrieval."""
        self._rag_context_enabled = enabled and self._conversion_rag_pipeline is not None

    def _get_rag_context(self, java_feature: str, feature_type: str) -> str:
        """Get RAG context for a Java feature.

        Args:
            java_feature: Description of the Java feature.
            feature_type: Type of feature (block, item, entity, etc.).

        Returns:
            Formatted context string for LLM, or empty string if unavailable.
        """
        if not self._rag_context_enabled or not self._conversion_rag_pipeline:
            return ""

        try:
            result = self._conversion_rag_pipeline.retrieve_conversion_context_sync(
                java_feature=java_feature,
                feature_type=feature_type,
                top_k=5,
            )
            return self._conversion_rag_pipeline.format_context_for_llm(result)
        except Exception as e:
            logger.warning(f"RAG context retrieval failed: {e}")
            return ""
