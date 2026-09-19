"""
Shared types for the hybrid search engine family.

This module collects the small enums and dataclasses used across the
keyword, hybrid, and unified search engines so each engine module can
depend on a single, dependency-light types module instead of importing
from one another just for type definitions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List

from schemas.multimodal_schema import MultiModalDocument


class SearchMode(str, Enum):
    """Search modes for the hybrid search engine."""

    VECTOR_ONLY = "vector_only"
    KEYWORD_ONLY = "keyword_only"
    HYBRID = "hybrid"
    ADAPTIVE = "adaptive"


class RankingStrategy(str, Enum):
    """Ranking strategies for combining scores."""

    WEIGHTED_SUM = "weighted_sum"
    RECIPROCAL_RANK_FUSION = "reciprocal_rank_fusion"
    RRF = RECIPROCAL_RANK_FUSION  # Alias for convenience
    BAYESIAN_COMBINATION = "bayesian_combination"
    LEARNED_COMBINATION = "learned_combination"


@dataclass
class SearchCandidate:
    """Candidate document with multiple relevance scores."""

    document: MultiModalDocument
    vector_score: float = 0.0
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    context_score: float = 0.0
    final_score: float = 0.0
    explanation: List[str] = None

    def __post_init__(self):
        if self.explanation is None:
            self.explanation = []
