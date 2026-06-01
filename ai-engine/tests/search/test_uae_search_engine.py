"""
Tests for UAE Search Engine.

Tests the UAE-enhanced search engine that combines utility-aligned
embeddings with standard similarity search for improved Bedrock API retrieval.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from search.uae_search_engine import UAESearchEngine, UAESearchConfig
from search.hybrid_search_engine import SearchMode
from schemas.multimodal_schema import MultiModalDocument, SearchQuery, SearchResult


@pytest.fixture
def mock_document():
    """Create a mock document."""
    doc = Mock(spec=MultiModalDocument)
    doc.id = "doc_1"
    doc.content_text = "Minecraft Bedrock Script API entity registration"
    doc.source_path = "/bedrock/docs/api/entity.md"
    doc.content_type = "api_reference"
    doc.tags = ["bedrock", "api", "entity"]
    doc.content_metadata = {"class_name": "EntityRegistration", "method_name": "registerEntity"}
    return doc


@pytest.fixture
def mock_documents(mock_document):
    """Create mock documents dict."""
    docs = {"doc_1": mock_document}
    for i in range(2, 6):
        doc = Mock(spec=MultiModalDocument)
        doc.id = f"doc_{i}"
        doc.content_text = f"Content about Minecraft {i}"
        doc.source_path = f"/test/file{i}.java"
        doc.content_type = "code"
        doc.tags = ["minecraft", "code"]
        doc.content_metadata = {}
        docs[f"doc_{i}"] = doc
    return docs


@pytest.fixture
def mock_embeddings():
    """Create mock embeddings."""
    embeddings = {}
    for i in range(1, 6):
        emb = np.random.randn(384).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        embeddings[f"doc_{i}"] = [emb.tolist()]
    return embeddings


@pytest.fixture
def mock_query():
    """Create mock search query."""
    return SearchQuery(
        query_text="how to register custom entity with Bedrock Script API",
        top_k=5,
        tags=["bedrock", "api"],
    )


class TestUAESearchConfig:
    """Tests for UAE search configuration."""

    def test_default_config(self):
        """Test default UAE search configuration."""
        config = UAESearchConfig()

        assert config.use_uae is True
        assert config.baseline_weight == 0.3
        assert config.uae_weight == 0.7
        assert config.min_utility_threshold == 0.3
        assert config.enable_utility_scoring is True
        assert config.benchmark_interval == 100

    def test_custom_config(self):
        """Test custom UAE search configuration."""
        config = UAESearchConfig(
            use_uae=True,
            baseline_weight=0.2,
            uae_weight=0.8,
            min_utility_threshold=0.4,
        )

        assert config.baseline_weight == 0.2
        assert config.uae_weight == 0.8
        assert config.min_utility_threshold == 0.4


class TestUAESearchEngine:
    """Tests for UAE search engine."""

    def test_engine_creation(self):
        """Test UAE search engine creation."""
        engine = UAESearchEngine()

        assert engine.config is not None
        assert engine.hybrid_engine is not None

    def test_engine_with_disabled_uae(self):
        """Test UAE search engine with UAE disabled."""
        config = UAESearchConfig(use_uae=False)
        engine = UAESearchEngine(config=config)

        assert engine.config.use_uae is False
        assert engine._uae_retriever is None

    def test_engine_with_custom_config(self):
        """Test UAE search engine with custom config."""
        config = UAESearchConfig(
            use_uae=True,
            baseline_weight=0.4,
            uae_weight=0.6,
        )
        engine = UAESearchEngine(config=config)

        assert engine.config.baseline_weight == 0.4
        assert engine.config.uae_weight == 0.6

    @pytest.mark.asyncio
    async def test_search_without_uae(self, mock_documents, mock_embeddings, mock_query):
        """Test search with UAE disabled."""
        config = UAESearchConfig(use_uae=False)
        engine = UAESearchEngine(config=config)

        results = await engine.search(
            query=mock_query,
            documents=mock_documents,
            embeddings=mock_embeddings,
            query_embedding=mock_embeddings["doc_1"][0],
            search_mode=SearchMode.HYBRID,
        )

        assert isinstance(results, list)

    def test_compute_utility_similarity(self):
        """Test utility-weighted similarity computation."""
        engine = UAESearchEngine()

        query_emb = np.random.randn(384).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)

        doc_emb = np.random.randn(384).astype(np.float32)
        doc_emb = doc_emb / np.linalg.norm(doc_emb)

        score = engine.compute_utility_similarity(query_emb, doc_emb, utility_weight=0.8)

        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0

    @pytest.mark.slow
    def test_estimate_utility_weight(self):
        """Test utility weight estimation."""
        engine = UAESearchEngine()

        weight_high = engine._estimate_utility_weight(
            "register entity with custom AI goal and component handler",
            "doc_1"
        )
        assert weight_high >= 0.7

        weight_medium = engine._estimate_utility_weight(
            "how to create block item",
            "doc_2"
        )
        assert weight_medium >= 0.5

        weight_low = engine._estimate_utility_weight(
            "general minecraft question",
            "doc_3"
        )
        assert weight_low >= 0.4

    def test_score_candidate_uae_enabled(self):
        """Test candidate scoring with UAE enabled."""
        config = UAESearchConfig(use_uae=True, uae_weight=0.7, baseline_weight=0.3)
        engine = UAESearchEngine(config=config)

        candidate = Mock()
        candidate.vector_score = 0.8
        candidate.semantic_score = 0.9
        candidate.keyword_score = 0.5
        candidate.context_score = 0.1
        candidate.explanation = []

        engine._score_candidate(candidate, is_uae=True)

        assert candidate.final_score > 0
        assert len(candidate.explanation) > 0

    def test_score_candidate_uae_disabled(self):
        """Test candidate scoring with UAE disabled."""
        config = UAESearchConfig(use_uae=False)
        engine = UAESearchEngine(config=config)

        candidate = Mock()
        candidate.vector_score = 0.8
        candidate.semantic_score = 0.0
        candidate.keyword_score = 0.5
        candidate.context_score = 0.1
        candidate.explanation = []

        engine._score_candidate(candidate, is_uae=False)

        assert candidate.final_score > 0

    def test_passes_filters(self):
        """Test document filtering."""
        engine = UAESearchEngine()

        doc = Mock()
        doc.content_type = "documentation"
        doc.tags = ["bedrock", "api"]
        doc.content_metadata = {}

        query = SearchQuery(
            query_text="test",
            content_types=["documentation"],
            tags=["bedrock"],
        )

        assert engine._passes_filters(doc, query) is True

        query_no_match = SearchQuery(
            query_text="test",
            content_types=["configuration"],
        )

        assert engine._passes_filters(doc, query_no_match) is False

    def test_calculate_context_score(self):
        """Test context score calculation."""
        engine = UAESearchEngine()

        doc = Mock()
        doc.content_metadata = {
            "minecraft_version": "1.20",
            "class_name": "EntityRegistration",
        }

        query = SearchQuery(
            query_text="test query",
            query_context="entity",
        )

        score = engine._calculate_context_score(doc, query)

        assert score > 0

    def test_fine_tune_without_retriever(self):
        """Test fine-tuning when UAE retriever not available."""
        config = UAESearchConfig(use_uae=False)
        engine = UAESearchEngine(config=config)

        result = engine.fine_tune(
            training_pairs=[],
            document_contents={},
        )

        assert result["status"] == "no_retriever"

    def test_is_fine_tuned_property(self):
        """Test is_fine_tuned property."""
        engine = UAESearchEngine()

        assert engine.is_fine_tuned is False

    def test_get_stats(self):
        """Test getting search engine stats."""
        engine = UAESearchEngine()

        stats = engine.get_stats()

        assert "uae_enabled" in stats
        assert "is_fine_tuned" in stats
        assert "search_count" in stats
        assert stats["uae_enabled"] is True


class TestUAESearchBenchmark:
    """Tests for UAE search benchmarking."""

    def test_benchmark_no_data(self):
        """Test benchmark with no data."""
        engine = UAESearchEngine()

        result = engine.benchmark(
            test_queries=[],
            retrieved_docs={},
            useful_docs={},
            use_uae=False,
        )

        assert result.total_queries == 0

    def test_benchmark_with_data(self):
        """Test benchmark with actual data."""
        engine = UAESearchEngine()

        queries = ["query1", "query2"]
        retrieved = {
            "query1": ["doc1", "doc2", "doc3"],
            "query2": ["doc1", "doc2", "doc4"],
        }
        useful = {
            "query1": ["doc1", "doc2"],
            "query2": ["doc2", "doc4"],
        }

        result = engine.benchmark(
            test_queries=queries,
            retrieved_docs=retrieved,
            useful_docs=useful,
            use_uae=False,
        )

        assert result.total_queries == 2
        assert result.precision_at_k >= 0
        assert result.recall_at_k >= 0

    def test_compare_uae_vs_baseline_no_data(self):
        """Test comparison with no data."""
        engine = UAESearchEngine()

        result = engine.compare_uae_vs_baseline()

        assert result["status"] == "insufficient_data"

    def test_compare_uae_vs_baseline_with_data(self):
        """Test comparison with actual data."""
        engine = UAESearchEngine()

        queries = ["query1", "query2"]
        retrieved = {
            "query1": ["doc1", "doc2"],
            "query2": ["doc1", "doc3"],
        }
        useful = {
            "query1": ["doc1"],
            "query2": ["doc3"],
        }

        engine.benchmark(queries, retrieved, useful, use_uae=False)
        engine.benchmark(queries, retrieved, useful, use_uae=True)

        result = engine.compare_uae_vs_baseline()

        assert result["status"] == "compared"
        assert "baseline" in result
        assert "uae" in result
        assert "improvement" in result


class TestUAEUiltInIntegration:
    """Tests for UAE integration with hybrid search."""

    def test_engine_has_hybrid_engine(self):
        """Test that UAE engine has hybrid engine."""
        engine = UAESearchEngine()

        assert engine.hybrid_engine is not None
        assert hasattr(engine.hybrid_engine, "keyword_engine")
        assert hasattr(engine.hybrid_engine, "search")

    def test_vector_similarity_calculation(self):
        """Test vector similarity calculation."""
        engine = UAESearchEngine()

        query_emb = [1.0] * 384
        doc_embs = [[0.5] * 384, [0.3] * 384]

        score = engine._calculate_vector_similarity(query_emb, doc_embs)

        assert isinstance(score, float)
        assert 0 <= score <= 1.0

    def test_empty_embeddings(self):
        """Test handling of empty embeddings."""
        engine = UAESearchEngine()

        score = engine._calculate_vector_similarity([1.0] * 384, [])

        assert score == 0.0

    def test_mismatched_dimensions(self):
        """Test handling of mismatched dimensions."""
        engine = UAESearchEngine()

        score = engine._calculate_vector_similarity([1.0] * 384, [[1.0] * 128])

        assert score == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])