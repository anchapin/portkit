"""
Minecraft-Specific Reward Models for Bedrock API Idiomaticity Scoring

Implements specialized reward models (RMs) for evaluating LLM-generated Bedrock code
based on the approach from Themis: Training Robust Multilingual Code Reward Models
(https://arxiv.org/abs/2605.00754v1)

This module provides:
- Multi-criteria reward models combining correctness, idiomaticity, and conciseness
- Specialized Minecraft/Bedrock idiomaticity scoring
- Integration with the existing RL reward system
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .minecraft_contracts import (
    BedrockIdiomaticityRewardModel,
    MinecraftContractResult,
)

logger = logging.getLogger(__name__)


class RewardCriterion(Enum):
    """Criteria for multi-criteria reward optimization."""

    CORRECTNESS = "correctness"
    IDIOMATICITY = "idiomaticity"
    CONCISENESS = "conciseness"
    READABILITY = "readability"
    PARTIAL_FUNCTIONAL = "partial_functional"


@dataclass
class MultiCriteriaReward:
    """Container for multi-criteria reward components."""

    total_reward: float
    correctness_reward: float
    idiomaticity_reward: float
    conciseness_reward: float
    readability_reward: float
    weighted_score: float
    criteria_scores: Dict[str, float] = field(default_factory=dict)
    penalty_reasons: List[str] = field(default_factory=list)
    bonus_reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "total_reward": self.total_reward,
            "correctness_reward": self.correctness_reward,
            "idiomaticity_reward": self.idiomaticity_reward,
            "conciseness_reward": self.conciseness_reward,
            "readability_reward": self.readability_reward,
            "weighted_score": self.weighted_score,
            "criteria_scores": self.criteria_scores,
            "penalty_reasons": self.penalty_reasons,
            "bonus_reasons": self.bonus_reasons,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
        return result


@dataclass
class MinecraftRewardWeights:
    """Weights for multi-criteria reward optimization."""

    correctness: float = 0.60
    idiomaticity: float = 0.30
    conciseness: float = 0.10
    readability: float = 0.0

    def __post_init__(self):
        total = self.correctness + self.idiomaticity + self.conciseness + self.readability
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


class ConcisenessScorer:
    """Scores code for conciseness - penalizes overly verbose output."""

    LONG_FUNCTION_THRESHOLD = 50
    REPEATED_PATTERN_PENALTY = 0.1
    UNNECESSARY_NESTING_PENALTY = 0.05

    def score(self, code: str, file_type: str = "json") -> Tuple[float, List[str]]:
        """
        Score code for conciseness.

        Returns:
            Tuple of (score 0-1, list of penalty reasons)
        """
        if file_type == "json":
            return self._score_json_conciseness(code)
        elif file_type == "js":
            return self._score_js_conciseness(code)
        return 1.0, []

    def _score_json_conciseness(self, code: str) -> Tuple[float, List[str]]:
        """Score JSON file for conciseness."""
        penalties = []
        score = 1.0

        try:
            data = json.loads(code)
            lines = code.split("\n")
            line_count = len(lines)

            if line_count > 500:
                penalties.append(f"Excessive line count: {line_count}")
                score -= 0.2

            json_str = json.dumps(data)
            if len(json_str) > 50000:
                penalties.append(f"Large JSON size: {len(json_str)} bytes")
                score -= 0.15

            repeated_keys = self._find_repeated_keys(data)
            if len(repeated_keys) > 10:
                penalties.append(f"Many repeated keys: {len(repeated_keys)}")
                score -= 0.1

        except json.JSONDecodeError:
            score = 0.7
            penalties.append("Invalid JSON - conciseness scoring limited")

        return max(0.0, score), penalties

    def _score_js_conciseness(self, code: str) -> Tuple[float, List[str]]:
        """Score JavaScript file for conciseness."""
        penalties = []
        score = 1.0

        lines = code.split("\n")
        line_count = len(lines)

        if line_count > 1000:
            penalties.append(f"Excessive line count: {line_count}")
            score -= 0.2

        empty_lines = sum(1 for line in lines if not line.strip())
        empty_ratio = empty_lines / max(1, len(lines))
        if empty_ratio > 0.3:
            penalties.append(f"Excessive empty lines: {empty_ratio:.0%}")
            score -= 0.1

        long_lines = sum(1 for line in lines if len(line) > 120)
        if long_lines > 20:
            penalties.append(f"Many long lines: {long_lines}")
            score -= 0.1

        return max(0.0, score), penalties

    def _find_repeated_keys(self, obj: Any, path: str = "") -> List[str]:
        """Find repeated keys in nested structure."""
        repeated = []
        key_counts: Dict[str, int] = {}

        def traverse(item: Any, current_path: str):
            if isinstance(item, dict):
                for key, value in item.items():
                    full_key = f"{current_path}.{key}" if current_path else key
                    key_counts[full_key] = key_counts.get(full_key, 0) + 1
                    traverse(value, full_key)
            elif isinstance(item, list):
                for i, elem in enumerate(item):
                    traverse(elem, f"{current_path}[{i}]")

        traverse(obj, path)

        for key, count in key_counts.items():
            if count > 5:
                repeated.append(f"{key} ({count} times)")

        return repeated


class ReadabilityScorer:
    """Scores code for readability - evaluates structure and formatting."""

    VALID_INDENT_SIZE = 4

    def score(self, code: str, file_type: str = "json") -> Tuple[float, List[str]]:
        """
        Score code for readability.

        Returns:
            Tuple of (score 0-1, list of readability issues)
        """
        if file_type == "json":
            return self._score_json_readability(code)
        elif file_type == "js":
            return self._score_js_readability(code)
        return 1.0, []

    def _score_json_readability(self, code: str) -> Tuple[float, List[str]]:
        """Score JSON file for readability."""
        issues = []
        score = 1.0

        lines = code.split("\n")

        inconsistent_indent = self._check_indentation_consistency(lines)
        if inconsistent_indent:
            issues.append("Inconsistent indentation")
            score -= 0.1

        try:
            data = json.loads(code)
            flat_str = json.dumps(data, separators=(",", ":"))
            compact_size = len(flat_str)
            formatted_size = len(code)

            if formatted_size > compact_size * 1.5:
                issues.append("Overly formatted (excessive whitespace)")
                score -= 0.1

        except json.JSONDecodeError:
            issues.append("Invalid JSON")
            score -= 0.2

        return max(0.0, score), issues

    def _score_js_readability(self, code: str) -> Tuple[float, List[str]]:
        """Score JavaScript file for readability."""
        issues = []
        score = 1.0

        lines = code.split("\n")

        inconsistent_indent = self._check_indentation_consistency(lines)
        if inconsistent_indent:
            issues.append("Inconsistent indentation")
            score -= 0.15

        max_line_length = max(len(line) for line in lines)
        if max_line_length > 150:
            issues.append(f"Very long lines (max: {max_line_length})")
            score -= 0.1

        comment_lines = sum(1 for line in lines if "//" in line or "/*" in line)
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith("//"))
        if comment_lines > 0 and code_lines > 0:
            comment_ratio = comment_lines / (comment_lines + code_lines)
            if comment_ratio > 0.4:
                issues.append(f"Excessive comments: {comment_ratio:.0%}")
                score -= 0.1

        return max(0.0, score), issues

    def _check_indentation_consistency(self, lines: List[str]) -> bool:
        """Check if indentation is consistent."""
        indent_sizes = set()
        for line in lines:
            if line.startswith(" "):
                leading_spaces = len(line) - len(line.lstrip())
                if leading_spaces % 4 == 0:
                    indent_sizes.add(4)
                elif leading_spaces % 2 == 0:
                    indent_sizes.add(2)

        return len(indent_sizes) > 1


class MinecraftSpecificIdiomDetector:
    """Detects Minecraft-specific idioms and patterns in Bedrock code."""

    HAND_WRITTEN_PATTERNS = [
        r'"minecraft:item"\s*:\s*\{[^}]*"id"\s*:\s*"[^"]+:[^"]+"',
        r'"format_version"\s*:\s*"\d+\.\d+\.\d+"',
        r'"uuid"\s*:\s*"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"',
    ]

    TRANSLATOR_OUTPUT_PATTERNS = [
        r'"parent"\s*:\s*".*:.*:.*"',
        r'"description"\s*:\s*\{\s*"identifier"\s*:\s*"[^"]+"\s*\}',
        r'"scripts"\s*:\s*\{\s*"client"\s*:\s*\[\s*\]',
    ]

    def detect_idiom_quality(self, code: str, file_type: str = "json") -> Tuple[float, List[str]]:
        """
        Detect whether code looks hand-written or machine-translated.

        Returns:
            Tuple of (quality score 0-1, list of detected patterns)
        """
        detected = []
        score = 0.5

        for pattern in self.HAND_WRITTEN_PATTERNS:
            if re.search(pattern, code):
                detected.append(f"hand_written:{pattern[:50]}")
                score += 0.1

        for pattern in self.TRANSLATOR_OUTPUT_PATTERNS:
            if re.search(pattern, code):
                detected.append(f"translator:{pattern[:50]}")
                score -= 0.15

        code_lower = code.lower()
        if "test" in code_lower or "example" in code_lower or "sample" in code_lower:
            score -= 0.05

        minecraft_specific = self._detect_minecraft_specific_constructs(code)
        if minecraft_specific:
            detected.extend(minecraft_specific)
            score += 0.1 * min(1.0, len(minecraft_specific) / 3)

        return max(0.0, min(1.0, score)), detected

    def _detect_minecraft_specific_constructs(self, code: str) -> List[str]:
        """Detect Minecraft-specific Bedrock constructs."""
        constructs = []

        if '"minecraft:' in code or "'minecraft:" in code:
            constructs.append("uses_minecraft_namespaces")

        if re.search(r'"creative_category"\s*:', code):
            constructs.append("has_creative_category")

        if re.search(r'"menu_category"\s*:', code):
            constructs.append("has_menu_category")

        if re.search(r'"series"\s*:', code):
            constructs.append("has_series")

        if re.search(r'"geometry"\s*:', code):
            constructs.append("has_geometry")

        if re.search(r'"material"\s*:', code):
            constructs.append("has_material")

        return constructs
    

class PartialFunctionalRewardModel:
    """
    Evaluates how close code is to being functional.
    
    Awards rewards for:
    - Correct Bedrock API namespace usage
    - Presence of required components for the mod type
    - Correct data structures even if some values are wrong
    """

    REQUIRED_COMPONENTS = {
        "item": ["minecraft:item", "description", "components"],
        "block": ["minecraft:block", "description", "components"],
        "entity": ["minecraft:entity", "description", "components", "events"],
        "recipe": ["minecraft:recipe", "description", "result"],
    }

    def score(self, code: str, feature_type: str = "item") -> float:
        """Score how functionally complete the code is."""
        score = 0.0
        
        # Check for core identifiers
        if '"minecraft:' in code:
            score += 0.2
            
        # Check for required components for this type
        required = self.REQUIRED_COMPONENTS.get(feature_type, ["description"])
        found_count = 0
        for comp in required:
            if f'"{comp}"' in code:
                found_count += 1
        
        if required:
            score += 0.5 * (found_count / len(required))
            
        # Check for schema version
        if '"format_version"' in code:
            score += 0.1
            
        # Check for syntax validity
        try:
            json.loads(code)
            score += 0.2
        except:
            pass
            
        return min(1.0, score)


class MultiCriteriaRewardModel:
    """
    Multi-criteria reward model for Minecraft/Bedrock code.

    Combines:
    - Correctness (60%): Does the code execute correctly?
    - Idiomaticity (30%): Does it look hand-written vs translator output?
    - Conciseness (10%): Is the code appropriately concise?

    Based on the Themis paper's approach to code reward models.
    """

    def __init__(
        self,
        weights: Optional[MinecraftRewardWeights] = None,
        enable_repair: bool = True,
    ):
        self.weights = weights or MinecraftRewardWeights()
        self.idiomaticity_rm = BedrockIdiomaticityRewardModel()
        self.conciseness_scorer = ConcisenessScorer()
        self.readability_scorer = ReadabilityScorer()
        self.idiom_detector = MinecraftSpecificIdiomDetector()
        self.partial_functional_rm = PartialFunctionalRewardModel()
        self.enable_repair = enable_repair

        self.reward_config = {
            "excellent_score": 2.0,
            "good_score": 1.5,
            "acceptable_score": 1.0,
            "poor_score": 0.5,
            "correctness_bonus": 1.0,
            "idiom_bonus": 0.5,
            "concise_bonus": 0.25,
            "readability_bonus": 0.15,
        }

    def score(
        self,
        code: str,
        file_type: str = "json",
        location: Optional[str] = None,
        original_code: Optional[str] = None,
        conversion_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[MultiCriteriaReward, MinecraftContractResult]:
        """
        Score code using multi-criteria reward model.

        Args:
            code: Bedrock code to score
            file_type: Type of file (json, js, etc.)
            location: Optional location identifier
            original_code: Original code for correctness comparison
            conversion_context: Additional context about the conversion

        Returns:
            Tuple of (MultiCriteriaReward, MinecraftContractResult)
        """
        context = conversion_context or {}

        correctness_score, idiomaticity_result = self._score_correctness_and_idiomaticity(
            code, file_type, location, original_code, context
        )

        conciseness_score, conciseness_issues = self.conciseness_scorer.score(code, file_type)

        readability_score, readability_issues = self.readability_scorer.score(code, file_type)

        idiom_quality, idiom_patterns = self.idiom_detector.detect_idiom_quality(code, file_type)

        criteria_scores = {
            "correctness": correctness_score,
            "idiomaticity": idiomaticity_result.idiomaticity_score.overall_score,
            "conciseness": conciseness_score,
            "readability": readability_score,
            "idiom_quality": idiom_quality,
            "partial_functional": self.partial_functional_rm.score(code, context.get("feature_type", "item")),
        }

        total_reward = self._compute_total_reward(criteria_scores)

        reward = MultiCriteriaReward(
            total_reward=total_reward,
            correctness_reward=criteria_scores["correctness"] * self.weights.correctness,
            idiomaticity_reward=criteria_scores["idiomaticity"] * self.weights.idiomaticity,
            conciseness_reward=conciseness_score * self.weights.conciseness,
            readability_reward=readability_score * self.weights.readability,
            weighted_score=total_reward,
            criteria_scores={k: round(v, 3) for k, v in criteria_scores.items()},
            penalty_reasons=idiomaticity_result.violations
            + conciseness_issues
            + readability_issues,
            bonus_reasons=self._generate_bonus_reasons(criteria_scores, idiom_patterns),
            metadata={
                "idiomaticity_details": idiomaticity_result.idiomaticity_score.to_dict(),
                "idiom_patterns": idiom_patterns,
                "weights": {
                    "correctness": self.weights.correctness,
                    "idiomaticity": self.weights.idiomaticity,
                    "conciseness": self.weights.conciseness,
                },
                "repair_triggered": idiomaticity_result.repair_loop_triggered,
            },
        )

        return reward, idiomaticity_result

    def _score_correctness_and_idiomaticity(
        self,
        code: str,
        file_type: str,
        location: Optional[str],
        original_code: Optional[str],
        context: Dict[str, Any],
    ) -> Tuple[float, MinecraftContractResult]:
        """Score correctness and idiomaticity together."""
        result, idiomaticity_reward = self.idiomaticity_rm.score(
            code, file_type, location, enable_repair=self.enable_repair
        )

        base_correctness = result.idiomaticity_score.overall_score

        if original_code:
            structure_matches = self._check_structure_match(code, original_code)
            base_correctness = (base_correctness + structure_matches) / 2

        return base_correctness, result

    def _check_structure_match(self, code: str, original: str) -> float:
        """Check how well the converted code maintains structure."""
        try:
            code_data = json.loads(code) if isinstance(code, str) and code.startswith("{") else {}
            orig_data = (
                json.loads(original)
                if isinstance(original, str) and original.startswith("{")
                else {}
            )

            if not code_data or not orig_data:
                return 0.5

            code_keys = set(code_data.keys()) if isinstance(code_data, dict) else set()
            orig_keys = set(orig_data.keys()) if isinstance(orig_data, dict) else set()

            if not orig_keys:
                return 0.5

            overlap = len(code_keys & orig_keys) / len(orig_keys)
            return overlap

        except (json.JSONDecodeError, TypeError):
            return 0.5

    def _compute_total_reward(self, criteria_scores: Dict[str, float]) -> float:
        """Compute total reward from criteria scores."""
        reward = 0.0

        weighted = (
            criteria_scores["correctness"] * self.weights.correctness
            + criteria_scores["idiomaticity"] * self.weights.idiomaticity
            + criteria_scores["conciseness"] * self.weights.conciseness
            + criteria_scores["readability"] * self.weights.readability
            + criteria_scores.get("partial_functional", 0.0) * 0.1  # Add small weight for partial functional
        )

        if weighted >= 0.9:
            reward += self.reward_config["excellent_score"]
        elif weighted >= 0.75:
            reward += self.reward_config["good_score"]
        elif weighted >= 0.6:
            reward += self.reward_config["acceptable_score"]
        else:
            reward += self.reward_config["poor_score"]

        if criteria_scores["idiomaticity"] >= 0.8:
            reward += self.reward_config["idiom_bonus"]

        if criteria_scores["conciseness"] >= 0.8:
            reward += self.reward_config["concise_bonus"]

        if criteria_scores.get("idiom_quality", 0.5) >= 0.7:
            reward += self.reward_config["readability_bonus"]

        return max(-1.0, min(3.0, reward))

    def _generate_bonus_reasons(
        self, criteria_scores: Dict[str, float], idiom_patterns: List[str]
    ) -> List[str]:
        """Generate reasons for bonuses awarded."""
        reasons = []

        if criteria_scores["correctness"] >= 0.9:
            reasons.append("Excellent correctness score")

        if criteria_scores["idiomaticity"] >= 0.85:
            reasons.append("High idiomaticity - code looks hand-written")

        if criteria_scores["conciseness"] >= 0.85:
            reasons.append("Concise code structure")

        if criteria_scores.get("idiom_quality", 0) >= 0.7:
            reasons.append("Good Minecraft-specific idiom usage")

        for pattern in idiom_patterns:
            if pattern.startswith("hand_written:"):
                reasons.append(f"Detected hand-written pattern")
                break

        return reasons

    def batch_score(
        self,
        samples: List[Dict[str, Any]],
    ) -> List[Tuple[MultiCriteriaReward, MinecraftContractResult]]:
        """Score multiple code samples."""
        results = []

        for sample in samples:
            code = sample.get("code", "")
            file_type = sample.get("file_type", "json")
            location = sample.get("location")
            original_code = sample.get("original_code")
            context = sample.get("context", {})

            result, contract_result = self.score(
                code=code,
                file_type=file_type,
                location=location,
                original_code=original_code,
                conversion_context=context,
            )
            results.append((result, contract_result))

        return results


class MinecraftRewardModelFactory:
    """Factory for creating Minecraft-specific reward models."""

    PRESETS = {
        "balanced": MinecraftRewardWeights(correctness=0.60, idiomaticity=0.30, conciseness=0.10),
        "correctness_focused": MinecraftRewardWeights(
            correctness=0.70, idiomaticity=0.20, conciseness=0.10
        ),
        "idiomaticity_focused": MinecraftRewardWeights(
            correctness=0.40, idiomaticity=0.50, conciseness=0.10
        ),
        "readability_focused": MinecraftRewardWeights(
            correctness=0.50, idiomaticity=0.25, conciseness=0.10, readability=0.15
        ),
    }

    @classmethod
    def create(
        cls,
        preset: Optional[str] = None,
        custom_weights: Optional[MinecraftRewardWeights] = None,
        enable_repair: bool = True,
    ) -> MultiCriteriaRewardModel:
        """Create a Minecraft reward model with specified configuration."""
        if preset and preset in cls.PRESETS:
            weights = cls.PRESETS[preset]
        elif custom_weights:
            weights = custom_weights
        else:
            weights = cls.PRESETS["balanced"]

        return MultiCriteriaRewardModel(weights=weights, enable_repair=enable_repair)

    @classmethod
    def create_with_custom_weights(
        cls,
        correctness: float = 0.60,
        idiomaticity: float = 0.30,
        conciseness: float = 0.10,
        readability: float = 0.0,
    ) -> MultiCriteriaRewardModel:
        """Create reward model with specific weight values."""
        weights = MinecraftRewardWeights(
            correctness=correctness,
            idiomaticity=idiomaticity,
            conciseness=conciseness,
            readability=readability,
        )
        return MultiCriteriaRewardModel(weights=weights)


def create_multi_criteria_reward_model(
    preset: Optional[str] = None,
    enable_repair: bool = True,
) -> MultiCriteriaRewardModel:
    """Factory function to create a multi-criteria reward model."""
    return MinecraftRewardModelFactory.create(preset=preset, enable_repair=enable_repair)


def create_idiomaticity_reward_model() -> BedrockIdiomaticityRewardModel:
    """Factory function to create a Bedrock idiomaticity reward model."""
    return BedrockIdiomaticityRewardModel()
