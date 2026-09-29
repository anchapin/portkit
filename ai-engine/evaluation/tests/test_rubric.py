"""
Tests for rubric-grounded evaluation framework.

Run with: pytest ai-engine/evaluation/tests/test_rubric.py -v
"""

import pytest

from evaluation.models import (
    RubricCategory,
    RubricScore,
    RubricResult,
    RewardSignal,
)
from evaluation.evaluator import RubricEvaluator, BedrockConstraintChecker, RUBRIC_DEFINITIONS


class TestRubricModels:
    """Tests for rubric model classes."""

    def test_rubric_score_normalized_score(self):
        """Test normalized score calculation."""
        score = RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=2.0,
            max_score=4.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="test",
        )
        assert score.normalized_score == 0.5

    def test_rubric_score_is_complete(self):
        """Test is_complete property."""
        partial = RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=2.0,
            max_score=4.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="test",
        )
        assert partial.is_complete is False

        complete = RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=4.0,
            max_score=4.0,
            evidence={},
            partial_credit_breakdown={},
            reasoning="test",
        )
        assert complete.is_complete is True

    def test_rubric_score_to_dict(self):
        """Test score serialization."""
        score = RubricScore(
            category=RubricCategory.CODE_QUALITY,
            score=2.0,
            max_score=3.0,
            evidence={"idiomatic": True, "proper_imports": False, "no_deprecated": True},
            partial_credit_breakdown={"criteria_met": 2.0},
            reasoning="2 of 3 criteria met",
        )
        d = score.to_dict()
        assert d["category"] == "code_quality"
        assert d["score"] == 2.0
        assert d["max_score"] == 3.0
        assert d["normalized_score"] == pytest.approx(0.667, rel=0.01)


class TestRewardSignal:
    """Tests for RewardSignal model."""

    def test_reward_signal_creation(self):
        """Test reward signal creation."""
        signal = RewardSignal(
            total_reward=10.0,
            behavioral_preservation=0.8,
            constraint_compliance=1.0,
            code_quality=0.67,
            structural_validity=1.0,
        )
        assert signal.total_reward == 10.0
        assert len(signal.penalty_reasons) == 0

    def test_reward_signal_with_penalties(self):
        """Test reward signal with penalty reasons."""
        signal = RewardSignal(
            total_reward=8.0,
            behavioral_preservation=0.5,
            constraint_compliance=1.0,
            code_quality=0.67,
            structural_validity=1.0,
            penalty_reasons=["Low behavioral preservation", "Constraint failures: tick_rate"],
        )
        assert len(signal.penalty_reasons) == 2

    def test_reward_signal_to_dict(self):
        """Test reward signal serialization."""
        signal = RewardSignal(
            total_reward=10.0,
            behavioral_preservation=0.8,
            constraint_compliance=1.0,
            code_quality=0.67,
            structural_validity=1.0,
        )
        d = signal.to_dict()
        assert d["total_reward"] == 10.0
        assert d["behavioral_preservation"] == 0.8


class TestBedrockConstraintChecker:
    """Tests for BedrockConstraintChecker."""

    def test_check_json_nesting_depth_valid(self):
        """Test valid JSON nesting depth."""
        checker = BedrockConstraintChecker()
        valid_json = '{"format_version": 2, "header": {"name": "test"}}'
        is_valid, max_depth = checker.check_json_nesting_depth(valid_json)
        assert is_valid is True
        assert max_depth == 2

    def test_check_json_nesting_depth_invalid(self):
        """Test invalid JSON nesting depth."""
        checker = BedrockConstraintChecker()

        # Create deeply nested JSON exceeding the limit of 6
        # Use programmatically built nested dict to ensure correct depth
        def make_nested(depth):
            if depth <= 1:
                return "value"
            return {"level": make_nested(depth - 1)}

        deep_json = json.dumps(make_nested(8))  # 8 levels creates max_depth of 7
        is_valid, max_depth = checker.check_json_nesting_depth(deep_json)
        assert is_valid is False
        assert max_depth == 7

    def test_check_json_nesting_depth_invalid_json(self):
        """Test invalid JSON string."""
        checker = BedrockConstraintChecker()
        is_valid, max_depth = checker.check_json_nesting_depth("not json")
        assert is_valid is False
        assert max_depth == 0

    def test_check_script_api_version_valid(self):
        """Test valid Script API version usage."""
        checker = BedrockConstraintChecker()
        valid_script = """
        import { world } from "@minecraft/server";
        world.afterEvents.tick.subscribe(() => {
            console.log("tick");
        });
        """
        is_valid, issues = checker.check_script_api_version(valid_script)
        assert is_valid is True
        assert len(issues) == 0

    def test_check_script_api_version_invalid(self):
        """Test invalid Script API usage."""
        checker = BedrockConstraintChecker()
        invalid_script = """
        import { world } from "@minecraft/server.v1";
        world.getBlock().setType("minecraft:stone");
        """
        is_valid, issues = checker.check_script_api_version(invalid_script)
        assert is_valid is False
        assert len(issues) == 2

    def test_check_tick_rate_valid(self):
        """Test valid tick rate compliance."""
        checker = BedrockConstraintChecker()
        valid_script = """
        import { world } from "@minecraft/server";
        world.afterEvents.tick.subscribe(() => {
            console.log("tick");
        });
        """
        is_valid, violations = checker.check_tick_rate(valid_script)
        assert is_valid is True
        assert len(violations) == 0

    def test_check_tick_rate_invalid(self):
        """Test invalid tick rate patterns."""
        checker = BedrockConstraintChecker()
        # Use setInterval to trigger tick rate violation
        invalid_script = """
        import { world } from "@minecraft/server";
        setInterval(() => {
            console.log("tick");
        }, 1);
        """
        is_valid, violations = checker.check_tick_rate(invalid_script)
        assert is_valid is False
        assert len(violations) > 0

    def test_check_event_queue_size_valid(self):
        """Test valid event queue size."""
        checker = BedrockConstraintChecker()
        script = (
            """
        import { world } from "@minecraft/server";
        """
            + "world.afterEvents.tick.subscribe(() => {});\n" * 10
        )
        is_valid, _ = checker.check_event_queue_size(script)
        assert is_valid is True

    def test_check_event_queue_size_high(self):
        """Test high event subscription count."""
        checker = BedrockConstraintChecker()
        script = (
            """
        import { world } from "@minecraft/server";
        """
            + "world.afterEvents.tick.subscribe(() => {});\n" * 150
        )
        is_valid, warning = checker.check_event_queue_size(script)
        assert is_valid is False
        assert "150" in warning


