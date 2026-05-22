"""Unit tests for evaluation.models module."""

import pytest

from evaluation.models import (
    BedrockConstraint,
    BedrockConstraintType,
    BEDROCK_CONSTRAINTS,
    RubricCategory,
    RubricResult,
    RubricScore,
    RewardSignal,
)


class TestRubricCategory:
    """Tests for RubricCategory enum."""

    def test_enum_values(self):
        """Test all rubric category enum values exist."""
        assert RubricCategory.BEHAVIORAL_PRESERVATION.value == "behavioral_preservation"
        assert RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE.value == "bedrock_constraint_compliance"
        assert RubricCategory.CODE_QUALITY.value == "code_quality"
        assert RubricCategory.STRUCTURAL_VALIDITY.value == "structural_validity"

    def test_enum_count(self):
        """Test there are exactly 4 rubric categories."""
        assert len(RubricCategory) == 4


class TestRubricScore:
    """Tests for RubricScore dataclass."""

    def test_init_basic(self):
        """Test RubricScore basic initialization."""
        score = RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=8.0,
            max_score=10.0,
            evidence={"feature_x": True, "feature_y": False},
            partial_credit_breakdown={"aspect_a": 5.0, "aspect_b": 3.0},
            reasoning="Good conversion with minor issues",
        )
        assert score.category == RubricCategory.BEHAVIORAL_PRESERVATION
        assert score.score == 8.0
        assert score.max_score == 10.0
        assert score.evidence == {"feature_x": True, "feature_y": False}
        assert score.partial_credit_breakdown == {"aspect_a": 5.0, "aspect_b": 3.0}
        assert score.reasoning == "Good conversion with minor issues"

    def test_normalized_score_valid(self):
        """Test normalized_score with valid max_score."""
        score = RubricScore(
            category=RubricCategory.CODE_QUALITY,
            score=7.5,
            max_score=10.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.normalized_score == 0.75

    def test_normalized_score_zero_max(self):
        """Test normalized_score when max_score is zero."""
        score = RubricScore(
            category=RubricCategory.STRUCTURAL_VALIDITY,
            score=0.0,
            max_score=0.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.normalized_score == 0.0

    def test_normalized_score_perfect(self):
        """Test normalized_score for perfect score."""
        score = RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=10.0,
            max_score=10.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.normalized_score == 1.0

    def test_normalized_score_partial(self):
        """Test normalized_score for partial credit."""
        score = RubricScore(
            category=RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE,
            score=3.0,
            max_score=10.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.normalized_score == 0.3

    def test_is_complete_true(self):
        """Test is_complete when score equals max_score."""
        score = RubricScore(
            category=RubricCategory.CODE_QUALITY,
            score=10.0,
            max_score=10.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.is_complete is True

    def test_is_complete_exceeds(self):
        """Test is_complete when score exceeds max_score (bonus)."""
        score = RubricScore(
            category=RubricCategory.STRUCTURAL_VALIDITY,
            score=12.0,
            max_score=10.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.is_complete is True

    def test_is_complete_false(self):
        """Test is_complete when score is less than max_score."""
        score = RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=7.0,
            max_score=10.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="",
        )
        assert score.is_complete is False

    def test_to_dict(self):
        """Test RubricScore serialization to dict."""
        score = RubricScore(
            category=RubricCategory.CODE_QUALITY,
            score=8.0,
            max_score=10.0,
            evidence={"check_a": True},
            partial_credit_breakdown={"item1": 4.0},
            reasoning="Test reasoning",
        )
        d = score.to_dict()
        assert d["category"] == "code_quality"
        assert d["score"] == 8.0
        assert d["max_score"] == 10.0
        assert d["normalized_score"] == 0.8
        assert d["evidence"] == {"check_a": True}
        assert d["partial_credit_breakdown"] == {"item1": 4.0}
        assert d["reasoning"] == "Test reasoning"


class TestRubricResult:
    """Tests for RubricResult dataclass."""

    def test_init_full(self):
        """Test RubricResult full initialization."""
        scores = {
            RubricCategory.BEHAVIORAL_PRESERVATION: RubricScore(
                category=RubricCategory.BEHAVIORAL_PRESERVATION,
                score=8.0,
                max_score=10.0,
                evidence={},
                partial_credit_breakdown={},
                reasoning="",
            ),
        }
        reward_signal = RewardSignal(
            total_reward=0.8,
            behavioral_preservation=0.8,
            constraint_compliance=0.0,
            code_quality=0.0,
            structural_validity=0.0,
        )
        result = RubricResult(
            conversion_id="conv-123",
            java_source="public class Test {}",
            bedrock_output="const test = {};",
            scores=scores,
            overall_score=8.0,
            overall_max_score=10.0,
            reward_signal=reward_signal,
            adjudication_notes="Good conversion",
        )
        assert result.conversion_id == "conv-123"
        assert result.java_source == "public class Test {}"
        assert result.bedrock_output == "const test = {};"
        assert len(result.scores) == 1
        assert result.overall_score == 8.0
        assert result.overall_max_score == 10.0
        assert result.adjudication_notes == "Good conversion"

    def test_init_without_conversion_id(self):
        """Test RubricResult initialization with no conversion_id."""
        result = RubricResult(
            conversion_id=None,
            java_source="class A {}",
            bedrock_output="const a = {};",
            scores={},
            overall_score=0.0,
            overall_max_score=10.0,
            reward_signal=RewardSignal(0.0, 0.0, 0.0, 0.0, 0.0),
            adjudication_notes="",
        )
        assert result.conversion_id is None

    def test_overall_normalized_valid(self):
        """Test overall_normalized with valid max_score."""
        result = RubricResult(
            conversion_id="test",
            java_source="",
            bedrock_output="",
            scores={},
            overall_score=7.5,
            overall_max_score=10.0,
            reward_signal=RewardSignal(0.75, 0.0, 0.0, 0.0, 0.0),
            adjudication_notes="",
        )
        assert result.overall_normalized == 0.75

    def test_overall_normalized_zero_max(self):
        """Test overall_normalized when max_score is zero."""
        result = RubricResult(
            conversion_id="test",
            java_source="",
            bedrock_output="",
            scores={},
            overall_score=0.0,
            overall_max_score=0.0,
            reward_signal=RewardSignal(0.0, 0.0, 0.0, 0.0, 0.0),
            adjudication_notes="",
        )
        assert result.overall_normalized == 0.0

    def test_overall_normalized_perfect(self):
        """Test overall_normalized for perfect score."""
        result = RubricResult(
            conversion_id="test",
            java_source="",
            bedrock_output="",
            scores={},
            overall_score=10.0,
            overall_max_score=10.0,
            reward_signal=RewardSignal(1.0, 0.0, 0.0, 0.0, 0.0),
            adjudication_notes="",
        )
        assert result.overall_normalized == 1.0

    def test_to_reward_signal(self):
        """Test to_reward_signal method."""
        reward_signal = RewardSignal(0.5, 0.1, 0.1, 0.1, 0.2)
        result = RubricResult(
            conversion_id="test",
            java_source="",
            bedrock_output="",
            scores={},
            overall_score=5.0,
            overall_max_score=10.0,
            reward_signal=reward_signal,
            adjudication_notes="",
        )
        assert result.to_reward_signal() is reward_signal

    def test_to_dict(self):
        """Test RubricResult serialization to dict."""
        scores = {
            RubricCategory.BEHAVIORAL_PRESERVATION: RubricScore(
                category=RubricCategory.BEHAVIORAL_PRESERVATION,
                score=8.0,
                max_score=10.0,
                evidence={},
                partial_credit_breakdown={},
                reasoning="",
            ),
        }
        reward_signal = RewardSignal(0.8, 0.8, 0.0, 0.0, 0.0)
        result = RubricResult(
            conversion_id="conv-456",
            java_source="class B {}",
            bedrock_output="const b = {};",
            scores=scores,
            overall_score=8.0,
            overall_max_score=10.0,
            reward_signal=reward_signal,
            adjudication_notes="Test notes",
        )
        d = result.to_dict()
        assert d["conversion_id"] == "conv-456"
        assert "behavioral_preservation" in d["scores"]
        assert d["overall_score"] == 8.0
        assert d["overall_max_score"] == 10.0
        assert d["overall_normalized"] == 0.8
        assert d["reward_signal"]["total_reward"] == 0.8
        assert d["adjudication_notes"] == "Test notes"


class TestRewardSignal:
    """Tests for RewardSignal dataclass."""

    def test_init_full(self):
        """Test RewardSignal full initialization."""
        signal = RewardSignal(
            total_reward=0.85,
            behavioral_preservation=0.9,
            constraint_compliance=0.8,
            code_quality=0.85,
            structural_validity=0.8,
            partial_credits={"aspect1": 0.1, "aspect2": 0.05},
            penalty_reasons=["penalty_a", "penalty_b"],
        )
        assert signal.total_reward == 0.85
        assert signal.behavioral_preservation == 0.9
        assert signal.constraint_compliance == 0.8
        assert signal.code_quality == 0.85
        assert signal.structural_validity == 0.8
        assert signal.partial_credits == {"aspect1": 0.1, "aspect2": 0.05}
        assert signal.penalty_reasons == ["penalty_a", "penalty_b"]

    def test_init_defaults(self):
        """Test RewardSignal with default partial_credits and penalty_reasons."""
        signal = RewardSignal(
            total_reward=0.5,
            behavioral_preservation=0.5,
            constraint_compliance=0.5,
            code_quality=0.5,
            structural_validity=0.5,
        )
        assert signal.partial_credits == {}
        assert signal.penalty_reasons == []

    def test_to_dict(self):
        """Test RewardSignal serialization to dict."""
        signal = RewardSignal(
            total_reward=0.75,
            behavioral_preservation=0.8,
            constraint_compliance=0.7,
            code_quality=0.75,
            structural_validity=0.75,
            partial_credits={"extra": 0.05},
            penalty_reasons=["late_penalty"],
        )
        d = signal.to_dict()
        assert d["total_reward"] == 0.75
        assert d["behavioral_preservation"] == 0.8
        assert d["constraint_compliance"] == 0.7
        assert d["code_quality"] == 0.75
        assert d["structural_validity"] == 0.75
        assert d["partial_credits"] == {"extra": 0.05}
        assert d["penalty_reasons"] == ["late_penalty"]


class TestBedrockConstraintType:
    """Tests for BedrockConstraintType enum."""

    def test_enum_values(self):
        """Test all Bedrock constraint type enum values."""
        assert BedrockConstraintType.TICK_RATE_LIMIT.value == "tick_rate_limit"
        assert BedrockConstraintType.JSON_NESTING_DEPTH.value == "json_nesting_depth"
        assert BedrockConstraintType.SCRIPT_API_VERSION.value == "script_api_version"
        assert BedrockConstraintType.EVENT_QUEUE_SIZE.value == "event_queue_size"
        assert BedrockConstraintType.WORLD_DATA_ACCESS.value == "world_data_access"
        assert BedrockConstraintType.BLOCK_STATE_LIMITS.value == "block_state_limits"

    def test_enum_count(self):
        """Test there are exactly 6 Bedrock constraint types."""
        assert len(BedrockConstraintType) == 6


class TestBedrockConstraint:
    """Tests for BedrockConstraint dataclass."""

    def test_init_full(self):
        """Test BedrockConstraint full initialization."""
        constraint = BedrockConstraint(
            constraint_type=BedrockConstraintType.TICK_RATE_LIMIT,
            description="Test description",
            max_value=20.0,
            min_value=0.0,
            applies_to="script_timing",
        )
        assert constraint.constraint_type == BedrockConstraintType.TICK_RATE_LIMIT
        assert constraint.description == "Test description"
        assert constraint.max_value == 20.0
        assert constraint.min_value == 0.0
        assert constraint.applies_to == "script_timing"

    def test_init_defaults(self):
        """Test BedrockConstraint with default values."""
        constraint = BedrockConstraint(
            constraint_type=BedrockConstraintType.WORLD_DATA_ACCESS,
            description="World access constraint",
        )
        assert constraint.max_value is None
        assert constraint.min_value is None
        assert constraint.applies_to == "all"

    def test_init_with_min_only(self):
        """Test BedrockConstraint with min_value only."""
        constraint = BedrockConstraint(
            constraint_type=BedrockConstraintType.SCRIPT_API_VERSION,
            description="API version constraint",
            min_value=2.0,
        )
        assert constraint.max_value is None
        assert constraint.min_value == 2.0

    def test_init_with_max_only(self):
        """Test BedrockConstraint with max_value only."""
        constraint = BedrockConstraint(
            constraint_type=BedrockConstraintType.JSON_NESTING_DEPTH,
            description="JSON depth constraint",
            max_value=6.0,
        )
        assert constraint.max_value == 6.0
        assert constraint.min_value is None


class TestBedrockConstraints:
    """Tests for BEDROCK_CONSTRAINTS predefined dict."""

    def test_all_constraint_types_defined(self):
        """Test all 6 constraint types are defined."""
        assert len(BEDROCK_CONSTRAINTS) == 6
        for constraint_type in BedrockConstraintType:
            assert constraint_type in BEDROCK_CONSTRAINTS

    def test_tick_rate_limit_constraint(self):
        """Test TICK_RATE_LIMIT constraint has correct values."""
        constraint = BEDROCK_CONSTRAINTS[BedrockConstraintType.TICK_RATE_LIMIT]
        assert constraint.max_value == 20.0
        assert constraint.applies_to == "script_timing"

    def test_json_nesting_depth_constraint(self):
        """Test JSON_NESTING_DEPTH constraint has correct values."""
        constraint = BEDROCK_CONSTRAINTS[BedrockConstraintType.JSON_NESTING_DEPTH]
        assert constraint.max_value == 6.0
        assert constraint.applies_to == "json_files"

    def test_script_api_version_constraint(self):
        """Test SCRIPT_API_VERSION constraint has correct values."""
        constraint = BEDROCK_CONSTRAINTS[BedrockConstraintType.SCRIPT_API_VERSION]
        assert constraint.min_value == 2.0
        assert constraint.applies_to == "script_imports"

    def test_event_queue_size_constraint(self):
        """Test EVENT_QUEUE_SIZE constraint has correct values."""
        constraint = BEDROCK_CONSTRAINTS[BedrockConstraintType.EVENT_QUEUE_SIZE]
        assert constraint.max_value == 1000.0
        assert constraint.applies_to == "event_handlers"

    def test_world_data_access_constraint(self):
        """Test WORLD_DATA_ACCESS constraint has correct values."""
        constraint = BEDROCK_CONSTRAINTS[BedrockConstraintType.WORLD_DATA_ACCESS]
        assert constraint.applies_to == "world_queries"
        assert constraint.max_value is None

    def test_block_state_limits_constraint(self):
        """Test BLOCK_STATE_LIMITS constraint has correct values."""
        constraint = BEDROCK_CONSTRAINTS[BedrockConstraintType.BLOCK_STATE_LIMITS]
        assert constraint.max_value == 16.0
        assert constraint.applies_to == "block_definitions"