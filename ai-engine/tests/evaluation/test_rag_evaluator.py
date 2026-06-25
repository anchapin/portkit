"""
Unit tests for evaluation/rag_evaluator.py

Covers RetrievalMetrics (precision/recall/F1/MRR/NDCG/hit-rate),
GenerationMetrics (keyword coverage/prohibition, length appropriateness,
citation quality, coherence), DiversityMetrics, GoldenDatasetItem,
EvaluationResult, and RAGEvaluator setup. Tests do not require a live
RAG agent — we exercise the pure metric functions directly.
"""

from unittest.mock import Mock

import pytest

from evaluation.rag_evaluator import (
    DiversityMetrics,
    EvaluationResult,
    GenerationMetrics,
    GoldenDatasetItem,
    MetricType,
    RAGEvaluator,
    RetrievalMetrics,
)


pytestmark = pytest.mark.unit


# -----------------------------------------------------------------------
# MetricType enum
# -----------------------------------------------------------------------


class TestMetricType:
    def test_values(self):
        assert MetricType.RETRIEVAL.value == "retrieval"
        assert MetricType.GENERATION.value == "generation"
        assert MetricType.RELEVANCE.value == "relevance"
        assert MetricType.DIVERSITY.value == "diversity"
        assert MetricType.EFFICIENCY.value == "efficiency"
        assert MetricType.USER_SATISFACTION.value == "user_satisfaction"

    def test_is_string_enum(self):
        # It should behave like a string
        assert MetricType.RETRIEVAL == "retrieval"


# -----------------------------------------------------------------------
# RetrievalMetrics
# -----------------------------------------------------------------------


class TestRetrievalMetrics:
    """Cover the static metric calculators."""

    def test_precision_at_k_perfect(self):
        assert RetrievalMetrics.precision_at_k(["a", "b", "c"], ["a", "b", "c"], 3) == 1.0

    def test_precision_at_k_partial(self):
        # 2 of 3 retrieved are relevant
        assert RetrievalMetrics.precision_at_k(["a", "x", "b"], ["a", "b"], 3) == pytest.approx(
            2 / 3
        )

    def test_precision_at_k_k_truncates(self):
        # Only consider top-k
        assert (
            RetrievalMetrics.precision_at_k(["a", "b", "c", "d"], ["c", "d"], 2) == 0.0
        )  # Top-2 has 0 relevant

    def test_precision_at_k_empty_retrieved(self):
        assert RetrievalMetrics.precision_at_k([], ["a"], 5) == 0.0

    def test_precision_at_k_k_zero(self):
        assert RetrievalMetrics.precision_at_k(["a"], ["a"], 0) == 0.0

    def test_recall_at_k_perfect(self):
        assert RetrievalMetrics.recall_at_k(["a", "b", "c"], ["a", "b"], 3) == 1.0

    def test_recall_at_k_partial(self):
        # 1 of 2 relevant docs retrieved
        assert RetrievalMetrics.recall_at_k(["a", "x"], ["a", "b"], 2) == 0.5

    def test_recall_at_k_empty_relevant(self):
        # No relevant docs, so recall is 1 if no retrieved
        assert RetrievalMetrics.recall_at_k([], [], 5) == 1.0
        # But 0 if anything is retrieved
        assert RetrievalMetrics.recall_at_k(["x"], [], 5) == 0.0

    def test_f1_at_k_perfect(self):
        assert RetrievalMetrics.f1_at_k(["a", "b"], ["a", "b"], 2) == 1.0

    def test_f1_at_k_no_overlap(self):
        assert RetrievalMetrics.f1_at_k(["x"], ["y"], 1) == 0.0

    def test_f1_at_k_mixed(self):
        # precision=0.5, recall=0.5 -> F1=0.5
        assert RetrievalMetrics.f1_at_k(["a", "x"], ["a", "y"], 2) == pytest.approx(0.5)

    def test_mrr_first_relevant(self):
        assert RetrievalMetrics.mean_reciprocal_rank(["a", "b"], ["a"]) == 1.0

    def test_mrr_second_relevant(self):
        assert RetrievalMetrics.mean_reciprocal_rank(["x", "a", "b"], ["a"]) == pytest.approx(0.5)

    def test_mrr_third_relevant(self):
        assert RetrievalMetrics.mean_reciprocal_rank(["x", "y", "a"], ["a"]) == pytest.approx(1 / 3)

    def test_mrr_no_relevant(self):
        assert RetrievalMetrics.mean_reciprocal_rank(["x", "y"], ["a"]) == 0.0

    def test_mrr_empty(self):
        assert RetrievalMetrics.mean_reciprocal_rank([], ["a"]) == 0.0

    def test_ndcg_perfect_order(self):
        # All relevant docs in order
        ndcg = RetrievalMetrics.normalized_discounted_cumulative_gain(["a", "b"], ["a", "b"])
        assert ndcg == pytest.approx(1.0)

    def test_ndcg_reversed_order_with_graded_relevance(self):
        # With graded relevance, a wrong order reduces NDCG
        ndcg = RetrievalMetrics.normalized_discounted_cumulative_gain(
            ["b", "a"],
            ["a", "b"],
            relevance_scores={"a": 3.0, "b": 1.0},
        )
        assert 0.0 < ndcg < 1.0

    def test_ndcg_empty(self):
        assert RetrievalMetrics.normalized_discounted_cumulative_gain([], ["a"]) == 0.0

    def test_ndcg_with_custom_relevance(self):
        # Custom relevance scores
        ndcg = RetrievalMetrics.normalized_discounted_cumulative_gain(
            ["a", "b", "c"],
            ["a", "b", "c"],
            relevance_scores={"a": 3.0, "b": 2.0, "c": 1.0},
        )
        # Perfect ordering
        assert ndcg == pytest.approx(1.0)

    def test_ndcg_zero_relevance(self):
        # IDCG is zero -> NDCG is zero
        ndcg = RetrievalMetrics.normalized_discounted_cumulative_gain(["a", "b"], [])
        assert ndcg == 0.0

    def test_hit_rate_positive(self):
        assert RetrievalMetrics.hit_rate(["a", "x"], ["a"]) == 1.0

    def test_hit_rate_negative(self):
        assert RetrievalMetrics.hit_rate(["x", "y"], ["a"]) == 0.0

    def test_hit_rate_empty(self):
        assert RetrievalMetrics.hit_rate([], ["a"]) == 0.0


