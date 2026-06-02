"""
Unit tests for search/rag_pipeline.py

Tests QueryType, ComplexityLevel, QueryAnalysis, PipelineResult,
PipelineConfig, and PipelineStage classes.
"""

import pytest
from search.rag_pipeline import (
    QueryType,
    ComplexityLevel,
    QueryAnalysis,
    PipelineResult,
    PipelineConfig,
    PipelineStage,
    QueryAnalysisStage,
)


class TestQueryType:
    """Tests for QueryType enum."""

    def test_query_types_exist(self):
        """Test that all expected query types exist."""
        assert QueryType.INFORMATIONAL.value == "informational"
        assert QueryType.NAVIGATIONAL.value == "navigational"
        assert QueryType.TRANSACTIONAL.value == "transactional"
        assert QueryType.COMPLEX.value == "complex"
        assert QueryType.SIMPLE.value == "simple"

    def test_query_type_is_string(self):
        """Test that QueryType values are strings."""
        for qt in QueryType:
            assert isinstance(qt.value, str)


class TestComplexityLevel:
    """Tests for ComplexityLevel enum."""

    def test_complexity_levels_exist(self):
        """Test that all expected complexity levels exist."""
        assert ComplexityLevel.SIMPLE.value == "simple"
        assert ComplexityLevel.STANDARD.value == "standard"
        assert ComplexityLevel.COMPLEX.value == "complex"

    def test_complexity_level_is_string(self):
        """Test that ComplexityLevel values are strings."""
        for cl in ComplexityLevel:
            assert isinstance(cl.value, str)


class TestQueryAnalysis:
    """Tests for QueryAnalysis dataclass."""

    def test_create_minimal(self):
        """Test creating a minimal QueryAnalysis."""
        analysis = QueryAnalysis(original_query="How to spawn entity?")
        assert analysis.original_query == "How to spawn entity?"
        assert analysis.rewritten_query is None
        assert analysis.expanded_terms == []
        assert analysis.query_type == QueryType.SIMPLE
        assert analysis.complexity == ComplexityLevel.SIMPLE
        assert analysis.confidence == 1.0

    def test_create_full(self):
        """Test creating a full QueryAnalysis."""
        analysis = QueryAnalysis(
            original_query="How to spawn entity?",
            rewritten_query="Spawning entities in Minecraft",
            expanded_terms=["entity", "spawn", "minecraft"],
            query_type=QueryType.INFORMATIONAL,
            complexity=ComplexityLevel.COMPLEX,
            confidence=0.9,
        )
        assert analysis.original_query == "How to spawn entity?"
        assert analysis.rewritten_query == "Spawning entities in Minecraft"
        assert analysis.expanded_terms == ["entity", "spawn", "minecraft"]
        assert analysis.query_type == QueryType.INFORMATIONAL
        assert analysis.complexity == ComplexityLevel.COMPLEX
        assert analysis.confidence == 0.9


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_create_empty(self):
        """Test creating a minimal PipelineResult."""
        analysis = QueryAnalysis(original_query="test")
        result = PipelineResult(results=[], query_analysis=analysis)
        assert result.results == []
        assert result.query_analysis == analysis
        assert result.expansion_metadata == {}
        assert result.reranking_stages_applied == []
        assert result.timing == {}

    def test_create_with_timing(self):
        """Test creating a PipelineResult with timing info."""
        analysis = QueryAnalysis(original_query="test")
        result = PipelineResult(
            results=[],
            query_analysis=analysis,
            timing={"query_analysis": 0.1, "search": 0.5},
        )
        assert result.timing["query_analysis"] == 0.1
        assert result.timing["search"] == 0.5


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_config(self):
        """Test default pipeline configuration."""
        config = PipelineConfig()
        assert config.enable_query_expansion is True
        assert config.enable_reranking is True
        assert config.reranking_stages == ["feature", "cross_encoder"]
        assert config.fusion_strategy == "reciprocal_rank"
        assert config.max_results == 20
        assert config.cache_enabled is True
        assert config.cache_ttl == 3600
        assert config.cache_backend == "memory"

    def test_custom_config(self):
        """Test custom pipeline configuration."""
        config = PipelineConfig(
            enable_query_expansion=False,
            enable_reranking=False,
            reranking_stages=["bm25"],
            max_results=50,
            cache_enabled=False,
        )
        assert config.enable_query_expansion is False
        assert config.enable_reranking is False
        assert config.reranking_stages == ["bm25"]
        assert config.max_results == 50
        assert config.cache_enabled is False


class TestQueryAnalysisStage:
    """Tests for QueryAnalysisStage class."""

    def test_process_informational_query(self):
        """Test processing an informational query."""
        stage = QueryAnalysisStage()
        result = stage.process("What is entity spawning?")
        assert result.query_type == QueryType.INFORMATIONAL
        assert result.complexity in [ComplexityLevel.SIMPLE, ComplexityLevel.STANDARD, ComplexityLevel.COMPLEX]

    def test_process_navigational_query(self):
        """Test processing a navigational query."""
        stage = QueryAnalysisStage()
        result = stage.process("Minecraft documentation link")
        assert result.query_type == QueryType.NAVIGATIONAL

    def test_process_transactional_query(self):
        """Test processing a transactional query."""
        stage = QueryAnalysisStage()
        result = stage.process("Download mod installer")
        assert result.query_type == QueryType.TRANSACTIONAL

    def test_process_simple_query(self):
        """Test processing a simple query."""
        stage = QueryAnalysisStage()
        result = stage.process("spawn entity")
        assert result.query_type == QueryType.SIMPLE

    def test_process_empty_query(self):
        """Test processing an empty query."""
        stage = QueryAnalysisStage()
        result = stage.process("")
        # Empty query should default to SIMPLE
        assert result.query_type == QueryType.SIMPLE

    def test_get_config(self):
        """Test getting stage configuration."""
        stage = QueryAnalysisStage()
        config = stage.get_config()
        assert isinstance(config, dict)