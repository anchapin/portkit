"""
Token Budget Estimator for B2B Cost Transparency

Provides pre-conversion token and cost estimation based on mod metadata,
enabling budget prediction before conversion runs.

Based on: "How Do AI Agents Spend Your Money? Analyzing and Predicting
Token Consumption in Agentic Coding Tasks" (Bai et al., 2026-04-24)

Key findings applied:
1. Context tokens dominate (long-horizon history)
2. Model efficiency varies 3-5x between models
3. Pre-task prediction is feasible

Issue: #1188 - Implement per-conversion token budget prediction and cost monitoring
"""

import logging
import os
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_metrics.llm_usage_tracker import estimate_cost

logger = logging.getLogger(__name__)


class ConversionPhase(str, Enum):
    """Phases of the conversion pipeline"""

    ANALYSIS = "analysis"
    MAPPING = "mapping"
    TRANSLATION = "translation"
    QA = "qa"


@dataclass
class ModMetadata:
    """Metadata extracted from a Java mod for estimation"""

    file_count: int = 0
    total_loc: int = 0
    class_count: int = 0
    max_class_depth: int = 0
    dependency_count: int = 0
    has_gui: bool = False
    has_entities: bool = False
    has_tile_entities: bool = False
    estimated_features: int = 0


@dataclass
class PhaseEstimate:
    """Token estimate for a single phase"""

    phase: ConversionPhase
    input_tokens: int = 0
    output_tokens: int = 0
    confidence_low: float = 0.8
    confidence_high: float = 1.2

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class EstimatedTokenUsage:
    """Complete token usage estimate for a conversion"""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    by_phase: Dict[ConversionPhase, PhaseEstimate] = field(default_factory=dict)
    confidence_interval_low: float = 0.85
    confidence_interval_high: float = 1.15
    estimated_cost_usd: float = 0.0
    model_used: str = "gpt-4o"
    estimated_duration_seconds: float = 0.0
    complexity_tier: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "by_phase": {
                phase.value: {
                    "input_tokens": est.input_tokens,
                    "output_tokens": est.output_tokens,
                    "confidence_low": est.confidence_low,
                    "confidence_high": est.confidence_high,
                }
                for phase, est in self.by_phase.items()
            },
            "confidence_interval": (self.confidence_interval_low, self.confidence_interval_high),
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "model_used": self.model_used,
            "estimated_duration_seconds": round(self.estimated_duration_seconds, 1),
            "complexity_tier": self.complexity_tier,
        }


@dataclass
class ConversionCostReport:
    """Post-conversion cost report for B2B transparency"""

    conversion_id: str
    estimated: EstimatedTokenUsage
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    actual_cost_usd: float = 0.0
    by_phase: Dict[str, Dict[str, int]] = field(default_factory=dict)
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    budget_exceeded: bool = False
    budget_limit_usd: Optional[float] = None
    over_budget_by: float = 0.0

    @property
    def actual_total_tokens(self) -> int:
        return self.actual_input_tokens + self.actual_output_tokens

    @property
    def cost_vs_estimate_ratio(self) -> float:
        if self.estimated.estimated_cost_usd == 0:
            return 0.0
        return self.actual_cost_usd / self.estimated.estimated_cost_usd

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversion_id": self.conversion_id,
            "estimated": self.estimated.to_dict(),
            "actual": {
                "input_tokens": self.actual_input_tokens,
                "output_tokens": self.actual_output_tokens,
                "total_tokens": self.actual_total_tokens,
                "cost_usd": round(self.actual_cost_usd, 4),
            },
            "by_phase": self.by_phase,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 1),
            "budget_exceeded": self.budget_exceeded,
            "budget_limit_usd": self.budget_limit_usd,
            "over_budget_by": round(self.over_budget_by, 4),
            "cost_vs_estimate_ratio": round(self.cost_vs_estimate_ratio, 2),
        }