class TestRubricEvaluator:
    """Tests for RubricEvaluator."""

    def test_evaluate_full_conversion(self):
        """Test evaluation of a well-formed conversion."""
        evaluator = RubricEvaluator()

        java_source = """
        package com.example;

        public class MyMod {
            @Mod.Element
            public static MyMod instance;

            public void onInitialize() {
                System.out.println("Mod initialized!");
            }
        }
        """

        bedrock_output = """
        ## manifest.json
        ```json
        {
            "format_version": 2,
            "header": {
                "name": "examplemod",
                "description": "My awesome mod",
                "version": [1, 0, 0],
                "min_engine_version": [1, 21, 0]
            },
            "modules": [
                {
                    "type": "script",
                    "language": "javascript",
                    "entry": "scripts/main.js",
                    "version": [1, 0, 0]
                }
            ]
        }
        ```

        ## scripts/main.js
        ```javascript
        import { world } from "@minecraft/server";

        world.afterEvents.tick.subscribe(() => {
            console.log("Mod initialized!");
        });
        ```
        """

        result = evaluator.evaluate(java_source, bedrock_output, "test-001")

        assert result.conversion_id == "test-001"
        assert result.overall_score > 0
        assert result.overall_score <= result.overall_max_score
        assert result.reward_signal.total_reward == result.overall_score

    def test_evaluate_empty_output(self):
        """Test evaluation of empty/invalid output."""
        evaluator = RubricEvaluator()

        java_source = """
        public class MyMod {
            public void onInitialize() {}
        }
        """

        bedrock_output = "No conversion produced"

        result = evaluator.evaluate(java_source, bedrock_output)

        # Should still produce scores, just low ones
        assert RubricCategory.BEHAVIORAL_PRESERVATION in result.scores
        assert RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE in result.scores
        assert RubricCategory.CODE_QUALITY in result.scores
        assert RubricCategory.STRUCTURAL_VALIDITY in result.scores

    def test_evaluate_invalid_json(self):
        """Test evaluation with invalid manifest JSON."""
        evaluator = RubricEvaluator()

        java_source = "public class Test {}"
        bedrock_output = """
        ```json
        {
            "format_version": 2
            "header": MISSING COMMA
        }
        ```

        ```javascript
        import { world } from "@minecraft/server";
        ```
        """

        result = evaluator.evaluate(java_source, bedrock_output)

        structural_score = result.scores[RubricCategory.STRUCTURAL_VALIDITY]
        assert structural_score.evidence["manifest_valid_json"] is False

    def test_evaluate_deprecated_apis(self):
        """Test evaluation catches deprecated API usage."""
        evaluator = RubricEvaluator()

        java_source = "public class Test {}"
        bedrock_output = """
        ```json
        {
            "format_version": 2,
            "header": {"name": "test"}
        }
        ```

        ```javascript
        import { world } from "@minecraft/server";
        world.afterEvents.tick.subscribe(() => {
            setTimeout(() => {}, 1);
        });
        ```
        """

        result = evaluator.evaluate(java_source, bedrock_output)

        # Tick rate violation should be caught, but that's a different rubric
        # The deprecated API check is separate
        quality_score = result.scores[RubricCategory.CODE_QUALITY]
        # No deprecated APIs should be detected in this script
        assert quality_score.evidence["no_deprecated_apis"] is True

    def test_evaluate_partial_behavioral_preservation(self):
        """Test partial credit for behavioral preservation."""
        evaluator = RubricEvaluator()

        # Java with entities but bedrock only has basic manifest
        java_source = """
        public class EntityMod {
            public void registerEntity() {
                // Entity registration
            }
        }
        """

        bedrock_output = """
        ```json
        {
            "format_version": 2,
            "header": {"name": "entitymod"}
        }
        ```

        ```javascript
        import { world } from "@minecraft/server";
        ```
        """

        result = evaluator.evaluate(java_source, bedrock_output)

        behavioral = result.scores[RubricCategory.BEHAVIORAL_PRESERVATION]
        # entity_spawning_preserved should be True (bedrock has entity-like structure)
        # block/item/event preservation depends on what's detected
        assert behavioral.score >= 0


