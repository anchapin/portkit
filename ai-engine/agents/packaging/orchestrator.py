"""
PackagingAgent — high-level packaging workflow coordinator.

Extracted from packaging/agent.py per issue #1766. The PackagingAgent class
holds packaging state (submodule instances, manifest templates, pack
structures, package constraints) and exposes thin orchestration methods that
delegate to those submodules.

Execution logic that parses JSON and assembles output from generators lives
in assembler.py; typed LangChain tool wrappers live in tools.py. This file
intentionally holds only the coordinator.
"""

import logging

from .bundler import Bundler
from .folder_builder import FolderBuilder
from .manifest_builder import ManifestBuilder

logger = logging.getLogger(__name__)


class PackagingAgent:
    """
    Packaging Agent responsible for assembling converted components into
    .mcaddon packages as specified in PRD Feature 2.

    Coordinates packaging operations through specialized submodules:
    - ManifestBuilder: manifest.json generation
    - FolderBuilder: folder structure creation
    - Bundler: high-level mcaddon building

    Assembly execution helpers (enhanced manifests, blocks/items, entities,
    packaging, validation) are delegated to assembler.py; typed tool
    wrappers are attached to this class by tools.py at import time.
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

    # ─────────────────────────────────────────────────────────────────────
    # Instance delegation methods — thin wrappers over the packaging submodules
    # ─────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────
    # Static tool-execution entry points.
    # Simple delegation wrappers live here; assembly-heavy wrappers delegate
    # to assembler.py (lazy import to avoid circular dependency at import time).
    # ─────────────────────────────────────────────────────────────────────

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
        """Generate enhanced Bedrock manifests (delegates to assembler)."""
        from .assembler import generate_enhanced_manifests

        return generate_enhanced_manifests(mod_data)

    @staticmethod
    def _generate_blocks_and_items(conversion_data: str) -> str:
        """Generate Bedrock blocks and items (delegates to assembler)."""
        from .assembler import generate_blocks_and_items

        return generate_blocks_and_items(conversion_data)

    @staticmethod
    def _generate_entities(entity_data: str) -> str:
        """Generate Bedrock entities (delegates to assembler)."""
        from .assembler import generate_entities

        return generate_entities(entity_data)

    @staticmethod
    def _package_enhanced_addon(package_data: str) -> str:
        """Package addon via the enhanced file packager (delegates to assembler)."""
        from .assembler import package_enhanced_addon

        return package_enhanced_addon(package_data)

    @staticmethod
    def _validate_enhanced_addon(addon_path: str) -> str:
        """Validate addon via the enhanced validator (delegates to assembler)."""
        from .assembler import validate_enhanced_addon

        return validate_enhanced_addon(addon_path)

    @staticmethod
    def _validate_mcaddon_structure(mcaddon_path: str) -> str:
        """Validate .mcaddon structure (delegates to assembler)."""
        from .assembler import validate_mcaddon_structure

        return validate_mcaddon_structure(mcaddon_path)

    @staticmethod
    def _validate_manifest_schema(manifest_data: str) -> str:
        """Validate a manifest.json against schema (delegates to assembler)."""
        from .assembler import validate_manifest_schema

        return validate_manifest_schema(manifest_data)

    @staticmethod
    def _generate_validation_report(mcaddon_path: str) -> str:
        """Generate a human-readable validation report (delegates to assembler)."""
        from .assembler import generate_validation_report

        return generate_validation_report(mcaddon_path)
