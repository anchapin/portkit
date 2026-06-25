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

import logging

logger = logging.getLogger(__name__)

from agents.packaging import (
    Bundler,
    FolderBuilder,
    ManifestBuilder,
    PackagingAgent,
    PackagingValidator,
    ResourceMapper,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    ZipAssembler,
    generate_validation_report,
)

# Re-export typed tool classes for backward compatibility with tests
from agents.packaging.agent import (
    _AnalyzeConversionComponentsInput,
    _AnalyzeConversionComponentsTool,
    _BuildMcaddonInput,
    _BuildMcaddonTool,
    _CreatePackageStructureInput,
    _CreatePackageStructureTool,
    _GenerateBlocksAndItemsInput,
    _GenerateBlocksAndItemsTool,
    _GenerateEnhancedManifestsInput,
    _GenerateEnhancedManifestsTool,
    _GenerateEntitiesInput,
    _GenerateEntitiesTool,
    _GenerateManifestsInput,
    _GenerateManifestsTool,
    _GenerateValidationReportInput,
    _GenerateValidationReportTool,
    _PackageEnhancedAddonInput,
    _PackageEnhancedAddonTool,
    _ValidateEnhancedAddonInput,
    _ValidateEnhancedAddonTool,
    _ValidateManifestSchemaInput,
    _ValidateManifestSchemaTool,
    _ValidateMcaddonStructureInput,
    _ValidateMcaddonStructureTool,
    _ValidatePackageInput,
    _ValidatePackageTool,
)

__all__ = [
    "Bundler",
    "FolderBuilder",
    "ManifestBuilder",
    "PackagingAgent",
    "PackagingValidator",
    "ResourceMapper",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
    "ZipAssembler",
    "generate_validation_report",
    "_AnalyzeConversionComponentsInput",
    "_AnalyzeConversionComponentsTool",
    "_BuildMcaddonInput",
    "_BuildMcaddonTool",
    "_CreatePackageStructureInput",
    "_CreatePackageStructureTool",
    "_GenerateBlocksAndItemsInput",
    "_GenerateBlocksAndItemsTool",
    "_GenerateEnhancedManifestsInput",
    "_GenerateEnhancedManifestsTool",
    "_GenerateEntitiesInput",
    "_GenerateEntitiesTool",
    "_GenerateManifestsInput",
    "_GenerateManifestsTool",
    "_GenerateValidationReportInput",
    "_GenerateValidationReportTool",
    "_PackageEnhancedAddonInput",
    "_PackageEnhancedAddonTool",
    "_ValidateEnhancedAddonInput",
    "_ValidateEnhancedAddonTool",
    "_ValidateManifestSchemaInput",
    "_ValidateManifestSchemaTool",
    "_ValidateMcaddonStructureInput",
    "_ValidateMcaddonStructureTool",
    "_ValidatePackageInput",
    "_ValidatePackageTool",
]
