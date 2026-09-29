"""Manifest Generator — Bedrock manifest.json structure generation.

Provides functions to generate valid Bedrock add-on manifests with proper
UUID generation, version parsing, and capability determination.

Issue #1613 — Extracted from bedrock_architect.py for single responsibility.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PackType(Enum):
    """Pack type enumeration for Bedrock add-ons."""

    BEHAVIOR = "behavior"
    RESOURCE = "resource"


@dataclass
class ModuleInfo:
    """Represents a manifest module entry."""

    module_type: str  # "data", "resources", "client_data", "javascript"
    uuid: str
    version: List[int]
    description: Optional[str] = None


@dataclass
class ManifestData:
    """Complete manifest structure holder."""

    name: str
    description: str
    version: List[int]
    uuid: str
    min_engine_version: List[int] = field(default_factory=lambda: [1, 21, 0])
    modules: List[ModuleInfo] = field(default_factory=list)
    capabilities: Optional[List[str]] = None
    dependencies: Optional[List[Dict[str, Any]]] = None


# Default manifest schema for validation
DEFAULT_MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["format_version", "header", "modules"],
    "properties": {
        "format_version": {"type": "integer", "minimum": 1, "maximum": 2},
        "header": {
            "type": "object",
            "required": ["name", "description", "uuid", "version"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 256},
                "description": {"type": "string", "maxLength": 512},
                "uuid": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                },
                "version": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "min_engine_version": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
        },
        "modules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type", "uuid", "version"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["data", "resources", "client_data", "javascript"],
                    },
                    "uuid": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    },
                    "version": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                },
            },
        },
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "dependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["uuid", "version"],
                "properties": {"uuid": {"type": "string"}, "version": {"type": "array"}},
            },
        },
    },
}


def generate_pack_uuid() -> str:
    """Generate a new random UUID for a pack."""
    return str(uuid.uuid4())


def parse_version_string(version_str: str) -> List[int]:
    """Parse version string into [major, minor, patch] format.

    Args:
        version_str: Version like "1.0.0", "2.1.3-beta", or [1, 2, 3].

    Returns:
        Three-element version list like [1, 0, 0].
    """
    try:
        if isinstance(version_str, list):
            return version_str[:3] + [0] * (3 - len(version_str))

        version_parts = str(version_str).split(".")
        version_ints = []

        for part in version_parts[:3]:
            numeric_part = "".join(c for c in part if c.isdigit())
            version_ints.append(int(numeric_part) if numeric_part else 0)

        while len(version_ints) < 3:
            version_ints.append(0)

        return version_ints

    except (ValueError, AttributeError):
        logger.warning(f"Could not parse version '{version_str}', using [1, 0, 0]")
        return [1, 0, 0]


def determine_capabilities(mod_data: Dict[str, Any]) -> List[str]:
    """Determine required Bedrock capabilities based on mod features.

    Args:
        mod_data: Dictionary containing mod features.

    Returns:
        List of capability strings like ["experimental_custom_ui"].
    """
    capabilities: List[str] = []
    features = mod_data.get("features", [])

    if any(f.get("type") == "custom_ui" for f in features):
        capabilities.append("experimental_custom_ui")

    if any(f.get("type") == "scripting" for f in features):
        capabilities.append("script_eval")

    if any(f.get("type") == "chemistry" for f in features):
        capabilities.append("chemistry")

    experimental_features = mod_data.get("experimental_features", [])
    if experimental_features:
        capabilities.extend(experimental_features)

    return list(set(capabilities))


def create_behavior_manifest(
    name: str,
    description: str,
    version: List[int],
    pack_uuid: str,
    capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create behavior pack manifest structure.

    Args:
        name: Pack name.
        description: Pack description.
        version: Version list like [1, 0, 0].
        pack_uuid: UUID for the pack.
        capabilities: Optional list of Bedrock capability strings.

    Returns:
        Complete behavior pack manifest dictionary.
    """
    modules = [{"type": "data", "uuid": str(uuid.uuid4()), "version": version}]

    # Add script module if needed
    if capabilities and any(
        cap in capabilities for cap in ["experimental_custom_ui", "script_eval"]
    ):
        modules.append(
            {
                "type": "javascript",
                "uuid": str(uuid.uuid4()),
                "version": version,
                "entry": "scripts/main.js",
            }
        )

    manifest: Dict[str, Any] = {
        "format_version": 2,
        "header": {
            "name": f"{name} BP",
            "description": f"{description} - Behavior Pack",
            "uuid": pack_uuid,
            "version": version,
            "min_engine_version": [1, 21, 0],
        },
        "modules": modules,
    }

    if capabilities:
        manifest["capabilities"] = capabilities

    return manifest


