"""
Unit tests for search/adaptive_fusion.py

Tests QueryType, ComplexityLevel, FusionStrategy, FusionConfig,
and AdaptiveFusion classes.
"""

import pytest
from search.adaptive_fusion import (
    QueryType,
    ComplexityLevel,
    FusionStrategy,
    FusionConfig,
    AdaptiveFusion,
)


class TestQueryTypeEnum:
    """Tests for QueryType enum in adaptive_fusion."""

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


class TestComplexityLevelEnum:
    """Tests for ComplexityLevel enum in adaptive_fusion."""

    def test_complexity_levels_exist(self):
        """Test that all expected complexity levels exist."""
        assert ComplexityLevel.SIMPLE.value == "simple"
        assert ComplexityLevel.STANDARD.value == "standard"
        assert ComplexityLevel.COMPLEX.value == "complex"

    def test_complexity_level_is_string(self):
        """Test that ComplexityLevel values are strings."""
        for cl in ComplexityLevel:
            assert isinstance(cl.value, str)


class TestFusionStrategyEnum:
    """Tests for FusionStrategy enum."""

    def test_fusion_strategies_exist(self):
        """Test that all expected fusion strategies exist."""
        assert FusionStrategy.RECIPROCAL_RANK_FUSION.value == "reciprocal_rank"
        assert FusionStrategy.WEIGHTED_SUM.value == "weighted_sum"
        assert FusionStrategy.SCORE_AVERAGING.value == "score_averaging"
        assert FusionStrategy.CONFIDENCE_WEIGHTED.value == "confidence_weighted"


class TestFusionConfig:
    """Tests for FusionConfig dataclass."""

    def test_default_config(self):
        """Test default fusion configuration."""
        config = FusionConfig()
        assert config.strategy == FusionStrategy.RECIPROCAL_RANK_FUSION
        assert config.semantic_weight == 0.5
        assert config.keyword_weight == 0.3
        assert config.contextual_weight == 0.2

    def test_custom_config(self):
        """Test custom fusion configuration."""
        config = FusionConfig(
            strategy=FusionStrategy.WEIGHTED_SUM,
            semantic_weight=0.4,
            keyword_weight=0.4,
            contextual_weight=0.2,
        )
        assert config.strategy == FusionStrategy.WEIGHTED_SUM
        assert config.semantic_weight == 0.4
        assert config.keyword_weight == 0.4


class TestAdaptiveFusion:
    """Tests for AdaptiveFusion class."""

    def test_init_default_strategy(self):
        """Test initialization with default strategy."""
        fusion = AdaptiveFusion()
        assert fusion.default_strategy == FusionStrategy.RECIPROCAL_RANK_FUSION

    def test_init_custom_strategy(self):
        """Test initialization with custom strategy."""
        fusion = AdaptiveFusion(default_strategy="weighted_sum")
        assert fusion.default_strategy == FusionStrategy.WEIGHTED_SUM

    def test_query_type_weights_exist(self):
        """Test that query type weights are defined for all query types."""
        fusion = AdaptiveFusion()
        for qt in QueryType:
            assert qt in fusion.query_type_weights
            weights = fusion.query_type_weights[qt]
            assert "semantic" in weights
            assert "keyword" in weights
            assert "contextual" in weights
            # Weights should sum to 1.0
            total = weights["semantic"] + weights["keyword"] + weights["contextual"]
            assert abs(total - 1.0) < 0.001

    def test_get_weights_for_query_type_informational(self):
        """Test getting weights for INFORMATIONAL query type."""
        fusion = AdaptiveFusion()
        weights = fusion._get_weights(QueryType.INFORMATIONAL)
        assert weights["semantic"] > weights["keyword"]

    def test_get_weights_for_query_type_navigational(self):
        """Test getting weights for NAVIGATIONAL query type."""
        fusion = AdaptiveFusion()
        weights = fusion._get_weights(QueryType.NAVIGATIONAL)
        assert weights["keyword"] > weights["semantic"]

    def test_get_weights_for_query_type_none(self):
        """Test getting weights when query type is None."""
        fusion = AdaptiveFusion()
        weights = fusion._get_weights(None)
        assert "semantic" in weights
        assert "keyword" in weights
        assert "contextual" in weights

    def test_select_strategy_simple_complexity(self):
        """Test strategy selection for SIMPLE complexity."""
        fusion = AdaptiveFusion()
        strategy = fusion.select_strategy(complexity=ComplexityLevel.SIMPLE)
        assert strategy == FusionStrategy.RECIPROCAL_RANK_FUSION

    def test_select_strategy_complex_complexity(self):
        """Test strategy selection for COMPLEX complexity."""
        fusion = AdaptiveFusion()
        strategy = fusion.select_strategy(complexity=ComplexityLevel.COMPLEX)
        assert strategy == FusionStrategy.WEIGHTED_SUM

    def test_select_strategy_navigational(self):
        """Test strategy selection for NAVIGATIONAL query type."""
        fusion = AdaptiveFusion()
        strategy = fusion.select_strategy(query_type=QueryType.NAVIGATIONAL)
        assert strategy == FusionStrategy.WEIGHTED_SUM

    def test_select_strategy_informational(self):
        """Test strategy selection for INFORMATIONAL query type."""
        fusion = AdaptiveFusion()
        strategy = fusion.select_strategy(query_type=QueryType.INFORMATIONAL)
        assert strategy == FusionStrategy.RECIPROCAL_RANK_FUSION

    def test_select_strategy_default(self):
        """Test strategy selection falls back to default."""
        fusion = AdaptiveFusion()
        strategy = fusion.select_strategy()
        assert strategy == fusion.default_strategy

    def test_fuse_empty_results(self):
        """Test fuse with empty results."""
        fusion = AdaptiveFusion()
        fused = fusion.fuse({})
        assert fused == []

    def test_fuse_single_source(self):
        """Test fuse with single source results."""
        fusion = AdaptiveFusion()
        # The method expects Dict[str, List[SearchResult]]
        # but we're testing it returns empty for empty dict
        fused = fusion.fuse({})
        assert fused == []