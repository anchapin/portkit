"""CurseForge modpack manifest parser.

Parses CurseForge modpack ``manifest.json`` files for modpack conversion
support. Consolidated onto :class:`..base.ModPortalParserBase` to share
JSON-loading and structural-validation mechanics with the Modrinth parser
(issue #1730). Behaviour and public API are unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ModPortalParserAgentBase, ModPortalParserBase

logger = logging.getLogger(__name__)


class CurseForgeManifestParser(ModPortalParserBase):
    """
    Parser for CurseForge modpack manifest files.

    Handles parsing of manifest.json files from CurseForge modpacks,
    extracting mod information, dependencies, and metadata.
    """

    # CurseForge manifest version constants (inherited SUPPORTED_VERSIONS via base)

    def __init__(self):
        self.manifest: Optional[Dict[str, Any]] = None
        self.mods: List[Dict[str, Any]] = []
        self.overrides: List[str] = []
        self.metadata: Dict[str, Any] = {}

    def parse_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        """
        Parse a CurseForge manifest.json file.

        Args:
            manifest_path: Path to the manifest.json file

        Returns:
            Dictionary containing parsed manifest data

        Raises:
            FileNotFoundError: If manifest file doesn't exist
            ValueError: If manifest format is invalid
        """
        self.manifest = self.load_json_file(
            manifest_path,
            not_found_msg=f"Manifest file not found: {manifest_path}",
            invalid_msg="Invalid JSON in manifest",
        )

        # Validate manifest structure
        self._validate_manifest()

        # Extract data
        self._extract_metadata()
        self._extract_mods()
        self._extract_overrides()

        return self.get_parsed_data()

    def parse_from_string(self, manifest_content: str) -> Dict[str, Any]:
        """
        Parse a CurseForge manifest from a string.

        Args:
            manifest_content: JSON string content

        Returns:
            Dictionary containing parsed manifest data
        """
        self.manifest = self.load_json_string(
            manifest_content, invalid_msg="Invalid JSON in manifest content"
        )

        self._validate_manifest()
        self._extract_metadata()
        self._extract_mods()
        self._extract_overrides()

        return self.get_parsed_data()

    def _validate_manifest(self) -> None:
        """Validate the manifest structure."""
        self.require_non_empty(self.manifest, empty_msg="Manifest is empty")

        # Check required fields
        self.require_fields(self.manifest, ["manifestType"])

        if self.manifest.get("manifestType") != "minecraftModpack":
            raise ValueError(f"Unsupported manifest type: {self.manifest.get('manifestType')}")

        # Check manifest version
        self.require_supported_version(
            self.manifest.get("manifestVersion", 1),
            unsupported_msg_template="Unsupported manifest version: {}",
        )

        # Check for mods array
        self.require_fields(self.manifest, ["files"])

    def _extract_metadata(self) -> None:
        """Extract metadata from the manifest."""
        if not self.manifest:
            return

        self.metadata = {
            "name": self.manifest.get("name", "Unnamed Modpack"),
            "version": self.manifest.get("version", "1.0.0"),
            "author": self.manifest.get("author", "Unknown"),
            "description": self.manifest.get("description", ""),
            "manifest_version": self.manifest.get("manifestVersion", 1),
            "minecraft_version": self.manifest.get("minecraft", {}).get("version", ""),
            "modloader": self.manifest.get("minecraft", {}).get("modLoaders", []),
            "manifest_type": self.manifest.get("manifestType", ""),
        }

        # Extract overrides path
        overrides_path = self.manifest.get("overrides", "")
        if overrides_path:
            self.metadata["overrides_path"] = overrides_path

    def _extract_mods(self) -> None:
        """Extract mod information from the files array."""
        if not self.manifest:
            return

        self.mods = []
        files = self.manifest.get("files", [])

        for file_entry in files:
            mod_info = {
                "project_id": file_entry.get("projectID"),
                "file_id": file_entry.get("fileID"),
                "name": file_entry.get("name", ""),
                "version": file_entry.get("version", ""),
                "filename": file_entry.get("filename", ""),
                "path": file_entry.get("path", ""),
                "dependencies": self._extract_dependencies(file_entry),
                "required": file_entry.get("required", True),
            }
            self.mods.append(mod_info)

    def _extract_dependencies(self, file_entry: Dict[str, Any]) -> List[Dict[str, int]]:
        """Extract dependency information from a file entry."""
        dependencies = file_entry.get("dependencies", [])
        return [
            {"project_id": dep.get("projectID"), "file_id": dep.get("fileID")}
            for dep in dependencies
            if isinstance(dep, dict)
        ]

    def _extract_overrides(self) -> None:
        """Extract overrides list from manifest."""
        if not self.manifest:
            return

        overrides_path = self.manifest.get("overrides", "")
        self.overrides = (
            self.manifest.get("overrides", [])
            if isinstance(self.manifest.get("overrides"), list)
            else []
        )

        if overrides_path:
            self.metadata["overrides_path"] = overrides_path

    def get_parsed_data(self) -> Dict[str, Any]:
        """
        Get the complete parsed data.

        Returns:
            Dictionary containing all parsed manifest data
        """
        return {
            "metadata": self.metadata,
            "mods": self.mods,
            "mod_count": len(self.mods),
            "overrides": self.overrides,
            "is_server_modpack": self._is_server_modpack(),
            "is_client_modpack": self._is_client_modpack(),
        }

    def _is_server_modpack(self) -> bool:
        """Check if this is a server modpack."""
        if not self.manifest:
            return False

        # Check for server overrides directory
        return "server" in str(self.manifest.get("overrides", "")).lower()

    def _is_client_modpack(self) -> bool:
        """Check if this is a client modpack."""
        if not self.manifest:
            return False

        # Check for client overrides directory
        return "client" in str(self.manifest.get("overrides", "")).lower()

    def get_mod_by_project_id(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get mod information by project ID."""
        for mod in self.mods:
            if mod.get("project_id") == project_id:
                return mod
        return None

    def get_mod_dependencies(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all dependencies for a specific mod."""
        mod = self.get_mod_by_project_id(project_id)
        if mod:
            return mod.get("dependencies", [])
        return []

    def get_required_mods(self) -> List[Dict[str, Any]]:
        """Get all required mods."""
        return [mod for mod in self.mods if mod.get("required", True)]

    def get_optional_mods(self) -> List[Dict[str, Any]]:
        """Get all optional mods."""
        return [mod for mod in self.mods if not mod.get("required", True)]


class CurseForgeParserAgent(ModPortalParserAgentBase):
    """
    LangChain agent runnable for parsing CurseForge modpack manifests.
    """

    #: Descriptor filename looked up inside a modpack directory.
    manifest_filename = "manifest.json"
    #: Parser method invoked on :attr:`parser`.
    parse_method = "parse_manifest"

    def __init__(self):
        super().__init__()
        self.parser = CurseForgeManifestParser()