def create_resource_manifest(
    name: str,
    description: str,
    version: List[int],
    pack_uuid: str,
    capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create resource pack manifest structure.

    Args:
        name: Pack name.
        description: Pack description.
        version: Version list like [1, 0, 0].
        pack_uuid: UUID for the pack.
        capabilities: Optional list of Bedrock capability strings.

    Returns:
        Complete resource pack manifest dictionary.
    """
    modules = [{"type": "resources", "uuid": str(uuid.uuid4()), "version": version}]

    # Add client data module if needed for custom UI
    if capabilities and "experimental_custom_ui" in capabilities:
        modules.append({"type": "client_data", "uuid": str(uuid.uuid4()), "version": version})

    manifest: Dict[str, Any] = {
        "format_version": 2,
        "header": {
            "name": f"{name} RP",
            "description": f"{description} - Resource Pack",
            "uuid": pack_uuid,
            "version": version,
            "min_engine_version": [1, 21, 0],
        },
        "modules": modules,
    }

    if capabilities:
        manifest["capabilities"] = capabilities

    return manifest


def add_pack_dependency(
    manifest: Dict[str, Any], dep_uuid: str, dep_version: List[int]
) -> Dict[str, Any]:
    """Add a dependency to an existing manifest.

    Args:
        manifest: Manifest to add dependency to.
        dep_uuid: UUID of the pack to depend on.
        dep_version: Version of the dependency.

    Returns:
        Modified manifest with new dependency.
    """
    dependencies = manifest.get("dependencies", [])
    dependencies.append({"uuid": dep_uuid, "version": dep_version})
    manifest["dependencies"] = dependencies
    return manifest


def generate_manifests_pair(mod_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Generate both behavior pack and resource pack manifests together.

    Args:
        mod_data: Dictionary containing:
            - name: Mod name
            - description: Mod description
            - version: Version string or list

    Returns:
        Tuple of (behavior_manifest, resource_manifest).
    """
    mod_name = mod_data.get("name", "Converted Mod")
    mod_description = mod_data.get("description", "Converted from Java mod")
    mod_version = parse_version_string(mod_data.get("version", "1.0.0"))

    bp_uuid = generate_pack_uuid()
    rp_uuid = generate_pack_uuid()
    capabilities = determine_capabilities(mod_data)

    bp_manifest = create_behavior_manifest(
        mod_name, mod_description, mod_version, bp_uuid, capabilities
    )
    rp_manifest = create_resource_manifest(
        mod_name, mod_description, mod_version, rp_uuid, capabilities
    )

    # Add cross-dependencies
    bp_manifest = add_pack_dependency(bp_manifest, rp_uuid, mod_version)
    rp_manifest = add_pack_dependency(rp_manifest, bp_uuid, mod_version)

    logger.info(f"Generated manifests for mod: {mod_name}")
    return bp_manifest, rp_manifest


def write_manifest_to_file(manifest: Dict[str, Any], output_path: Path) -> Path:
    """Write a manifest dictionary to a JSON file.

    Args:
        manifest: Manifest dictionary to write.
        output_path: Target file path.

    Returns:
        The path that was written to.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.debug(f"Wrote manifest to {output_path}")
    return output_path


def validate_manifest(manifest: Dict[str, Any], pack_type: str) -> None:
    """Validate a manifest against the Bedrock schema.

    Args:
        manifest: Manifest dictionary to validate.
        pack_type: Type of pack ("behavior" or "resource") for error messages.

    Raises:
        ValueError: If validation fails.
    """
    try:
        import jsonschema

        jsonschema.validate(manifest, DEFAULT_MANIFEST_SCHEMA)
        logger.debug(f"Manifest validation passed for {pack_type} pack")
    except ImportError:
        logger.warning("jsonschema not installed — skipping validation")
    except Exception as e:
        logger.error(f"Manifest validation failed for {pack_type} pack: {e}")
        raise ValueError(f"Invalid {pack_type} pack manifest: {e}")


class BedrockManifestGenerator:
    """High-level manifest generation with full lifecycle support.

    Use this class when you need to generate multiple manifests with
    consistent configuration and validation.
    """

    def __init__(self, min_engine_version: Optional[List[int]] = None) -> None:
        """Initialize generator with optional engine version override.

        Args:
            min_engine_version: Override default [1, 21, 0] for min engine version.
        """
        self.min_engine_version = min_engine_version or [1, 21, 0]
        self.manifest_schema = DEFAULT_MANIFEST_SCHEMA

    def generate(self, mod_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Generate both BP and RP manifests for a mod.

        Args:
            mod_data: Mod information dictionary.

        Returns:
            Tuple of (behavior_manifest, resource_manifest).
        """
        return generate_manifests_pair(mod_data)

    def generate_single(self, pack_type: PackType, mod_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a single manifest for either BP or RP.

        Args:
            pack_type: Which pack type to generate.
            mod_data: Mod information dictionary.

        Returns:
            Generated manifest dictionary.
        """
        mod_name = mod_data.get("name", "Converted Mod")
        mod_description = mod_data.get("description", "Converted from Java mod")
        mod_version = parse_version_string(mod_data.get("version", "1.0.0"))
        pack_uuid = generate_pack_uuid()
        capabilities = determine_capabilities(mod_data)

        if pack_type == PackType.BEHAVIOR:
            manifest = create_behavior_manifest(
                mod_name, mod_description, mod_version, pack_uuid, capabilities
            )
        else:
            manifest = create_resource_manifest(
                mod_name, mod_description, mod_version, pack_uuid, capabilities
            )

        validate_manifest(manifest, pack_type.value)
        return manifest

    def write_to_disk(
        self,
        bp_manifest: Dict[str, Any],
        rp_manifest: Dict[str, Any],
        bp_path: Path,
        rp_path: Path,
    ) -> Tuple[Path, Path]:
        """Write both manifests to disk.

        Args:
            bp_manifest: Behavior pack manifest.
            rp_manifest: Resource pack manifest.
            bp_path: Behavior pack output path.
            rp_path: Resource pack output path.

        Returns:
            Tuple of (bp_path, rp_path) written.
        """
        write_manifest_to_file(bp_manifest, bp_path)
        write_manifest_to_file(rp_manifest, rp_path)
        logger.info(f"Wrote manifests to {bp_path} and {rp_path}")
        return bp_path, rp_path
