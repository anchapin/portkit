"""
PackagingAgent coordinator for the packaging subpackage.

This module contains the main PackagingAgent class which coordinates all
packaging operations through delegation to specialized submodules.

Per issue #1278 and #1581.
"""

import json
import logging
from typing import Any, ClassVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from .bundler import Bundler
from .folder_builder import FolderBuilder
from .manifest_builder import ManifestBuilder

logger = logging.getLogger(__name__)


class PackagingAgent:
    """
    Packaging Agent responsible for assembling converted components into
    .mcaddon packages as specified in PRD Feature 2.

    This class coordinates packaging operations through specialized submodules:
    - ManifestBuilder: manifest.json generation
    - FolderBuilder: folder structure creation
    - ResourceMapper: resource mapping and analysis
    - ZipAssembler: zip archive construction
    - Bundler: high-level mcaddon building
    """

    _instance = None

    def __init__(self):
        from agents.addon_validator import AddonValidator
        from agents.bedrock_manifest_generator import BedrockManifestGenerator
        from agents.block_item_generator import BlockItemGenerator
        from agents.entity_converter import EntityConverter
        from agents.file_packager import FilePackager
        from models.smart_assumptions import SmartAssumptionEngine

        self.smart_assumption_engine = SmartAssumptionEngine()

        # Core packaging submodules
        self.manifest_builder = ManifestBuilder()
        self.folder_builder = FolderBuilder()
        self.bundler = Bundler()

        # Validation
        from agents.packaging import PackagingValidator

        self.packaging_validator = PackagingValidator()

        # Enhanced generators
        self.addon_validator = AddonValidator()
        self.manifest_generator_enhanced = BedrockManifestGenerator()
        self.block_item_generator = BlockItemGenerator()
        self.entity_converter = EntityConverter()
        self.file_packager = FilePackager()

        self.manifest_template = {
            "format_version": 2,
            "header": {
                "name": "",
                "description": "",
                "uuid": "",
                "version": [1, 0, 0],
                "min_engine_version": [1, 19, 0],
            },
            "modules": [],
        }

        self.pack_structures = {
            "behavior_pack": {
                "required": {"manifest.json": "manifest"},
                "optional": {
                    "pack_icon.png": "icon",
                    "scripts/": "scripts",
                    "entities/": "entities",
                    "items/": "items",
                    "blocks/": "blocks",
                    "functions/": "functions",
                    "loot_tables/": "loot_tables",
                    "recipes/": "recipes",
                    "spawn_rules/": "spawn_rules",
                    "trading/": "trading",
                },
            },
            "resource_pack": {
                "required": {"manifest.json": "manifest"},
                "optional": {
                    "pack_icon.png": "icon",
                    "textures/": "textures",
                    "models/": "models",
                    "sounds/": "sounds",
                    "animations/": "animations",
                    "animation_controllers/": "animation_controllers",
                    "attachables/": "attachables",
                    "entity/": "entity_textures",
                    "font/": "fonts",
                    "particles/": "particles",
                },
            },
        }

        self.package_constraints = {
            "max_total_size_mb": 500,
            "max_files": 1000,
            "required_files": ["manifest.json"],
            "forbidden_extensions": [".exe", ".dll", ".bat", ".sh"],
            "max_manifest_size_kb": 10,
        }

    @classmethod
    def get_instance(cls):
        """Get singleton instance of PackagingAgent"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self):
        """Get tools available to this agent"""
        return [
            PackagingAgent.analyze_conversion_components_tool,
            PackagingAgent.create_package_structure_tool,
            PackagingAgent.generate_manifests_tool,
            PackagingAgent.validate_package_tool,
            PackagingAgent.build_mcaddon_tool,
            PackagingAgent.generate_enhanced_manifests_tool,
            PackagingAgent.generate_blocks_and_items_tool,
            PackagingAgent.generate_entities_tool,
            PackagingAgent.package_enhanced_addon_tool,
            PackagingAgent.validate_enhanced_addon_tool,
            PackagingAgent.validate_mcaddon_structure_tool,
            PackagingAgent.validate_manifest_schema_tool,
            PackagingAgent.generate_validation_report_tool,
        ]

    def generate_manifest(self, mod_info: str, pack_type: str) -> str:
        """Generate manifest for a pack."""
        return self.manifest_builder.generate_manifest(mod_info, pack_type)

    def generate_manifests(self, manifest_data: str) -> str:
        """Generate manifests for packaging."""
        return self.manifest_builder.generate_manifests(manifest_data)

    def analyze_conversion_components(self, component_data: str) -> str:
        """Analyze conversion components for packaging."""
        return self.folder_builder.analyze_conversion_components(component_data)

    def create_package_structure(self, structure_data) -> str:
        """Create package structure for Bedrock addon."""
        return self.folder_builder.create_package_structure(structure_data)

    def validate_package(self, validation_data: str) -> str:
        """Validate the package structure."""
        return self.folder_builder.validate_package(validation_data)

    def build_mcaddon(self, build_data) -> str:
        """Build the final mcaddon package."""
        return self.bundler.build_mcaddon(build_data)

    def build_mcaddon_mvp(self, temp_dir: str, output_path: str, mod_name: str = None):
        """Build .mcaddon file from temp directory structure for MVP pipeline."""
        return self.bundler.build_mcaddon_mvp(temp_dir, output_path, mod_name)

    def _validate_mcaddon_file(self, mcaddon_path):
        """Validate a created .mcaddon file."""
        return self.bundler._validate_mcaddon_file(mcaddon_path)

    @staticmethod
    def _analyze_conversion_components(component_data: str) -> str:
        """Analyze conversion components for packaging."""
        agent = PackagingAgent.get_instance()
        return agent.analyze_conversion_components(component_data)

    @staticmethod
    def _create_package_structure(structure_data: str) -> str:
        """Create package structure for Bedrock addon."""
        agent = PackagingAgent.get_instance()
        return agent.create_package_structure(structure_data)

    @staticmethod
    def _generate_manifests(manifest_data: str) -> str:
        """Generate manifest files for the addon."""
        agent = PackagingAgent.get_instance()
        return agent.generate_manifests(manifest_data)

    @staticmethod
    def _validate_package(validation_data: str) -> str:
        """Validate the package structure."""
        agent = PackagingAgent.get_instance()
        return agent.validate_package(validation_data)

    @staticmethod
    def _build_mcaddon(build_data: str) -> str:
        """Build the final mcaddon package."""
        agent = PackagingAgent.get_instance()
        return agent.build_mcaddon(build_data)

    @staticmethod
    def _generate_enhanced_manifests(mod_data: str) -> str:
        """Generate enhanced Bedrock manifests using the new manifest generator."""
        try:
            agent = PackagingAgent.get_instance()

            if isinstance(mod_data, str):
                data = json.loads(mod_data)
            else:
                data = mod_data

            bp_manifest, rp_manifest = agent.manifest_generator_enhanced.generate_manifests(data)

            result = {
                "success": True,
                "behavior_pack_manifest": bp_manifest,
                "resource_pack_manifest": rp_manifest,
                "message": "Enhanced manifests generated successfully",
            }

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Enhanced manifest generation error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _generate_blocks_and_items(conversion_data: str) -> str:
        """Generate Bedrock blocks and items from Java conversion data."""
        try:
            agent = PackagingAgent.get_instance()

            if isinstance(conversion_data, str):
                data = json.loads(conversion_data)
            else:
                data = conversion_data

            java_blocks = data.get("blocks", [])
            java_items = data.get("items", [])
            java_recipes = data.get("recipes", [])

            bedrock_blocks = agent.block_item_generator.generate_blocks(java_blocks)
            bedrock_items = agent.block_item_generator.generate_items(java_items)
            bedrock_recipes = agent.block_item_generator.generate_recipes(java_recipes)

            result = {
                "success": True,
                "blocks": bedrock_blocks,
                "items": bedrock_items,
                "recipes": bedrock_recipes,
                "stats": {
                    "blocks_generated": len(bedrock_blocks),
                    "items_generated": len(bedrock_items),
                    "recipes_generated": len(bedrock_recipes),
                },
                "message": "Blocks, items, and recipes generated successfully",
            }

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Block/item generation error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _generate_entities(entity_data: str) -> str:
        """Generate Bedrock entities from Java entity data."""
        try:
            agent = PackagingAgent.get_instance()

            if isinstance(entity_data, str):
                data = json.loads(entity_data)
            else:
                data = entity_data

            java_entities = data.get("entities", [])

            bedrock_entities = agent.entity_converter.convert_entities(java_entities)

            result = {
                "success": True,
                "entities": bedrock_entities,
                "stats": {"entities_generated": len(bedrock_entities)},
                "message": "Entities generated successfully",
            }

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Entity generation error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _package_enhanced_addon(package_data: str) -> str:
        """Package addon using the enhanced file packager."""
        try:
            agent = PackagingAgent.get_instance()

            if isinstance(package_data, str):
                data = json.loads(package_data)
            else:
                data = package_data

            result = agent.file_packager.package_addon(data)

            if result["success"]:
                logger.info(f"Enhanced packaging successful: {result['output_path']}")

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Enhanced packaging error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _validate_enhanced_addon(addon_path: str) -> str:
        """Validate addon using the enhanced validator."""
        try:
            agent = PackagingAgent.get_instance()

            validation_result = agent.addon_validator.validate_addon(Path(addon_path))

            def convert_paths(obj):
                from pathlib import Path as PathType

                if isinstance(obj, PathType):
                    return str(obj)
                elif isinstance(obj, dict):
                    return {k: convert_paths(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_paths(item) for item in obj]
                return obj

            result = convert_paths(validation_result)
            result["addon_path"] = addon_path

            logger.info(
                f"Enhanced validation completed. Score: {result.get('overall_score', 0)}/100"
            )

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Enhanced validation error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _validate_mcaddon_structure(mcaddon_path: str) -> str:
        """Validate .mcaddon file structure using comprehensive validator."""
        try:
            agent = PackagingAgent.get_instance()
            validator = agent.packaging_validator

            result = validator.validate_mcaddon(Path(mcaddon_path))

            result_dict = {
                "is_valid": result.is_valid,
                "overall_score": result.overall_score,
                "issues": [
                    {
                        "severity": issue.severity.value,
                        "category": issue.category,
                        "message": issue.message,
                        "file_path": str(issue.file_path) if issue.file_path else None,
                        "suggestion": issue.suggestion,
                    }
                    for issue in result.issues
                ],
                "stats": result.stats,
                "compatibility": result.compatibility,
                "file_structure": result.file_structure,
            }

            return json.dumps(result_dict)

        except Exception as e:
            logger.error(f"Structure validation error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _validate_manifest_schema(manifest_data: str) -> str:
        """Validate a manifest.json against Bedrock JSON schema."""
        try:
            agent = PackagingAgent.get_instance()
            validator = agent.packaging_validator

            manifest_path = Path(manifest_data)
            if manifest_path.exists() and manifest_path.is_file():
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
            else:
                manifest = json.loads(manifest_data)

            if "manifest" not in validator.schemas:
                return json.dumps({"success": False, "error": "Manifest schema not loaded"})

            try:
                import jsonschema

                jsonschema.validate(manifest, validator.schemas["manifest"])
                return json.dumps(
                    {"success": True, "valid": True, "message": "Manifest passes schema validation"}
                )
            except jsonschema.ValidationError as e:
                return json.dumps(
                    {
                        "success": True,
                        "valid": False,
                        "error": e.message,
                        "path": list(e.path) if e.path else [],
                        "schema_path": list(e.schema_path) if e.schema_path else [],
                    }
                )

        except json.JSONDecodeError as e:
            return json.dumps({"success": False, "error": f"Invalid JSON: {e}"})
        except Exception as e:
            logger.error(f"Manifest schema validation error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _generate_validation_report(mcaddon_path: str) -> str:
        """Generate a human-readable validation report for .mcaddon file."""
        try:
            agent = PackagingAgent.get_instance()
            validator = agent.packaging_validator

            from agents.packaging import generate_validation_report

            result = validator.validate_mcaddon(Path(mcaddon_path))
            report = generate_validation_report(result)

            return json.dumps(
                {
                    "success": True,
                    "report": report,
                    "is_valid": result.is_valid,
                    "score": result.overall_score,
                }
            )

        except Exception as e:
            logger.error(f"Report generation error: {e}")
            return json.dumps({"success": False, "error": str(e)})


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
        return PackagingAgent._generate_enhanced_manifests(mod_data)


class _GenerateBlocksAndItemsTool(_BasePackagingTool):
    name: str = "generate_blocks_and_items_tool"
    description: str = (
        "Generate Bedrock blocks, items, and recipes from Java conversion data. "
        "Args: conversion_data (str, required) — JSON with blocks/items/recipes."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateBlocksAndItemsInput

    def _run(self, conversion_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._generate_blocks_and_items(conversion_data)


class _GenerateEntitiesTool(_BasePackagingTool):
    name: str = "generate_entities_tool"
    description: str = (
        "Generate Bedrock entities from Java entity data. "
        "Args: entity_data (str, required) — JSON with entities list."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateEntitiesInput

    def _run(self, entity_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._generate_entities(entity_data)


class _PackageEnhancedAddonTool(_BasePackagingTool):
    name: str = "package_enhanced_addon_tool"
    description: str = (
        "Package an addon via the enhanced file packager. "
        "Args: package_data (str, required) — JSON describing the addon."
    )
    args_schema: ClassVar[type[BaseModel]] = _PackageEnhancedAddonInput

    def _run(self, package_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._package_enhanced_addon(package_data)


class _ValidateEnhancedAddonTool(_BasePackagingTool):
    name: str = "validate_enhanced_addon_tool"
    description: str = (
        "Validate an addon via the enhanced validator. "
        "Args: addon_path (str, required) — filesystem path to the addon."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateEnhancedAddonInput

    def _run(self, addon_path: str) -> str:  # type: ignore[override]
        return PackagingAgent._validate_enhanced_addon(addon_path)


class _ValidateMcaddonStructureTool(_BasePackagingTool):
    name: str = "validate_mcaddon_structure_tool"
    description: str = (
        "Validate the .mcaddon file structure via the comprehensive validator. "
        "Args: mcaddon_path (str, required) — filesystem path to the .mcaddon."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateMcaddonStructureInput

    def _run(self, mcaddon_path: str) -> str:  # type: ignore[override]
        return PackagingAgent._validate_mcaddon_structure(mcaddon_path)


class _ValidateManifestSchemaTool(_BasePackagingTool):
    name: str = "validate_manifest_schema_tool"
    description: str = (
        "Validate a manifest.json against the Bedrock JSON schema. "
        "Args: manifest_data (str, required) — file path or raw JSON."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateManifestSchemaInput

    def _run(self, manifest_data: str) -> str:  # type: ignore[override]
        return PackagingAgent._validate_manifest_schema(manifest_data)


class _GenerateValidationReportTool(_BasePackagingTool):
    name: str = "generate_validation_report_tool"
    description: str = (
        "Generate a human-readable validation report for a .mcaddon file. "
        "Args: mcaddon_path (str, required) — filesystem path to the .mcaddon."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateValidationReportInput

    def _run(self, mcaddon_path: str) -> str:  # type: ignore[override]
        return PackagingAgent._generate_validation_report(mcaddon_path)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level tool instances — preserved as class attributes on
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


from pathlib import Path