# -----------------------------------------------------------------------
# GenerationMetrics
# -----------------------------------------------------------------------


class TestGenerationMetrics:
    """Cover generation-side metrics."""

    def test_keyword_coverage_all_present(self):
        assert (
            GenerationMetrics.keyword_coverage("Blocks and items are fun", ["blocks", "items"])
            == 1.0
        )

    def test_keyword_coverage_partial(self):
        # 1 of 2 keywords present
        assert GenerationMetrics.keyword_coverage("Blocks are fun", ["blocks", "items"]) == 0.5

    def test_keyword_coverage_none(self):
        assert GenerationMetrics.keyword_coverage("Hello", ["blocks", "items"]) == 0.0

    def test_keyword_coverage_empty_required(self):
        # No requirements -> trivially 1.0
        assert GenerationMetrics.keyword_coverage("anything", []) == 1.0

    def test_keyword_coverage_case_insensitive(self):
        assert GenerationMetrics.keyword_coverage("BLOCKS and Items", ["blocks", "items"]) == 1.0

    def test_keyword_prohibition_compliance_all_clean(self):
        assert (
            GenerationMetrics.keyword_prohibition_compliance("Hello world", ["bad", "evil"]) == 1.0
        )

    def test_keyword_prohibition_compliance_some_present(self):
        # 1 of 2 prohibited keywords present
        assert GenerationMetrics.keyword_prohibition_compliance("Hello bad", ["bad", "evil"]) == 0.5

    def test_keyword_prohibition_compliance_all_present(self):
        assert (
            GenerationMetrics.keyword_prohibition_compliance("bad and evil", ["bad", "evil"]) == 0.0
        )

    def test_keyword_prohibition_compliance_empty_list(self):
        assert GenerationMetrics.keyword_prohibition_compliance("anything", []) == 1.0

    def test_answer_length_in_range(self):
        # How-to range: 100-300 words
        answer = " ".join(["word"] * 150)
        score = GenerationMetrics.answer_length_appropriateness(answer, "how_to")
        assert score == 1.0

    def test_answer_length_too_short(self):
        # 50 words for how-to (needs 100-300)
        answer = " ".join(["word"] * 50)
        score = GenerationMetrics.answer_length_appropriateness(answer, "how_to")
        # Score = answer/min = 50/100 = 0.5
        assert score == pytest.approx(0.5)

    def test_answer_length_too_long(self):
        # 500 words for how-to (needs 100-300)
        answer = " ".join(["word"] * 500)
        score = GenerationMetrics.answer_length_appropriateness(answer, "how_to")
        # Penalty applied
        assert 0.0 <= score < 1.0

    def test_answer_length_unknown_type_uses_default(self):
        # Default range is 30-200
        answer = " ".join(["word"] * 100)
        score = GenerationMetrics.answer_length_appropriateness(answer, "unknown")
        assert score == 1.0

    def test_source_citation_quality_no_sources(self):
        assert GenerationMetrics.source_citation_quality("any answer", []) == 0.0

    def test_source_citation_quality_with_citations(self):
        # Sources referencing "According to" should boost score
        source = Mock()
        source.document.source_path = "block_guide.md"
        answer = "According to the block_guide, you can create blocks easily."
        score = GenerationMetrics.source_citation_quality(answer, [source])
        assert score > 0.0

    def test_source_citation_quality_no_indicators(self):
        source = Mock()
        source.document.source_path = "guide.md"
        # No citation indicators, no filename match
        answer = "Use this pattern."
        score = GenerationMetrics.source_citation_quality(answer, [source])
        assert score == 0.0

    def test_coherence_score_empty(self):
        assert GenerationMetrics.coherence_score("") == 0.0

    def test_coherence_score_single_sentence(self):
        # Single sentence gets medium score
        score = GenerationMetrics.coherence_score("This is a single sentence.")
        assert score == 0.5

    def test_coherence_score_multi_sentence(self):
        # Multi-sentence with structure gets a higher score
        answer = (
            "First, you create the block.\n\n"
            "Then, you register it. Therefore, the block is available in the game. "
            "For example, you can place it.\n\n"
            "Finally, you test it. 1. Step one. 2. Step two."
        )
        score = GenerationMetrics.coherence_score(answer)
        assert score > 0.5

    def test_coherence_score_capped_at_one(self):
        answer = "First, second, third. Therefore, however. For example. 1. 2. 3. - a. b."
        score = GenerationMetrics.coherence_score(answer)
        assert score <= 1.0


