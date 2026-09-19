"""
Reasoning Pattern Discovery for Test-Time Scaling

Implements automatic discovery of optimal agentic reasoning patterns for
Java-to-Bedrock conversion using environment feedback, based on:
https://arxiv.org/abs/2605.08083v1 (LLMs Improving LLMs)

The system discovers which reasoning patterns work best for different
conversion scenarios (NBT logic, GUI, entities, etc.) by testing candidate
patterns against validation outcomes.
"""

from .reasoning_pattern import (
    ReasoningPattern,
    ReasoningStep,
    PatternPerformance,
    FeatureType,
)
from .pattern_discovery import PatternDiscoveryEngine
from .pattern_selector import PatternSelector

__all__ = [
    "ReasoningPattern",
    "ReasoningStep",
    "PatternPerformance",
    "FeatureType",
    "PatternDiscoveryEngine",
    "PatternSelector",
]
