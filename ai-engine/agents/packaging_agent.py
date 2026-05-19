"""
Packaging Agent - thin wrapper importing from packaging/ subpackage.

This module is a backward-compatibility wrapper. All implementation has been
moved to ai-engine/agents/packaging/ subpackage per issue #1278 and #1581.

Issue #1581: Complete packaging_agent.py split
  - #1625: Create packaging/agent.py - PackagingAgent coordinator
  - #1640: Create packaging/manifest_builder.py - manifest assembly
  - #1641: Create packaging/zip_assembler.py - zip construction
  - #1642: Create packaging/resource_mapper.py - resource mapping
  - #1643: Stub packaging_agent.py + verify packaging/__init__.py

All real implementation now lives in agents.packaging subpackage.
"""

# Re-export everything from the packaging subpackage for backward compatibility
from agents.packaging import (
    Bundler,
    FolderBuilder,
    ManifestBuilder,
    PackagingAgent,
    PackagingCoordinator,
    PackagingValidator,
    ResourceMapper,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    ZipAssembler,
    generate_validation_report,
)

# Also re-export from manifest module for any direct importers
from agents.packaging.manifest import ManifestGenerator

__all__ = [
    "Bundler",
    "FolderBuilder",
    "ManifestBuilder",
    "ManifestGenerator",
    "PackagingAgent",
    "PackagingCoordinator",
    "PackagingValidator",
    "ResourceMapper",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
    "ZipAssembler",
    "generate_validation_report",
]