# -----------------------------------------------------------------------
# DiversityMetrics
# -----------------------------------------------------------------------


class TestDiversityMetrics:
    """Cover diversity metrics — these use SearchResult-shaped objects."""

    def _make_source(self, content_type: str, path: str, tags: list):
        source = Mock()
        source.document.content_type = content_type
        source.document.source_path = path
        source.document.tags = tags
        return source

    def test_content_type_diversity_empty(self):
        assert DiversityMetrics.content_type_diversity([]) == 0.0

    def test_content_type_diversity_single(self):
        sources = [self._make_source("doc", "/a.md", [])]
        # max_diversity = min(4, len(sources)) = 1, unique = 1 -> 1.0
        assert DiversityMetrics.content_type_diversity(sources) == 1.0

    def test_content_type_diversity_max(self):
        sources = [
            self._make_source("a", "/a", []),
            self._make_source("b", "/b", []),
            self._make_source("c", "/c", []),
            self._make_source("d", "/d", []),
        ]
        # 4 unique types out of max 4 = 1.0
        assert DiversityMetrics.content_type_diversity(sources) == 1.0

    def test_content_type_diversity_half(self):
        # 2 unique types across 4 sources
        sources = [
            self._make_source("a", "/a", []),
            self._make_source("a", "/b", []),
            self._make_source("b", "/c", []),
            self._make_source("b", "/d", []),
        ]
        # 2 unique / min(4, 4) = 0.5
        assert DiversityMetrics.content_type_diversity(sources) == 0.5

    def test_source_diversity_all_unique(self):
        sources = [
            self._make_source("a", "/a.md", []),
            self._make_source("b", "/b.md", []),
        ]
        assert DiversityMetrics.source_diversity(sources) == 1.0

    def test_source_diversity_duplicates(self):
        sources = [
            self._make_source("a", "/a.md", []),
            self._make_source("b", "/a.md", []),
        ]
        assert DiversityMetrics.source_diversity(sources) == 0.5

    def test_source_diversity_empty(self):
        assert DiversityMetrics.source_diversity([]) == 0.0

    def test_topic_diversity_score(self):
        sources = [
            self._make_source("a", "/a", ["x", "y", "z"]),  # 3 unique
            self._make_source("b", "/b", ["x", "y", "z"]),  # 0 new unique
        ]
        # 3 unique / 6 total = 0.5
        assert DiversityMetrics.topic_diversity_score(sources) == 0.5

    def test_topic_diversity_no_tags(self):
        sources = [self._make_source("a", "/a", [])]
        assert DiversityMetrics.topic_diversity_score(sources) == 0.0

    def test_topic_diversity_empty(self):
        assert DiversityMetrics.topic_diversity_score([]) == 0.0


# -----------------------------------------------------------------------
# GoldenDatasetItem
# -----------------------------------------------------------------------


