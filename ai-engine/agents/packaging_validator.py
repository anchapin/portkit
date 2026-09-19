"""
Enhanced Packaging Validator for comprehensive .mcaddon validation

This module is now a thin wrapper that imports from the packaging/ subpackage.
All implementation details have been moved to ai-engine/agents/packaging/validator.py.

Per issue #1278: Split packaging_agent.py (42K) + packaging_validator.py (31K) into packaging/ subpackage
"""

from agents.packaging.validator import (
    PackagingValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)

__all__ = [
    "PackagingValidator",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
]
