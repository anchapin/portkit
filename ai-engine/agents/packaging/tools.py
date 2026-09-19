"""
Typed LangChain tool wrappers for the Packaging Agent.

Extracted from packaging/agent.py per issue #1766. Each BaseTool subclass
exposes an explicit Pydantic ``args_schema`` so chat models with native
tool-calling can invoke it with validated arguments (Phase 8 A4b, refs #1201).

The legacy ``<name>_data: str`` shape is preserved end-to-end so existing
call sites and the coverage suite (tests/test_packaging_agent.py) pass
unchanged.

Importing this module attaches the tool instances to PackagingAgent as class
attributes, preserving the existing access patterns
(``PackagingAgent.<tool_name>`` and ``agent.<tool_name>``).
"""

from typing import Any, ClassVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from .assembler import (
    generate_blocks_and_items,
    generate_enhanced_manifests,
    generate_entities,
    generate_validation_report,
    package_enhanced_addon,
    validate_enhanced_addon,
    validate_manifest_schema,
    validate_mcaddon_structure,
)
from .orchestrator import PackagingAgent

# ─────────────────────────────────────────────────────────────────────────────
# Typed args_schema models — one per LangChain tool wrapper
# ─────────────────────────────────────────────────────────────────────────────


class _AnalyzeConversionComponentsInput(BaseModel):
    """Args for :class:`_AnalyzeConversionComponentsTool`."""

    model_config = ConfigDict(extra="forbid")
    component_data: str = Field(
        min_length=1,
        description="JSON string describing the components to analyze for packaging.",
    )


class _CreatePackageStructureInput(BaseModel):
    """Args for :class:`_CreatePackageStructureTool`."""

    model_config = ConfigDict(extra="forbid")
    structure_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock package structure to create.",
    )


class _GenerateManifestsInput(BaseModel):
    """Args for :class:`_GenerateManifestsTool`."""

    model_config = ConfigDict(extra="forbid")
    manifest_data: str = Field(
        min_length=1,
        description="JSON string describing the manifest data to generate.",
    )


class _ValidatePackageInput(BaseModel):
    """Args for :class:`_ValidatePackageTool`."""

    model_config = ConfigDict(extra="forbid")
    validation_data: str = Field(
        min_length=1,
        description="JSON string describing the package data to validate.",
    )


class _BuildMcaddonInput(BaseModel):
    """Args for :class:`_BuildMcaddonTool`."""

    model_config = ConfigDict(extra="forbid")
    build_data: Any = Field(
        description=(
            "JSON string or dict describing the addon to bundle into a "
            ".mcaddon file. ``Any`` preserves the legacy build_data shape."
        ),
    )


class _GenerateEnhancedManifestsInput(BaseModel):
    """Args for :class:`_GenerateEnhancedManifestsTool`."""

    model_config = ConfigDict(extra="forbid")
    mod_data: str = Field(
        min_length=1,
        description="JSON string describing the mod data for the enhanced manifest generator.",
    )


class _GenerateBlocksAndItemsInput(BaseModel):
    """Args for :class:`_GenerateBlocksAndItemsTool`."""

    model_config = ConfigDict(extra="forbid")
    conversion_data: str = Field(
        min_length=1,
        description=(
            "JSON string with blocks/items/recipes lists to convert into Bedrock JSON definitions."
        ),
    )


class _GenerateEntitiesInput(BaseModel):
    """Args for :class:`_GenerateEntitiesTool`."""

    model_config = ConfigDict(extra="forbid")
    entity_data: str = Field(
        min_length=1,
        description="JSON string with an entities list to convert into Bedrock entity JSON.",
    )


class _PackageEnhancedAddonInput(BaseModel):
    """Args for :class:`_PackageEnhancedAddonTool`."""

    model_config = ConfigDict(extra="forbid")
    package_data: str = Field(
        min_length=1,
        description="JSON string describing the enhanced addon to package.",
    )