class TestGoldenDatasetItem:
    """Cover the dataclass that defines golden test items."""

    def test_minimum_constructible(self):
        item = GoldenDatasetItem(
            query_id="q1",
            query_text="What is X?",
            query_type="explanation",
            difficulty_level="beginner",
            domain="blocks",
            expected_answer="X is a thing",
            expected_sources=["src1"],
            required_keywords=["X"],
            prohibited_keywords=[],
            min_sources=1,
            max_response_time_ms=1000.0,
            min_confidence=0.5,
            content_types=None,
            metadata={},
        )
        assert item.query_id == "q1"
        assert item.content_types is None


# -----------------------------------------------------------------------
# EvaluationResult
# -----------------------------------------------------------------------


class TestEvaluationResult:
    """Cover EvaluationResult serialization."""

    def test_to_dict_with_response(self):
        # Mock a RAGResponse with to_dict
        response = Mock()
        response.to_dict = Mock(return_value={"answer": "hi", "sources": []})
        result = EvaluationResult(
            query_id="q1",
            query_text="what?",
            expected_answer="answer",
            expected_sources=["s1"],
            actual_response=response,
            metrics={"p": 0.5},
            passed_tests=["p"],
            failed_tests=[],
            evaluation_timestamp="2024-01-01T00:00:00Z",
        )
        d = result.to_dict()
        assert d["query_id"] == "q1"
        assert d["actual_response"] == {"answer": "hi", "sources": []}
        assert d["metrics"] == {"p": 0.5}

    def test_to_dict_with_none_response(self):
        result = EvaluationResult(
            query_id="q1",
            query_text="what?",
            expected_answer=None,
            expected_sources=[],
            actual_response=None,
            metrics={},
            passed_tests=[],
            failed_tests=["err"],
            evaluation_timestamp="2024-01-01T00:00:00Z",
        )
        d = result.to_dict()
        assert d["actual_response"] is None


# -----------------------------------------------------------------------
# RAGEvaluator
# -----------------------------------------------------------------------


class TestRAGEvaluator:
    """Cover RAGEvaluator setup and sample-dataset creation."""

    def test_init_empty_state(self):
        ev = RAGEvaluator()
        assert ev.golden_dataset == []
        assert ev.evaluation_history == []
        assert MetricType.RETRIEVAL in ev.metrics_calculators
        assert MetricType.GENERATION in ev.metrics_calculators
        assert MetricType.DIVERSITY in ev.metrics_calculators

    def test_create_sample_golden_dataset(self):
        ev = RAGEvaluator()
        sample = ev.create_sample_golden_dataset()
        assert len(sample) == 3
        assert sample[0].query_id == "blocks_001"
        assert sample[1].domain == "recipes"
        assert sample[2].metadata.get("platform") == "bedrock"
        # The dataset is also stored on the instance
        assert ev.golden_dataset == sample

    def test_get_evaluation_history_empty(self):
        ev = RAGEvaluator()
        assert ev.get_evaluation_history() == []

    def test_load_golden_dataset_missing_file(self, tmp_path):
        ev = RAGEvaluator()
        result = ev.load_golden_dataset(str(tmp_path / "nope.json"))
        assert result == 0
        assert ev.golden_dataset == []

    def test_load_golden_dataset_invalid_json(self, tmp_path):
        ev = RAGEvaluator()
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all {")
        result = ev.load_golden_dataset(str(bad))
        assert result == 0

    def test_load_golden_dataset_valid_file(self, tmp_path):
        ev = RAGEvaluator()
        good = tmp_path / "good.json"
        good.write_text(
            '{"items": [{"query_id": "q1", "query_text": "t", '
            '"query_type": "explanation", "difficulty_level": "beginner", '
            '"domain": "blocks", "expected_answer": null, '
            '"expected_sources": [], "required_keywords": [], '
            '"prohibited_keywords": [], "min_sources": 1, '
            '"max_response_time_ms": 1000, "min_confidence": 0.5, '
            '"content_types": null, "metadata": {}}]}'
        )
        result = ev.load_golden_dataset(str(good))
        assert result == 1
        assert len(ev.golden_dataset) == 1
        assert ev.golden_dataset[0].query_id == "q1"

    def test_export_evaluation_report(self, tmp_path):
        ev = RAGEvaluator()
        report = {"overall_score": 0.85, "details": "x"}
        out = tmp_path / "report.json"
        ev.export_evaluation_report(report, str(out))
        import json

        with open(out) as f:
            loaded = json.load(f)
        assert loaded["overall_score"] == 0.85
