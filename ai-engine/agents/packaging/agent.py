"""
PackagingAgent — thin re-export shim.

Per issue #1766 this file was split into focused modules:
- orchestrator.py — PackagingAgent class (high-level packaging coordination)
- assembler.py    — execution logic (manifests, blocks/items, entities, packaging)
- tools.py        — Pydantic args_schema models + typed BaseTool wrappers
- agent.py (this) — backwards-compat re-export of the above

Public API (PackagingAgent + typed tool classes) is unchanged; existing
imports from agents.packaging.agent or agents.packaging_agent continue to work.
"""

# Importing tools attaches the module-level tool instances to PackagingAgent
# as class attributes (mirrors the pre-split side-effect), so it must run
# before any caller accesses PackagingAgent.<tool_name>.
from . import tools  # noqa: F401
from .orchestrator import PackagingAgent
from .tools import (
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
    "PackagingAgent",
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
