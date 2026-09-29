"""
Pre-Conversion Scanner Models

Shared dataclasses and enums for the pre-conversion scanning phase.

Issue: #1769 - Split pre_conversion_scanner.py into focused modules
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RiskSeverity(Enum):
    """Severity level for identified risks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(Enum):
    """Category of the identified risk."""

    DEPENDENCY = "dependency"
    COMPLEXITY = "complexity"
    PATTERN = "pattern"
    ARCHITECTURE = "architecture"
    ASSET = "asset"
    COMPATIBILITY = "compatibility"
    SECURITY = "security"


@dataclass
class RiskItem:
    """Individual risk identified during scan."""

    risk_id: str
    severity: RiskSeverity
    category: RiskCategory
    title: str
    description: str
    location: Optional[str] = None
    suggestion: Optional[str] = None
    conversion_impact: Optional[str] = None
    evidence: List[str] = field(default_factory=list)


@dataclass
class ScanMetadata:
    """Metadata about the scanned file."""

    filename: str
    file_size: int
    file_count: int
    has_manifest: bool
    manifest_version: Optional[str] = None
    mod_name: Optional[str] = None
    minecraft_version: Optional[str] = None


@dataclass
class PreConversionScanResult:
    """Complete result of pre-conversion scan."""

    scan_id: str
    metadata: ScanMetadata
    overall_risk_level: RiskSeverity
    total_issues: int
    risks: List[RiskItem]
    can_proceed: bool
    warnings_summary: str
    recommendations: List[str]
    scan_timestamp: str
    version: str = "1.0"
