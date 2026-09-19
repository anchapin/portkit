"""
Evaluation Module for SAE-based Feature Steering.

This module provides metrics for measuring the effectiveness of Java idiom
suppression in Bedrock code generation. Based on the evaluation framework
from the Tilde Research Sieve paper.

Usage:
    from steering.evaluation import SteeringEvaluator, IdiomMetric

    evaluator = SteeringEvaluator()
    results = evaluator.evaluate_generation(
        original_java=java_code,
        generated_bedrock=bedrock_code,
        steering_applied=True,
    )
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .java_idiom_detector import JavaIdiomHeuristics

logger = logging.getLogger(__name__)


class IdiomCategory(Enum):
    """Categories of Java idioms to detect and measure."""

    FORGE_PATTERN = "forge_pattern"
    CLASS_PATTERN = "class_pattern"
    API_PATTERN = "api_pattern"
    COLLECTION_PATTERN = "collection_pattern"
    NULL_SAFETY_PATTERN = "null_safety_pattern"
    TYPE_CAST_PATTERN = "type_cast_pattern"
    METHOD_CHAIN_PATTERN = "method_chain_pattern"


@dataclass
class IdiomPattern:
    """A specific Java idiom pattern to detect."""

    name: str
    category: IdiomCategory
    pattern: str
    replacement: str
    description: str


# Standard Java idiom patterns for evaluation
JAVA_IDIOM_PATTERNS = [
    # Forge patterns (1000-1999)
    IdiomPattern(
        name="forge_import",
        category=IdiomCategory.FORGE_PATTERN,
        pattern=r"net\.minecraft\.forge",
        replacement="",
        description="Forge namespace imports",
    ),
    IdiomPattern(
        name="forge_event",
        category=IdiomCategory.FORGE_PATTERN,
        pattern=r"@SubscribeEvent",
        replacement="",
        description="Forge event subscriber annotations",
    ),
    IdiomPattern(
        name="forge_bus",
        category=IdiomCategory.FORGE_PATTERN,
        pattern=r"MinecraftForge\.EVENT_BUS",
        replacement="",
        description="Forge event bus references",
    ),
    # Class patterns (2000-2999)
    IdiomPattern(
        name="java_class_keyword",
        category=IdiomCategory.CLASS_PATTERN,
        pattern=r"\bclass\s+\w+",
        replacement="",
        description="Java class declarations",
    ),
    IdiomPattern(
        name="java_extends",
        category=IdiomCategory.CLASS_PATTERN,
        pattern=r"\bextends\s+\w+",
        replacement="",
        description="Java extends inheritance",
    ),
    IdiomPattern(
        name="java_implements",
        category=IdiomCategory.CLASS_PATTERN,
        pattern=r"\bimplements\s+\w+",
        replacement="",
        description="Java implements inheritance",
    ),
    # API patterns (3000-3999)
    IdiomPattern(
        name="getter_setter",
        category=IdiomCategory.API_PATTERN,
        pattern=r"\.get[A-Z]\w+\(\)|\.set[A-Z]\w+\(",
        replacement="",
        description="Java getter/setter method calls",
    ),
    IdiomPattern(
        name="java_system_out",
        category=IdiomCategory.API_PATTERN,
        pattern=r"System\.out\.print",
        replacement="",
        description="Java System.out print statements",
    ),
    IdiomPattern(
        name="java_throw",
        category=IdiomCategory.API_PATTERN,
        pattern=r"\bthrow\s+new\s+\w+Exception",
        replacement="",
        description="Java throw statements",
    ),
]


@dataclass
class IdiomMetrics:
    """Metrics for a single idiom category."""

    category: IdiomCategory
    detected_count: int = 0
    suppression_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "detected_count": self.detected_count,
            "suppression_rate": self.suppression_rate,
        }


@dataclass
class EvaluationResult:
    """Complete evaluation result for a generation."""

    # Overall score (0-100, higher is better)
    overall_score: float

    # Per-category metrics
    category_metrics: List[IdiomMetrics]

    # Detection counts
    total_idioms_detected: int
    idioms_suppressed: int
    idioms_persisted: int

    # Raw counts
    java_idiom_count: int
    bedrock_idiom_count: int

    # Steering metadata
    steering_applied: bool
    feature_ids: List[int] = field(default_factory=list)

    # Warnings
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "category_metrics": [m.to_dict() for m in self.category_metrics],
            "total_idioms_detected": self.total_idioms_detected,
            "idioms_suppressed": self.idioms_suppressed,
            "idioms_persisted": self.idioms_persisted,
            "java_idiom_count": self.java_idiom_count,
            "bedrock_idiom_count": self.bedrock_idiom_count,
            "steering_applied": self.steering_applied,
            "feature_ids": self.feature_ids,
            "warnings": self.warnings,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class SteeringEvaluator:
    """
    Evaluates the effectiveness of SAE-based feature steering.

    Measures:
    1. Idiom suppression rate (what % of Java idioms were suppressed)
    2. Idiom detection accuracy (did we detect the right idioms)
    3. Conversion quality (is the Bedrock code idiomatic)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._idiom_detector = JavaIdiomHeuristics()
        self._patterns = JAVA_IDIOM_PATTERNS

        # Thresholds
        self.suppression_threshold = self.config.get("suppression_threshold", 0.8)
        self.min_quality_score = self.config.get("min_quality_score", 60.0)

    def evaluate_generation(
        self,
        original_java: str,
        generated_bedrock: str,
        steering_applied: bool = False,
        steering_features: Optional[List[int]] = None,
    ) -> EvaluationResult:
        """
        Evaluate a Java-to-Bedrock generation.

        Args:
            original_java: The original Java code
            generated_bedrock: The generated Bedrock code
            steering_applied: Whether steering was applied
            steering_features: Feature IDs used for steering

        Returns:
            EvaluationResult with metrics
        """
        # Detect Java idioms in original
        java_idioms = self._detect_idioms(original_java)
        java_idiom_count = len(java_idioms)

        # Detect Java idioms in generated (should be suppressed)
        bedrock_idioms = self._detect_idioms(generated_bedrock)
        bedrock_idiom_count = len(bedrock_idioms)

        # Calculate suppression metrics
        suppression_results = self._calculate_suppression(java_idioms, bedrock_idioms)

        # Calculate per-category metrics
        category_metrics = self._calculate_category_metrics(java_idioms, bedrock_idioms)

        # Calculate overall score
        overall_score = self._calculate_overall_score(
            category_metrics,
            java_idiom_count,
            bedrock_idiom_count,
            steering_applied,
        )

        # Generate warnings
        warnings = self._generate_warnings(
            overall_score,
            bedrock_idioms,
            category_metrics,
        )

        return EvaluationResult(
            overall_score=overall_score,
            category_metrics=category_metrics,
            total_idioms_detected=java_idiom_count,
            idioms_suppressed=suppression_results["suppressed"],
            idioms_persisted=suppression_results["persisted"],
            java_idiom_count=java_idiom_count,
            bedrock_idiom_count=bedrock_idiom_count,
            steering_applied=steering_applied,
            feature_ids=steering_features or [],
            warnings=warnings,
        )

    def _detect_idioms(self, code: str) -> List[Tuple[str, int, str]]:
        """
        Detect Java idioms in code.

        Returns:
            List of (idiom_name, feature_id, matched_text) tuples
        """
        detected = []

        for pattern in self._patterns:
            matches = re.findall(pattern.pattern, code)
            for match in matches:
                detected.append((pattern.name, self._get_feature_id(pattern), match))

        return detected

    def _get_feature_id(self, pattern: IdiomPattern) -> int:
        """Map idiom pattern to SAE feature ID range."""
        category = pattern.category
        if category == IdiomCategory.FORGE_PATTERN:
            base = 1000
        elif category == IdiomCategory.CLASS_PATTERN:
            base = 2000
        elif category == IdiomCategory.API_PATTERN:
            base = 3000
        elif category == IdiomCategory.COLLECTION_PATTERN:
            base = 4000
        elif category == IdiomCategory.NULL_SAFETY_PATTERN:
            base = 4100
        elif category == IdiomCategory.TYPE_CAST_PATTERN:
            base = 4200
        elif category == IdiomCategory.METHOD_CHAIN_PATTERN:
            base = 4300
        else:
            base = 5000

        # Generate stable ID from pattern name
        name_hash = sum(ord(c) for c in pattern.name)
        return base + (name_hash % 100)

    def _calculate_suppression(
        self,
        java_idioms: List[Tuple[str, int, str]],
        bedrock_idioms: List[Tuple[str, int, str]],
    ) -> Dict[str, int]:
        """Calculate suppression metrics."""
        if not java_idioms:
            return {"suppressed": 0, "persisted": 0, "total": 0}

        # Build set of idiom names in java
        java_names = set(name for name, _, _ in java_idioms)
        bedrock_names = set(name for name, _, _ in bedrock_idioms)

        # Suppressed = present in Java but not in Bedrock
        suppressed = len(java_names - bedrock_names)

        # Persisted = present in both (not suppressed)
        persisted = len(java_names & bedrock_names)

        return {
            "suppressed": suppressed,
            "persisted": persisted,
            "total": len(java_names),
        }

    def _calculate_category_metrics(
        self,
        java_idioms: List[Tuple[str, int, str]],
        bedrock_idioms: List[Tuple[str, int, str]],
    ) -> List[IdiomMetrics]:
        """Calculate per-category suppression metrics."""
        # Group by category
        java_by_cat: Dict[IdiomCategory, List] = {}
        bedrock_by_cat: Dict[IdiomCategory, List] = {}

        for name, feat_id, match in java_idioms:
            cat = self._get_category_for_name(name)
            if cat not in java_by_cat:
                java_by_cat[cat] = []
            java_by_cat[cat].append(name)

        for name, feat_id, match in bedrock_idioms:
            cat = self._get_category_for_name(name)
            if cat not in bedrock_by_cat:
                bedrock_by_cat[cat] = []
            bedrock_by_cat[cat].append(name)

        # Calculate metrics per category
        metrics = []
        for cat in IdiomCategory:
            java_count = len(set(java_by_cat.get(cat, [])))
            bedrock_count = len(set(bedrock_by_cat.get(cat, [])))

            suppression_rate = 0.0
            if java_count > 0:
                suppression_rate = (java_count - bedrock_count) / java_count

            metrics.append(
                IdiomMetrics(
                    category=cat,
                    detected_count=java_count,
                    suppression_rate=suppression_rate,
                )
            )

        return metrics

    def _get_category_for_name(self, name: str) -> IdiomCategory:
        """Get the category for an idiom name."""
        for pattern in self._patterns:
            if pattern.name == name:
                return pattern.category
        return IdiomCategory.API_PATTERN

    def _calculate_overall_score(
        self,
        category_metrics: List[IdiomMetrics],
        java_count: int,
        bedrock_count: int,
        steering_applied: bool,
    ) -> float:
        """Calculate overall quality score (0-100)."""
        if java_count == 0:
            return 100.0  # No idioms to suppress

        # Base score from suppression rate
        suppression_rate = 1.0 - (bedrock_count / java_count) if java_count > 0 else 1.0
        base_score = suppression_rate * 60.0

        # Category bonus (up to 30 points)
        category_bonus = 0.0
        for metric in category_metrics:
            if metric.detected_count > 0:
                category_bonus += metric.suppression_rate * 5.0
        category_bonus = min(category_bonus, 30.0)

        # Steering bonus (up to 10 points)
        steering_bonus = 10.0 if steering_applied else 0.0

        return min(base_score + category_bonus + steering_bonus, 100.0)

    def _generate_warnings(
        self,
        overall_score: float,
        bedrock_idioms: List[Tuple[str, int, str]],
        category_metrics: List[IdiomMetrics],
    ) -> List[str]:
        """Generate warnings based on evaluation."""
        warnings = []

        # Low overall score
        if overall_score < self.min_quality_score:
            warnings.append(
                f"Overall score {overall_score:.1f} below threshold {self.min_quality_score}"
            )

        # Check for persisted idioms
        if bedrock_idioms:
            names = list(set(name for name, _, _ in bedrock_idioms))
            warnings.append(f"Persisted idioms: {', '.join(names[:5])}")

        # Check categories with low suppression
        for metric in category_metrics:
            if metric.detected_count > 2 and metric.suppression_rate < 0.5:
                warnings.append(
                    f"Low suppression in {metric.category.value}: "
                    f"{metric.suppression_rate * 100:.0f}%"
                )

        return warnings

    def evaluate_batch(
        self,
        evaluations: List[Tuple[str, str, bool]],
    ) -> Dict[str, Any]:
        """
        Evaluate multiple generations and compute aggregate metrics.

        Args:
            evaluations: List of (java_code, bedrock_code, steering_applied) tuples

        Returns:
            Aggregate metrics dictionary
        """
        results = []
        for java, bedrock, steering in evaluations:
            result = self.evaluate_generation(java, bedrock, steering)
            results.append(result)

        # Aggregate
        total_suppressed = sum(r.idioms_suppressed for r in results)
        total_persisted = sum(r.idioms_persisted for r in results)
        avg_score = sum(r.overall_score for r in results) / len(results) if results else 0

        # Per-category aggregates
        category_agg = {}
        for cat in IdiomCategory:
            cat_results = [m for r in results for m in r.category_metrics if m.category == cat]
            if cat_results:
                avg_rate = sum(m.suppression_rate for m in cat_results) / len(cat_results)
                category_agg[cat.value] = {
                    "avg_suppression_rate": avg_rate,
                    "total_detected": sum(m.detected_count for m in cat_results),
                }

        return {
            "total_evaluations": len(results),
            "total_suppressed": total_suppressed,
            "total_persisted": total_persisted,
            "average_score": avg_score,
            "category_aggregates": category_agg,
        }


# Convenience function
def evaluate_steering_effectiveness(
    java_code: str,
    bedrock_code: str,
    steering_applied: bool = False,
) -> EvaluationResult:
    """
    Quick evaluation of steering effectiveness.

    Usage:
        result = evaluate_steering_effectiveness(java_code, bedrock_code, steering_applied=True)
        print(f"Score: {result.overall_score}")
    """
    evaluator = SteeringEvaluator()
    return evaluator.evaluate_generation(
        original_java=java_code,
        generated_bedrock=bedrock_code,
        steering_applied=steering_applied,
    )
