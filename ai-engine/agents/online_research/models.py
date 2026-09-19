"""Data models for the Online Research agent.

Defines the :class:`SourceType` enum and the ``ResearchSource``,
``FeatureChecklistItem`` and ``ValidationReport`` dataclasses used across the
``online_research`` subpackage (issue #1730).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class SourceType(Enum):
    """Types of sources for online research."""

    CURSEFORGE = "curseforge"
    MODRINTH = "modrinth"
    YOUTUBE = "youtube"
    GENERIC_URL = "generic_url"
    UNKNOWN = "unknown"


@dataclass
class ResearchSource:
    """Represents a research source URL."""

    url: str
    source_type: SourceType
    title: str
    description: str
    metadata: Dict[str, Any]
    fetched_at: datetime


@dataclass
class FeatureChecklistItem:
    """A single feature in the checklist."""

    feature_name: str
    description: str
    category: str
    priority: str  # high, medium, low
    detected: bool
    evidence: List[str]
    validation_status: str  # verified, missing, unclear


@dataclass
class ValidationReport:
    """Report from validating converted addon against research."""

    overall_score: float
    feature_checklist: List[FeatureChecklistItem]
    verified_features: List[str]
    missing_features: List[str]
    unclear_features: List[str]
    recommendations: List[str]
    research_sources: List[ResearchSource]
