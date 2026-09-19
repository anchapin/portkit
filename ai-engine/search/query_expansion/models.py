"""
Core data models and enums for the query expansion system.

Shared types used by every expander module and the coordinator engine.
Extracted from the original ``search/query_expansion.py`` monolith (issue #1731).
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ExpansionStrategy(str, Enum):
    """Query expansion strategies available."""

    SYNONYM_EXPANSION = "synonym_expansion"
    CONTEXTUAL_EXPANSION = "contextual_expansion"
    DOMAIN_EXPANSION = "domain_expansion"
    SEMANTIC_EXPANSION = "semantic_expansion"
    HISTORICAL_EXPANSION = "historical_expansion"


@dataclass
class ExpansionTerm:
    """Term added during query expansion with metadata."""

    term: str
    expansion_type: ExpansionStrategy
    confidence: float
    source: str
    weight: float = 1.0


@dataclass
class ExpandedQuery:
    """Query after expansion with metadata."""

    original_query: str
    expanded_query: str
    expansion_terms: List[ExpansionTerm]
    expansion_confidence: float
    expansion_metadata: Dict[str, Any]
