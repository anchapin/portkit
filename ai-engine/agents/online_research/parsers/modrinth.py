"""Modrinth pack format parser.

Parses Modrinth pack format files (``modrinth.index.json``) for modpack
conversion support. Consolidated onto :class:`..base.ModPortalParserBase` to
share JSON-loading and structural-validation mechanics with the CurseForge
parser (issue #1730). Behaviour and public API are unchanged.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ModPortalParserAgentBase, ModPortalParserBase

logger = logging.getLogger(__name__)


class ModrinthPackParser(ModPortalParserBase):
    """
    Parser for Modrinth pack format files.

    Handles parsing of modrinth.index.json files from Modrinth modpacks,
    extracting file information, dependencies, and environment requirements.
    """

    # Modrinth pack format versions (inherited SUPPORTED_VERSIONS via base)

    # Pack types
    PACK_TYPE_MODPACK = "modpack"
    PACK_TYPE_DATAPACK = "datapack"
    PACK_TYPE_RESOURCEPACK = "resourcepack"

    def __init__(self):
        self.pack_info: Optional[Dict[str, Any]] = None
        self.files: List[Dict[str, Any]] = []
        self.dependencies: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {}

    def parse_index(self, index_path: Path) -> Dict[str, Any]:
        """
        Parse a Modrinth modrinth.index.json file.

        Args:
            index_path: Path to the modrinth.index.json file

        Returns:
            Dictionary containing parsed pack data

        Raises:
            FileNotFoundError: If index file doesn't exist
            ValueError: If index format is invalid
        """
        self.pack_info = self.load_json_file(
            index_path,
            not_found_msg=f"Index file not found: {index_path}",
            invalid_msg="Invalid JSON in index",
        )

        # Validate index structure
        self._validate_index()

        # Extract data
        self._extract_metadata()
        self._extract_files()
        self._extract_dependencies()

        return self.get_parsed_data()

    def parse_from_string(self, index_content: str) -> Dict[str, Any]:
        """
        Parse a Modrinth index from a string.

        Args:
            index_content: JSON string content

        Returns:
            Dictionary containing parsed pack data
        """
        self.pack_info = self.load_json_string(
            index_content, invalid_msg="Invalid JSON in index content"
        )

        self._validate_index()
        self._extract_metadata()
        self._extract_files()
        self._extract_dependencies()

        return self.get_parsed_data()

    def _validate_index(self) -> None:
        """Validate the index structure."""
        self.require_non_empty(self.pack_info, empty_msg="Pack info is empty")

        # Check required fields
        self.require_fields(self.pack_info, ["format_version", "pack", "files"])

        # Check format version
        self.require_supported_version(
            self.pack_info.get("format_version"),
            unsupported_msg_template="Unsupported format version: {}",
        )

    def _extract_metadata(self) -> None:
        """Extract metadata from the pack info."""
        if not self.pack_info:
            return

        pack = self.pack_info.get("pack", {})

        self.metadata = {
            "name": pack.get("name", "Unnamed Pack"),
            "version": pack.get("version", "1.0.0"),
            "description": pack.get("description", ""),
            "format_version": self.pack_info.get("format_version", 1),
            "author": self.pack_info.get("author", {}).get("name", "Unknown")
            if isinstance(self.pack_info.get("author"), dict)
            else self.pack_info.get("author", "Unknown"),
            "pack_type": self._determine_pack_type(pack.get("name", "")),
        }

    def _determine_pack_type(self, name: str) -> str:
        """Determine the pack type from the name."""
        name_lower = name.lower()
        if "datapack" in name_lower:
            return self.PACK_TYPE_DATAPACK
        elif "resourcepack" in name_lower or "resource pack" in name_lower:
            return self.PACK_TYPE_RESOURCEPACK
        else:
            return self.PACK_TYPE_MODPACK

    def _extract_files(self) -> None:
        """Extract file information from the files array."""
        if not self.pack_info:
            return

        self.files = []
        files = self.pack_info.get("files", [])

        for file_entry in files:
            file_info = {
                "path": file_entry.get("path", ""),
                "hashes": file_entry.get("hashes", {}),
                "env": self._extract_environment(file_entry.get("env", {})),
                "download_url": file_entry.get("downloads", [None])[0]
                if file_entry.get("downloads")
                else None,
                "file_size": file_entry.get("fileSize", 0),
            }
            self.files.append(file_info)

    def _extract_environment(self, env: Dict[str, Any]) -> Dict[str, str]:
        """Extract environment requirements from a file entry."""
        if not env:
            return {"client": "optional", "server": "optional"}

        return {
            "client": env.get("client", "optional"),
            "server": env.get("server", "optional"),
        }

    def _extract_dependencies(self) -> None:
        """Extract dependencies from the index."""
        if not self.pack_info:
            return

        self.dependencies = {}
        deps = self.pack_info.get("dependencies", {})

        for key, value in deps.items():
            # Handle different dependency formats
            if isinstance(value, dict):
                self.dependencies[key] = value.get("version", "*")
            else:
                self.dependencies[key] = str(value)

    def get_parsed_data(self) -> Dict[str, Any]:
        """
        Get the complete parsed data.

        Returns:
            Dictionary containing all parsed pack data
        """
        return {
            "metadata": self.metadata,
            "files": self.files,
            "file_count": len(self.files),
            "dependencies": self.dependencies,
            "pack_type": self.metadata.get("pack_type", self.PACK_TYPE_MODPACK),
            "has_client_files": self._has_client_files(),
            "has_server_files": self._has_server_files(),
        }

    def _has_client_files(self) -> bool:
        """Check if pack has client-specific files."""
        for file in self.files:
            env = file.get("env", {})
            client_env = env.get("client", "optional")
            if client_env in ["required", "optional"]:
                return True
        return False

    def _has_server_files(self) -> bool:
        """Check if pack has server-specific files."""
        for file in self.files:
            env = file.get("env", {})
            server_env = env.get("server", "optional")
            if server_env in ["required", "optional"]:
                return True
        return False

    def get_client_files(self) -> List[Dict[str, Any]]:
        """Get files that require client environment."""
        return [f for f in self.files if f.get("env", {}).get("client") == "required"]

    def get_server_files(self) -> List[Dict[str, Any]]:
        """Get files that require server environment."""
        return [f for f in self.files if f.get("env", {}).get("server") == "required"]

    def get_files_by_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """Get files matching a path pattern."""
        regex = re.compile(pattern)
        return [f for f in self.files if regex.search(f.get("path", ""))]

    def get_dependency_versions(self) -> Dict[str, str]:
        """Get all dependencies with their versions."""
        return self.dependencies.copy()


class ModrinthParserAgent(ModPortalParserAgentBase):
    """
    LangChain agent runnable for parsing Modrinth pack format files.
    """

    #: Descriptor filename looked up inside a modpack directory.
    manifest_filename = "modrinth.index.json"
    #: Parser method invoked on :attr:`parser`.
    parse_method = "parse_index"

    def __init__(self):
        super().__init__()
        self.parser = ModrinthPackParser()