class TokenBudgetEstimator:
    """
    Estimates LLM token consumption before and during conversion runs.

    Features:
    - Pre-conversion estimation from mod metadata
    - Per-phase token tracking during conversion
    - Budget cap enforcement (configurable)
    - Cost comparison reports for B2B transparency

    Based on regression model using:
    - File count
    - Total LOC (lines of code)
    - Max class depth
    - Number of dependencies
    """

    PHASE_WEIGHTS = {
        ConversionPhase.ANALYSIS: 0.25,
        ConversionPhase.MAPPING: 0.20,
        ConversionPhase.TRANSLATION: 0.40,
        ConversionPhase.QA: 0.15,
    }

    BASE_TOKENS_PER_LOC = 8.5
    CONTEXT_OVERHEAD_FACTOR = 2.3

    DEFAULT_MODEL = "gpt-4o"

    COMPLEXITY_TIERS = {
        "simple": {"max_loc": 500, "max_classes": 20, "max_depth": 3},
        "moderate": {"max_loc": 2000, "max_classes": 100, "max_depth": 5},
        "complex": {"max_loc": 5000, "max_classes": 250, "max_depth": 7},
        "very_complex": {
            "max_loc": float("inf"),
            "max_classes": float("inf"),
            "max_depth": float("inf"),
        },
    }

    def __init__(
        self,
        default_model: str = None,
        cost_alert_threshold: float = 5.0,
    ):
        self.default_model = default_model or self.DEFAULT_MODEL
        self.cost_alert_threshold = cost_alert_threshold
        self._historical_data: List[Dict[str, Any]] = []
        self._phase_trackers: Dict[str, Dict[ConversionPhase, int]] = {}

    def extract_metadata(self, mod_path: str) -> ModMetadata:
        """
        Extract metadata from a mod file for estimation.

        Args:
            mod_path: Path to the mod file (.jar/.zip)

        Returns:
            ModMetadata with extracted features
        """
        metadata = ModMetadata()

        try:
            path = Path(mod_path)
            if not path.exists():
                logger.warning(f"Mod file not found: {mod_path}")
                return metadata

            if path.suffix.lower() == ".jar" or path.name.endswith(".jar"):
                metadata = self._extract_from_jar(path)
            else:
                metadata = self._extract_from_directory(path)

            logger.info(
                f"Extracted metadata: files={metadata.file_count}, "
                f"loc={metadata.total_loc}, classes={metadata.class_count}"
            )

        except Exception as e:
            logger.error(f"Error extracting metadata from {mod_path}: {e}")

        return metadata

    def _extract_from_jar(self, jar_path: Path) -> ModMetadata:
        """Extract metadata from a JAR file"""
        metadata = ModMetadata()
        java_files = []
        total_loc = 0

        try:
            with zipfile.ZipFile(jar_path, "r") as zf:
                file_list = zf.namelist()
                metadata.file_count = len(file_list)

                for name in file_list:
                    if name.endswith(".java"):
                        java_files.append(name)
                        try:
                            content = zf.read(name).decode("utf-8", errors="ignore")
                            lines = content.count("\n") + 1
                            total_loc += lines
                        except Exception:
                            pass

        except Exception as e:
            logger.warning(f"Could not read JAR file: {e}")

        metadata.total_loc = total_loc
        metadata.class_count = self._count_java_classes(java_files)
        metadata.dependency_count = self._estimate_dependencies(jar_path)
        metadata.estimated_features = self._estimate_feature_count(metadata)
        metadata.max_class_depth = min(10, max(2, metadata.class_count // 10))

        return metadata

    def _extract_from_directory(self, dir_path: Path) -> ModMetadata:
        """Extract metadata from an unpacked mod directory"""
        metadata = ModMetadata()
        java_files = []
        total_loc = 0

        try:
            for root, _, files in os.walk(dir_path):
                for file in files:
                    full_path = Path(root) / file
                    metadata.file_count += 1

                    if file.endswith(".java"):
                        java_files.append(str(full_path))
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                                total_loc += sum(1 for _ in f)
                        except Exception:
                            pass

        except Exception as e:
            logger.warning(f"Could not read directory: {e}")

        metadata.total_loc = total_loc
        metadata.class_count = self._count_java_classes(java_files)
        metadata.estimated_features = self._estimate_feature_count(metadata)
        metadata.max_class_depth = min(10, max(2, metadata.class_count // 10))

        return metadata

    def _count_java_classes(self, java_files: List[str]) -> int:
        """Count Java classes from file paths"""
        count = 0
        for f in java_files:
            if "class " in f or "interface " in f or "enum " in f:
                count += 1
        return max(count, len(java_files) // 3)

    def _estimate_dependencies(self, path: Path) -> int:
        """Estimate number of mod dependencies"""
        return 2

    def _estimate_feature_count(self, metadata: ModMetadata) -> int:
        """Estimate number of features from metadata"""
        features = 0
        if metadata.has_gui:
            features += 2
        if metadata.has_entities:
            features += 3
        if metadata.has_tile_entities:
            features += 2
        return max(features, metadata.class_count // 5)

    def estimate(self, metadata: ModMetadata, model: str = None) -> EstimatedTokenUsage:
        """
        Estimate token usage for a conversion.

        Args:
            metadata: ModMetadata extracted from the mod
            model: Optional model override

        Returns:
            EstimatedTokenUsage with per-phase breakdown
        """
        model = model or self.default_model

        complexity_tier = self._determine_complexity_tier(metadata)
        phase_estimates = {}

        base_input = self._estimate_base_input_tokens(metadata)
        base_output = self._estimate_base_output_tokens(metadata)

        for phase, weight in self.PHASE_WEIGHTS.items():
            phase_input = int(base_input * weight)
            phase_output = int(base_output * weight)

            phase_estimates[phase] = PhaseEstimate(
                phase=phase,
                input_tokens=phase_input,
                output_tokens=phase_output,
                confidence_low=0.8 if complexity_tier == "simple" else 0.7,
                confidence_high=1.2 if complexity_tier == "simple" else 1.3,
            )

        total_input = sum(est.input_tokens for est in phase_estimates.values())
        total_output = sum(est.output_tokens for est in phase_estimates.values())
        total_tokens = total_input + total_output

        estimated_cost = estimate_cost(model, total_input, total_output)
        estimated_duration = self._estimate_duration(metadata)

        confidence_low = 0.85 if complexity_tier == "simple" else 0.75
        confidence_high = 1.15 if complexity_tier == "simple" else 1.25

        result = EstimatedTokenUsage(
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            by_phase=phase_estimates,
            confidence_interval_low=confidence_low,
            confidence_interval_high=confidence_high,
            estimated_cost_usd=estimated_cost,
            model_used=model,
            estimated_duration_seconds=estimated_duration,
            complexity_tier=complexity_tier,
        )

        logger.info(
            f"Token estimate: {total_tokens} tokens (~${estimated_cost:.4f}), "
            f"tier={complexity_tier}, duration~{estimated_duration:.0f}s"
        )

        return result

    def _determine_complexity_tier(self, metadata: ModMetadata) -> str:
        """Determine complexity tier based on metadata"""
        if metadata.total_loc <= 500 and metadata.class_count <= 20:
            return "simple"
        elif metadata.total_loc <= 2000 and metadata.class_count <= 100:
            return "moderate"
        elif metadata.total_loc <= 5000 and metadata.class_count <= 250:
            return "complex"
        else:
            return "very_complex"

    def _estimate_base_input_tokens(self, metadata: ModMetadata) -> int:
        """
        Estimate base input tokens based on LOC and complexity.

        Based on paper finding: context tokens dominate in agentic tasks.
        """
        loc_factor = metadata.total_loc * self.BASE_TOKENS_PER_LOC

        depth_factor = 1 + (metadata.max_class_depth * 0.1)
        complexity_factor = 1 + (metadata.class_count / 500)

        input_tokens = int(
            loc_factor * depth_factor * complexity_factor * self.CONTEXT_OVERHEAD_FACTOR
        )

        input_tokens = max(input_tokens, 5000)

        if metadata.dependency_count > 5:
            input_tokens = int(input_tokens * 1.2)

        return input_tokens

    def _estimate_base_output_tokens(self, metadata: ModMetadata) -> int:
        """
        Estimate base output tokens based on LOC.

        Output tokens correlate with generated code volume.
        """
        loc_factor = metadata.total_loc * 4.5

        complexity_factor = 1 + (metadata.class_count / 200)

        output_tokens = int(loc_factor * complexity_factor)

        output_tokens = max(output_tokens, 3000)

        return output_tokens

    def _estimate_duration(self, metadata: ModMetadata) -> float:
        """Estimate conversion duration in seconds"""
        base_duration = 30.0
        loc_factor = metadata.total_loc * 0.1
        class_factor = metadata.class_count * 0.5
        complexity_tier = self._determine_complexity_tier(metadata)
        complexity_multiplier = (
            1.0 if complexity_tier == "simple" else 1.5 if complexity_tier == "moderate" else 2.0
        )

        return base_duration + (loc_factor + class_factor) * complexity_multiplier

    def start_phase_tracking(self, conversion_id: str) -> None:
        """Start tracking tokens per phase for a conversion"""
        self._phase_trackers[conversion_id] = {phase: 0 for phase in ConversionPhase}

    def record_phase_tokens(
        self,
        conversion_id: str,
        phase: ConversionPhase,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """
        Record tokens used in a phase for tracking.

        Args:
            conversion_id: Conversion identifier
            phase: Current phase
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
        """
        if conversion_id not in self._phase_trackers:
            self.start_phase_tracking(conversion_id)

        self._phase_trackers[conversion_id][phase] += input_tokens + output_tokens

    def get_phase_totals(self, conversion_id: str) -> Dict[ConversionPhase, int]:
        """Get total tokens per phase for a conversion"""
        return self._phase_trackers.get(conversion_id, {})

    def check_budget(
        self,
        estimated_cost: float,
        budget_limit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Check if estimated cost exceeds budget.

        Args:
            estimated_cost: Estimated cost in USD
            budget_limit: Optional budget limit override

        Returns:
            Dict with 'within_budget', 'budget_action', 'message'
        """
        effective_limit = budget_limit or self.cost_alert_threshold

        if estimated_cost <= effective_limit * 0.8:
            return {
                "within_budget": True,
                "budget_action": "allow",
                "message": f"Estimated cost ${estimated_cost:.4f} is within budget",
                "budget_limit": effective_limit,
            }
        elif estimated_cost <= effective_limit:
            return {
                "within_budget": True,
                "budget_action": "warn",
                "message": f"Estimated cost ${estimated_cost:.4f} is approaching budget limit",
                "budget_limit": effective_limit,
            }
        else:
            return {
                "within_budget": False,
                "budget_action": "block",
                "message": f"Estimated cost ${estimated_cost:.4f} exceeds budget limit ${effective_limit:.4f}",
                "budget_limit": effective_limit,
            }

    def generate_cost_report(
        self,
        conversion_id: str,
        estimated: EstimatedTokenUsage,
        actual_by_phase: Dict[ConversionPhase, Dict[str, int]],
        duration_seconds: float,
        budget_limit: Optional[float] = None,
    ) -> ConversionCostReport:
        """
        Generate a post-conversion cost report.

        Args:
            conversion_id: Conversion identifier
            estimated: Pre-conversion estimate
            actual_by_phase: Actual tokens broken down by phase
            duration_seconds: Total conversion duration
            budget_limit: Optional budget limit

        Returns:
            ConversionCostReport for B2B transparency
        """
        actual_input = sum(p.get("input_tokens", 0) for p in actual_by_phase.values())
        actual_output = sum(p.get("output_tokens", 0) for p in actual_by_phase.values())
        actual_cost = estimate_cost(estimated.model_used, actual_input, actual_output)

        budget_exceeded = False
        over_budget_by = 0.0
        if budget_limit and actual_cost > budget_limit:
            budget_exceeded = True
            over_budget_by = actual_cost - budget_limit

        report = ConversionCostReport(
            conversion_id=conversion_id,
            estimated=estimated,
            actual_input_tokens=actual_input,
            actual_output_tokens=actual_output,
            actual_cost_usd=actual_cost,
            by_phase={
                phase.value: {
                    "input_tokens": data.get("input_tokens", 0),
                    "output_tokens": data.get("output_tokens", 0),
                }
                for phase, data in actual_by_phase.items()
            },
            completed_at=datetime.now(timezone.utc),
            duration_seconds=duration_seconds,
            budget_exceeded=budget_exceeded,
            budget_limit_usd=budget_limit,
            over_budget_by=over_budget_by,
        )

        self._record_historical(estimated, actual_input + actual_output, conversion_id)

        return report

    def _record_historical(
        self, estimated: EstimatedTokenUsage, actual_total: int, conversion_id: str
    ) -> None:
        """Record historical data for model improvement"""
        self._historical_data.append(
            {
                "conversion_id": conversion_id,
                "estimated_tokens": estimated.total_input_tokens + estimated.total_output_tokens,
                "actual_tokens": actual_total,
                "estimated_cost": estimated.estimated_cost_usd,
                "complexity_tier": estimated.complexity_tier,
                "timestamp": time.time(),
            }
        )

        if len(self._historical_data) > 1000:
            self._historical_data = self._historical_data[-1000:]

    def get_accuracy_stats(self) -> Dict[str, Any]:
        """Get estimation accuracy statistics from historical data"""
        if not self._historical_data:
            return {"message": "Insufficient data for accuracy stats"}

        ratios = []
        for record in self._historical_data:
            if record["estimated_tokens"] > 0:
                ratio = record["actual_tokens"] / record["estimated_tokens"]
                ratios.append(ratio)

        if not ratios:
            return {"message": "No valid records"}

        avg_ratio = sum(ratios) / len(ratios)
        min_ratio = min(ratios)
        max_ratio = max(ratios)

        within_30_pct = sum(1 for r in ratios if 0.7 <= r <= 1.3) / len(ratios)

        return {
            "sample_count": len(ratios),
            "avg_ratio": round(avg_ratio, 3),
            "min_ratio": round(min_ratio, 3),
            "max_ratio": round(max_ratio, 3),
            "within_30_pct": round(within_30_pct * 100, 1),
        }


_global_estimator: Optional[TokenBudgetEstimator] = None


def get_estimator() -> TokenBudgetEstimator:
    """Get or create global estimator instance"""
    global _global_estimator
    if _global_estimator is None:
        _global_estimator = TokenBudgetEstimator()
    return _global_estimator


def estimate_conversion_cost(
    mod_path: str,
    model: str = None,
    budget_limit: float = None,
) -> Dict[str, Any]:
    """
    Convenience function for quick cost estimation.

    Args:
        mod_path: Path to the mod file
        model: Optional model override
        budget_limit: Optional budget limit for checking

    Returns:
        Dictionary with estimate and budget check results
    """
    estimator = get_estimator()
    metadata = estimator.extract_metadata(mod_path)
    estimate = estimator.estimate(metadata, model)
    budget_check = estimator.check_budget(estimate.estimated_cost_usd, budget_limit)

    return {
        "metadata": {
            "file_count": metadata.file_count,
            "total_loc": metadata.total_loc,
            "class_count": metadata.class_count,
            "complexity_tier": estimate.complexity_tier,
        },
        "estimate": estimate.to_dict(),
        "budget_check": budget_check,
    }
