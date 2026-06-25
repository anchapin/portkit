"""
GRPO Model Comparison Evaluation Framework

Comprehensive evaluation framework for comparing GRPO models on the MMSD test set.
"""

from eval.grpo_model_comparison import (
    GRPOComparisonBenchmark,
    GRPOModelConfig,
    GRPO_MODELS,
    ComparisonReport,
    ModelAggregateResult,
    ModelSampleResult,
)

__all__ = [
    "GRPOComparisonBenchmark",
    "GRPOModelConfig",
    "GRPO_MODELS",
    "ComparisonReport",
    "ModelAggregateResult",
    "ModelSampleResult",
]
