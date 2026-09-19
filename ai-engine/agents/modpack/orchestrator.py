"""
Modpack Orchestrator for modpack conversion support.

Coordinates parsing of CurseForge/Modrinth modpacks, dependency analysis,
conflict detection, and load order calculation for complete modpack conversion.

Issues: #496, #497, #498, #499 - Modpack Support (Phase 5a-d)
Parent Issue: #478 - Implement Modpack Support (Phase 5)

Moved into agents/modpack/ subpackage per issue #1729.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .conflict_detector import ConflictDetectionResult, modpack_conflict_detector
from ..curseforge_parser import CurseForgeManifestParser, CurseForgeParserAgent
from ..mod_dependency_analyzer import DependencyAnalysisResult, mod_dependency_analyzer
from ..modrinth_parser import ModrinthPackParser, ModrinthParserAgent

logger = logging.getLogger(__name__)


class PackFormat(Enum):
    """Supported modpack formats."""

    CURSEFORGE = "curseforge"
    MODRINTH = "modrinth"
    UNKNOWN = "unknown"


@dataclass
class ModpackInfo:
    """Information about a modpack."""

    name: str
    version: str
    author: str
    description: str
    format: PackFormat
    minecraft_version: str
    mod_count: int
    mods: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ModpackAnalysisResult:
    """Complete analysis result for a modpack."""

    success: bool = False
    error_message: Optional[str] = None

    modpack_info: Optional[ModpackInfo] = None

    # Dependency analysis
    dependency_result: Optional[DependencyAnalysisResult] = None

    # Conflict detection
    conflict_result: Optional[ConflictDetectionResult] = None

    # Final recommendations
    recommended_load_order: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    # Files to convert
    mods_to_convert: List[Dict[str, Any]] = field(default_factory=list)
    mods_to_exclude: List[Dict[str, Any]] = field(default_factory=list)


class ModpackOrchestrator:
    """
    Orchestrates the complete modpack conversion workflow.

    Handles:
    1. Parsing CurseForge and Modrinth modpack manifests
    2. Analyzing mod dependencies
    3. Detecting conflicts (API, namespace, version)
    4. Calculating optimal load order
    5. Generating conversion recommendations
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Initialize parsers
        self.curseforge_parser = CurseForgeManifestParser()
        self.curseforge_agent = CurseForgeParserAgent()
        self.modrinth_parser = ModrinthPackParser()
        self.modrinth_agent = ModrinthParserAgent()

        # Initialize analyzers
        self.dependency_analyzer = mod_dependency_analyzer
        self.conflict_detector = modpack_conflict_detector

    def detect_format(self, pack_path: Path) -> PackFormat:
        """
        Detect the modpack format from directory contents.

        Args:
            pack_path: Path to the modpack directory or file

        Returns:
            Detected PackFormat
        """
        # Check for CurseForge manifest.json
        if (pack_path / "manifest.json").exists():
            return PackFormat.CURSEFORGE

        # Check for Modrinth modrinth.index.json
        if (pack_path / "modrinth.index.json").exists():
            return PackFormat.MODRINTH

        # Check for zip file contents
        if pack_path.suffix.lower() in [".zip", ".cfzip", ".mrpack"]:
            import zipfile

            try:
                with zipfile.ZipFile(pack_path, "r") as zf:
                    names = zf.namelist()
                    if "manifest.json" in names:
                        return PackFormat.CURSEFORGE
                    elif "modrinth.index.json" in names:
                        return PackFormat.MODRINTH
            except Exception as e:
                self.logger.warning(f"Could not read zip file: {e}")

        return PackFormat.UNKNOWN

    def parse_modpack(
        self, pack_path: Union[Path, str], format: Optional[PackFormat] = None
    ) -> Dict[str, Any]:
        """
        Parse a modpack and extract all information.

        Args:
            pack_path: Path to the modpack directory or zip file
            format: Optional format hint (auto-detected if not provided)

        Returns:
            Parsed modpack data
        """
        pack_path = Path(pack_path)

        # Detect format if not provided
        if format is None:
            format = self.detect_format(pack_path)

        if format == PackFormat.CURSEFORGE:
            return self._parse_curseforge(pack_path)
        elif format == PackFormat.MODRINTH:
            return self._parse_modrinth(pack_path)
        else:
            raise ValueError(f"Unknown modpack format for: {pack_path}")

    def _parse_curseforge(self, pack_path: Path) -> Dict[str, Any]:
        """Parse a CurseForge modpack."""
        manifest_path = pack_path / "manifest.json"

        if not manifest_path.exists():
            # Check if it's a zip file
            if pack_path.suffix.lower() == ".zip":
                import zipfile

                with zipfile.ZipFile(pack_path, "r") as zf:
                    # Extract to temp location
                    import tempfile

                    with tempfile.TemporaryDirectory() as tmpdir:
                        zf.extractall(tmpdir)
                        manifest_path = Path(tmpdir) / "manifest.json"
                        return self.curseforge_parser.parse_manifest(manifest_path)
            raise FileNotFoundError(f"manifest.json not found in {pack_path}")

        return self.curseforge_parser.parse_manifest(manifest_path)

    def _parse_modrinth(self, pack_path: Path) -> Dict[str, Any]:
        """Parse a Modrinth modpack."""
        index_path = pack_path / "modrinth.index.json"

        if not index_path.exists():
            # Check if it's a zip/mrpack file
            if pack_path.suffix.lower() in [".zip", ".mrpack"]:
                import zipfile

                with zipfile.ZipFile(pack_path, "r") as zf:
                    import tempfile

                    with tempfile.TemporaryDirectory() as tmpdir:
                        zf.extractall(tmpdir)
                        index_path = Path(tmpdir) / "modrinth.index.json"
                        return self.modrinth_parser.parse_index(index_path)
            raise FileNotFoundError(f"modrinth.index.json not found in {pack_path}")

        return self.modrinth_parser.parse_index(index_path)

    def analyze_modpack(
        self, pack_path: Union[Path, str], format: Optional[PackFormat] = None
    ) -> ModpackAnalysisResult:
        """
        Perform complete analysis of a modpack.

        This is the main entry point for analyzing a modpack.
        It parses the manifest, analyzes dependencies, detects conflicts,
        and generates recommendations.

        Args:
            pack_path: Path to the modpack directory or zip file
            format: Optional format hint

        Returns:
            ModpackAnalysisResult with complete analysis
        """
        result = ModpackAnalysisResult()

        try:
            # Detect and parse the modpack
            if format is None:
                format = self.detect_format(Path(pack_path))

            if format == PackFormat.UNKNOWN:
                result.error_message = "Could not detect modpack format"
                return result

            # Parse the modpack
            parsed = self.parse_modpack(pack_path, format)

            # Extract modpack info
            metadata = parsed.get("metadata", {})
            mods = parsed.get("mods", parsed.get("files", []))

            result.modpack_info = ModpackInfo(
                name=metadata.get("name", "Unknown"),
                version=metadata.get("version", "1.0.0"),
                author=metadata.get("author", "Unknown"),
                description=metadata.get("description", ""),
                format=format,
                minecraft_version=metadata.get("minecraft_version", ""),
                mod_count=len(mods),
                mods=mods,
            )

            # Analyze dependencies
            self.logger.info(f"Analyzing dependencies for {len(mods)} mods...")
            dependency_result = self.dependency_analyzer.analyze_from_manifest(
                manifest_data=parsed, source=format.value
            )
            result.dependency_result = dependency_result

            # Detect conflicts
            self.logger.info("Detecting conflicts...")
            conflict_result = self.conflict_detector.detect_conflicts(
                mods=mods,
                dependency_graph={
                    mod["project_id"]: [d["project_id"] for d in mod.get("dependencies", [])]
                    for mod in mods
                    if "project_id" in mod
                }
                if format == PackFormat.CURSEFORGE
                else None,
            )
            result.conflict_result = conflict_result

            # Build final load order and recommendations
            self._build_recommendations(result, dependency_result, conflict_result)

            result.success = True
            return result

        except Exception as e:
            self.logger.error(f"Error analyzing modpack: {e}")
            result.error_message = str(e)
            return result

    def _build_recommendations(
        self,
        result: ModpackAnalysisResult,
        dependency_result: DependencyAnalysisResult,
        conflict_result: ConflictDetectionResult,
    ) -> None:
        """Build final recommendations from analysis results."""
        # Combine warnings
        result.warnings.extend(dependency_result.warnings)

        # Check for critical conflicts
        if conflict_result.critical_count > 0:
            result.warnings.append(
                f"CRITICAL: {conflict_result.critical_count} critical conflict(s) detected"
            )

        # Build recommended load order
        load_order = []

        # Start with dependency-based order
        dep_order = dependency_result.recommended_load_order

        # Add mods from conflict detection load order
        conflict_order = conflict_result.load_order

        # Merge orders (dependency order takes precedence)
        seen = set()
        for mod_id in dep_order:
            if mod_id not in seen:
                mod = dependency_result.graph.mods.get(mod_id)
                if mod:
                    load_order.append(
                        {
                            "id": mod_id,
                            "name": mod.name,
                            "version": mod.version,
                            "reason": "Dependency requirement",
                        }
                    )
                    seen.add(mod_id)

        # Add any mods from conflict order not already included
        for entry in conflict_order:
            if entry.mod_id not in seen:
                load_order.append(
                    {
                        "id": entry.mod_id,
                        "name": entry.mod_name,
                        "version": None,
                        "reason": entry.reason,
                    }
                )
                seen.add(entry.mod_id)

        result.recommended_load_order = load_order

        # Determine which mods to convert and exclude
        if conflict_result.conflicts:
            excluded_ids = set()
            for conflict in conflict_result.conflicts:
                if conflict.severity in ["critical", "error"]:
                    # Exclude conflicting mods
                    for mod_name in conflict.mods_involved[1:]:
                        excluded_ids.add(mod_name)

            for mod in result.modpack_info.mods:
                mod_name = mod.get("name", "")
                if mod_name in excluded_ids:
                    result.mods_to_exclude.append(mod)
                else:
                    result.mods_to_convert.append(mod)
        else:
            result.mods_to_convert = result.modpack_info.mods

        # Generate recommendations
        result.recommendations = conflict_result.recommendations

        # Add dependency warnings
        if dependency_result.missing_dependencies:
            result.recommendations.append(
                f"Warning: {len(dependency_result.missing_dependencies)} required dependencies not found in modpack"
            )

    def generate_report(self, result: ModpackAnalysisResult) -> Dict[str, Any]:
        """
        Generate a human-readable report of the modpack analysis.

        Args:
            result: The analysis result

        Returns:
            Dictionary containing the report
        """
        report = {"success": result.success, "error": result.error_message}

        if not result.success:
            return report

        # Modpack info
        if result.modpack_info:
            report["modpack"] = {
                "name": result.modpack_info.name,
                "version": result.modpack_info.version,
                "author": result.modpack_info.author,
                "format": result.modpack_info.format.value,
                "minecraft_version": result.modpack_info.minecraft_version,
                "mod_count": result.modpack_info.mod_count,
            }

        # Warnings
        report["warnings"] = result.warnings

        # Recommendations
        report["recommendations"] = result.recommendations

        # Load order
        report["load_order"] = result.recommended_load_order

        # Conversion lists
        report["conversion"] = {
            "to_convert": len(result.mods_to_convert),
            "to_exclude": len(result.mods_to_exclude),
        }

        # Detailed dependency analysis
        if result.dependency_result:
            dep_report = self.dependency_analyzer.generate_report(result.dependency_result)
            report["dependencies"] = dep_report

        # Detailed conflict analysis
        if result.conflict_result:
            conflict_report = self.conflict_detector.generate_conflict_report(
                result.conflict_result
            )
            report["conflicts"] = conflict_report

        return report


# Singleton instance
modpack_orchestrator = ModpackOrchestrator()


class ModpackConversionCrew:
    """
    LangChain agent runnable crew for modpack conversion.

    Coordinates all agents needed for complete modpack conversion.
    """

    def __init__(self):
        self.orchestrator = modpack_orchestrator
        self.tools = []

    def get_tools(self):
        """Get the tools for this crew."""
        return self.tools

    def process_modpack(
        self, pack_path: Union[Path, str], format: Optional[PackFormat] = None
    ) -> ModpackAnalysisResult:
        """
        Process a modpack for conversion.

        Args:
            pack_path: Path to the modpack
            format: Optional format hint

        Returns:
            Complete analysis result
        """
        return self.orchestrator.analyze_modpack(pack_path, format)

    def generate_report(self, result: ModpackAnalysisResult) -> Dict[str, Any]:
        """
        Generate a conversion report.

        Args:
            result: The analysis result

        Returns:
            Report dictionary
        """
        return self.orchestrator.generate_report(result)