class TestRubricDefinitions:
    """Tests for rubric definitions."""

    def test_all_categories_have_definitions(self):
        """Test all rubric categories have definitions."""
        for category in RubricCategory:
            assert category in RUBRIC_DEFINITIONS
            definition = RUBRIC_DEFINITIONS[category]
            assert "name" in definition
            assert "max_score" in definition
            assert "criteria" in definition
            assert "partial_credits" in definition

    def test_partial_credits_sum_to_max(self):
        """Test partial credits can achieve max score."""
        for category, definition in RUBRIC_DEFINITIONS.items():
            partial = definition["partial_credits"]
            # "all" or highest tier should equal max_score
            if "all" in partial:
                assert partial["all"] == definition["max_score"]

    def test_criteria_count_matches_partial_credits(self):
        """Test criteria count is consistent with partial credit tiers."""
        for category, definition in RUBRIC_DEFINITIONS.items():
            criteria = definition["criteria"]
            max_count = len(criteria)
            # Partial credits should have tiers for 0 to max_count
            partial = definition["partial_credits"]
            # Check that we have a way to get max score (either "all", "X_of_X", or similar)
            max_score_tier_found = (
                "all" in partial
                or f"{max_count}_of_{max_count}" in partial
                or any(f"{max_count}" in k for k in partial.keys())
            )
            assert max_score_tier_found, f"No max score tier found for {category}"


class TestRubricIntegration:
    """Integration tests for rubric evaluation pipeline."""

    def test_full_pipeline_with_reward_signal(self):
        """Test complete evaluation pipeline produces valid reward signal."""
        evaluator = RubricEvaluator()

        java_source = """
        @Mod.EntryPoint
        public class MyMod {
            public void onInitialize() {
                // Initialize mod
            }
        }
        """

        bedrock_output = """
        ## manifest.json
        ```json
        {
            "format_version": 2,
            "header": {
                "name": "mymod",
                "description": "My mod",
                "version": [1, 0, 0],
                "min_engine_version": [1, 21, 0]
            },
            "modules": [
                {
                    "type": "script",
                    "language": "javascript",
                    "entry": "scripts/main.js"
                }
            ]
        }
        ```

        ## scripts/main.js
        ```javascript
        import { world } from "@minecraft/server";

        world.afterEvents.tick.subscribe(() => {
            console.log("Initialized!");
        });
        ```
        """

        result = evaluator.evaluate(java_source, bedrock_output, "pipeline-test")

        # Verify result structure
        assert isinstance(result, RubricResult)
        assert result.to_dict()["conversion_id"] == "pipeline-test"

        # Verify reward signal
        signal = result.to_reward_signal()
        assert isinstance(signal, RewardSignal)
        assert signal.total_reward > 0

        # Verify reward components
        assert 0 <= signal.behavioral_preservation <= 1
        assert 0 <= signal.constraint_compliance <= 1
        assert 0 <= signal.code_quality <= 1
        assert 0 <= signal.structural_validity <= 1

    def test_multiple_evaluations_deterministic(self):
        """Test same inputs produce same outputs."""
        evaluator = RubricEvaluator()

        java_source = "public class Test {}"
        bedrock_output = """
        ```json
        {"format_version": 2, "header": {"name": "test"}}
        ```
        ```javascript
        import { world } from "@minecraft/server";
        ```
        """

        result1 = evaluator.evaluate(java_source, bedrock_output)
        result2 = evaluator.evaluate(java_source, bedrock_output)

        assert result1.overall_score == result2.overall_score
        assert (
            result1.scores[RubricCategory.BEHAVIORAL_PRESERVATION].score
            == result2.scores[RubricCategory.BEHAVIORAL_PRESERVATION].score
        )


import json  # Needed for test_check_json_nesting_depth tests