class _ValidateEnhancedAddonInput(BaseModel):
    """Args for :class:`_ValidateEnhancedAddonTool`."""

    model_config = ConfigDict(extra="forbid")
    addon_path: str = Field(
        min_length=1,
        description="Filesystem path to the addon directory or archive to validate.",
    )


class _ValidateMcaddonStructureInput(BaseModel):
    """Args for :class:`_ValidateMcaddonStructureTool`."""

    model_config = ConfigDict(extra="forbid")
    mcaddon_path: str = Field(
        min_length=1,
        description="Filesystem path to the .mcaddon archive to validate.",
    )


class _ValidateManifestSchemaInput(BaseModel):
    """Args for :class:`_ValidateManifestSchemaTool`."""

    model_config = ConfigDict(extra="forbid")
    manifest_data: str = Field(
        min_length=1,
        description=(
            "Either a filesystem path to a manifest.json file, or a JSON "
            "string containing the manifest data."
        ),
    )


class _GenerateValidationReportInput(BaseModel):
    """Args for :class:`_GenerateValidationReportTool`."""

    model_config = ConfigDict(extra="forbid")
    mcaddon_path: str = Field(
        min_length=1,
        description="Filesystem path to the .mcaddon archive to validate and report on.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Typed BaseTool subclasses — replace the previous @tool @staticmethod wrappers
# ─────────────────────────────────────────────────────────────────────────────


class _BasePackagingTool(BaseTool):
    """Common scaffolding for Packaging Agent typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class _AnalyzeConversionComponentsTool(_BasePackagingTool):
    name: str = "analyze_conversion_components_tool"
    description: str = (
        "Analyze conversion components for packaging. "
        "Args: component_data (str, required) — JSON describing the components."
    )
    args_schema: ClassVar[type[BaseModel]] = _AnalyzeConversionComponentsInput

    def _run(self, component_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._analyze_conversion_components(component_data)


class _CreatePackageStructureTool(_BasePackagingTool):
    name: str = "create_package_structure_tool"
    description: str = (
        "Create the Bedrock package structure on disk. "
        "Args: structure_data (str, required) — JSON describing the structure."
    )
    args_schema: ClassVar[type[BaseModel]] = _CreatePackageStructureInput

    def _run(self, structure_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._create_package_structure(structure_data)


class _GenerateManifestsTool(_BasePackagingTool):
    name: str = "generate_manifests_tool"
    description: str = (
        "Generate Bedrock manifest files for the addon. "
        "Args: manifest_data (str, required) — JSON describing the manifest data."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateManifestsInput

    def _run(self, manifest_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._generate_manifests(manifest_data)


class _ValidatePackageTool(_BasePackagingTool):
    name: str = "validate_package_tool"
    description: str = (
        "Validate the package structure. "
        "Args: validation_data (str, required) — JSON describing the package."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidatePackageInput

    def _run(self, validation_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._validate_package(validation_data)


class _BuildMcaddonTool(_BasePackagingTool):
    name: str = "build_mcaddon_tool"
    description: str = (
        "Bundle the package into a .mcaddon file. "
        "Args: build_data (str or dict, required) — JSON describing the addon."
    )
    args_schema: ClassVar[type[BaseModel]] = _BuildMcaddonInput

    def _run(self, build_data: Any) -> str:  # type: ignore[override]
        return PackagingAgent._build_mcaddon(build_data)


class _GenerateEnhancedManifestsTool(_BasePackagingTool):
    name: str = "generate_enhanced_manifests_tool"
    description: str = (
        "Generate enhanced Bedrock manifests via the new manifest generator. "
        "Args: mod_data (str, required) — JSON describing the mod."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateEnhancedManifestsInput

    def _run(self, mod_data: str) -> str:  # type: ignore[override]
        return generate_enhanced_manifests(mod_data)


class _GenerateBlocksAndItemsTool(_BasePackagingTool):
    name: str = "generate_blocks_and_items_tool"
    description: str = (
        "Generate Bedrock blocks, items, and recipes from Java conversion data. "
        "Args: conversion_data (str, required) — JSON with blocks/items/recipes."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateBlocksAndItemsInput

    def _run(self, conversion_data: str) -> str:  # type: ignore[override]
        return generate_blocks_and_items(conversion_data)


class _GenerateEntitiesTool(_BasePackagingTool):
    name: str = "generate_entities_tool"
    description: str = (
        "Generate Bedrock entities from Java entity data. "
        "Args: entity_data (str, required) — JSON with entities list."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateEntitiesInput

    def _run(self, entity_data: str) -> str:  # type: ignore[override]
        return generate_entities(entity_data)


class _PackageEnhancedAddonTool(_BasePackagingTool):
    name: str = "package_enhanced_addon_tool"
    description: str = (
        "Package an addon via the enhanced file packager. "
        "Args: package_data (str, required) — JSON describing the addon."
    )
    args_schema: ClassVar[type[BaseModel]] = _PackageEnhancedAddonInput

    def _run(self, package_data: str) -> str:  # type: ignore[override]
        return package_enhanced_addon(package_data)


class _ValidateEnhancedAddonTool(_BasePackagingTool):
    name: str = "validate_enhanced_addon_tool"
    description: str = (
        "Validate an addon via the enhanced validator. "
        "Args: addon_path (str, required) — filesystem path to the addon."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateEnhancedAddonInput

    def _run(self, addon_path: str) -> str:  # type: ignore[override]
        return validate_enhanced_addon(addon_path)


class _ValidateMcaddonStructureTool(_BasePackagingTool):
    name: str = "validate_mcaddon_structure_tool"
    description: str = (
        "Validate the .mcaddon file structure via the comprehensive validator. "
        "Args: mcaddon_path (str, required) — filesystem path to the .mcaddon."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateMcaddonStructureInput

    def _run(self, mcaddon_path: str) -> str:  # type: ignore[override]
        return validate_mcaddon_structure(mcaddon_path)


class _ValidateManifestSchemaTool(_BasePackagingTool):
    name: str = "validate_manifest_schema_tool"
    description: str = (
        "Validate a manifest.json against the Bedrock JSON schema. "
        "Args: manifest_data (str, required) — file path or raw JSON."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateManifestSchemaInput

    def _run(self, manifest_data: str) -> str:  # type: ignore[override]
        return validate_manifest_schema(manifest_data)


class _GenerateValidationReportTool(_BasePackagingTool):
    name: str = "generate_validation_report_tool"
    description: str = (
        "Generate a human-readable validation report for a .mcaddon file. "
        "Args: mcaddon_path (str, required) — filesystem path to the .mcaddon."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateValidationReportInput

    def _run(self, mcaddon_path: str) -> str:  # type: ignore[override]
        return generate_validation_report(mcaddon_path)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level tool instances — attached as class attributes on
# PackagingAgent so the existing access patterns
# (``PackagingAgent.<tool_name>`` and ``agent.<tool_name>``) both continue
# to work unchanged for call sites and tests.
# ─────────────────────────────────────────────────────────────────────────────


PackagingAgent.analyze_conversion_components_tool = _AnalyzeConversionComponentsTool()
PackagingAgent.create_package_structure_tool = _CreatePackageStructureTool()
PackagingAgent.generate_manifests_tool = _GenerateManifestsTool()
PackagingAgent.validate_package_tool = _ValidatePackageTool()
PackagingAgent.build_mcaddon_tool = _BuildMcaddonTool()
PackagingAgent.generate_enhanced_manifests_tool = _GenerateEnhancedManifestsTool()
PackagingAgent.generate_blocks_and_items_tool = _GenerateBlocksAndItemsTool()
PackagingAgent.generate_entities_tool = _GenerateEntitiesTool()
PackagingAgent.package_enhanced_addon_tool = _PackageEnhancedAddonTool()
PackagingAgent.validate_enhanced_addon_tool = _ValidateEnhancedAddonTool()
PackagingAgent.validate_mcaddon_structure_tool = _ValidateMcaddonStructureTool()
PackagingAgent.validate_manifest_schema_tool = _ValidateManifestSchemaTool()
PackagingAgent.generate_validation_report_tool = _GenerateValidationReportTool()
