"""
Packaging subpackage for Bedrock addon packaging and validation.

Split from packaging_agent.py (42K) and packaging_validator.py (31K) per issue #1278.
Public API remains unchanged - callers import from agents.packaging.

Module structure:
- agent.py: PackagingAgent coordinator
- manifest_builder.py: Manifest assembly
- zip_assembler.py: Zip construction
- resource_mapper.py: Resource mapping
- bundler.py: High-level bundling (delegates to zip_assembler)
- folder_builder.py: Folder structure (delegates to resource_mapper)
- manifest.py: Manifest generation (delegates to manifest_builder)
- validator.py: Package validation
- pack_report.py: Validation reporting
"""

from .agent import PackagingAgent
from .bundler import Bundler
from .folder_builder import FolderBuilder
from .manifest import ManifestGenerator
from .manifest_builder import ManifestBuilder
from .pack_report import generate_validation_report
from .resource_mapper import ResourceMapper
from .validator import (
    PackagingValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from .zip_assembler import ZipAssembler


class PackagingCoordinator:
    """
    Thin coordinator class that delegates to subpackage modules.
    Preserves the original PackagingAgent interface for backwards compatibility.
    """

    _instance = None

    def __init__(self):
        from agents.addon_validator import AddonValidator
        from agents.block_item_generator import BlockItemGenerator
        from agents.entity_converter import EntityConverter
        from agents.file_packager import FilePackager
        from models.smart_assumptions import SmartAssumptionEngine

        self.smart_assumption_engine = SmartAssumptionEngine()
        self.manifest_generator = ManifestGenerator()
        self.folder_builder = FolderBuilder()
        self.bundler = Bundler()
        self.validator = PackagingValidator()
        self.addon_validator = AddonValidator()
        self.block_item_generator = BlockItemGenerator()
        self.entity_converter = EntityConverter()
        self.file_packager = FilePackager()

    @classmethod
    def get_instance(cls):
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self):
        """Get tools available to the packaging system."""
        return PackagingAgent.get_instance().get_tools()


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
