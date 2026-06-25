"""
Manifest building logic for Bedrock addon packages.

This module handles manifest.json generation and assembly.
Extracted from manifest.py per issue #1581/#1640.

Per issue #1278: Split packaging_agent.py (42K) + packaging_validator.py (31K) into packaging/ subpackage
"""

import copy
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


class ManifestBuilder:
    """Handles manifest.json and pack_icon generation."""

    def __init__(self):
        self.manifest_template = {
            "format_version": 2,
            "header": {
                "name": "",
                "description": "",
                "uuid": "",
                "version": [1, 0, 0],
                "min_engine_version": [1, 21, 0],
            },
            "modules": [],
        }

    def generate_manifest(self, mod_info: str, pack_type: str) -> str:
        """
        Generate manifest for a pack.

        Args:
            mod_info: JSON string containing mod information
            pack_type: Type of pack ("behavior", "resource", "both")

        Returns:
            JSON string with manifest data
        """
        try:
            info = json.loads(mod_info) if isinstance(mod_info, str) else mod_info

            manifest = copy.deepcopy(self.manifest_template)
            manifest["header"]["name"] = info.get("name", "Converted Mod")
            manifest["header"]["description"] = (
                f"Converted from {info.get('framework', 'Java')} mod"
            )
            manifest["header"]["uuid"] = str(uuid.uuid4())
            manifest["header"]["version"] = info.get("version", [1, 0, 0])

            if pack_type in ["behavior", "both"]:
                manifest["modules"].append(
                    {"type": "data", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}
                )

            if pack_type in ["resource", "both"]:
                manifest["modules"].append(
                    {"type": "resources", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}
                )

            return json.dumps(manifest)

        except Exception as e:
            logger.error(f"Error generating manifest: {e}")
            return json.dumps({"error": str(e), "success": False})

    def generate_manifests(self, manifest_data: str) -> str:
        """
        Generate manifests for packaging.

        Args:
            manifest_data: JSON string or dict containing manifest information

        Returns:
            JSON string with generation results
        """
        try:
            if isinstance(manifest_data, str):
                try:
                    data = json.loads(manifest_data)
                except json.JSONDecodeError:
                    return json.dumps({"success": False, "error": "Invalid JSON input"})
            else:
                data = (
                    manifest_data
                    if isinstance(manifest_data, dict)
                    else {"error": "Invalid input format"}
                )

            package_info = data.get("package_info", {})
            capabilities = data.get("capabilities", [])
            pack_types = data.get("pack_types", [])

            has_behavior_pack = "behavior_pack" in pack_types or package_info.get(
                "has_behavior_pack", False
            )
            has_resource_pack = "resource_pack" in pack_types or package_info.get(
                "has_resource_pack", False
            )

            mod_name = data.get("mod_name", package_info.get("name", "Converted Mod"))
            mod_description = data.get(
                "mod_description", package_info.get("description", "Converted from Java mod")
            )
            mod_version = data.get("mod_version", package_info.get("version", [1, 0, 0]))

            base_manifest = {
                "format_version": 2,
                "header": {
                    "name": mod_name,
                    "description": mod_description,
                    "uuid": str(uuid.uuid4()),
                    "version": mod_version,
                    "min_engine_version": [1, 21, 0],
                },
                "modules": [],
            }

            if capabilities:
                base_manifest["capabilities"] = capabilities

            result = {"success": True, "files_created": []}

            if has_behavior_pack:
                behavior_manifest = copy.deepcopy(base_manifest)
                behavior_manifest["header"]["name"] = f"{mod_name} Behavior Pack"
                behavior_manifest["modules"].append(
                    {"type": "data", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}
                )
                result["behavior_pack_manifest"] = behavior_manifest

            if has_resource_pack:
                resource_manifest = copy.deepcopy(base_manifest)
                resource_manifest["header"]["name"] = f"{mod_name} Resource Pack"
                resource_manifest["modules"].append(
                    {"type": "resources", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}
                )
                result["resource_pack_manifest"] = resource_manifest

            output_dir = package_info.get("output_directory", "")
            if output_dir:
                output_path = Path(output_dir)

                if has_behavior_pack and "behavior_pack_manifest" in result:
                    bp_dir = output_path / "behavior_pack"
                    bp_dir.mkdir(parents=True, exist_ok=True)

                    with open(bp_dir / "manifest.json", "w") as f:
                        json.dump(result["behavior_pack_manifest"], f, indent=2)

                    result["behavior_manifest_path"] = f"{output_dir}/behavior_pack/manifest.json"
                    result["files_created"].append(result["behavior_manifest_path"])

                if has_resource_pack and "resource_pack_manifest" in result:
                    rp_dir = output_path / "resource_pack"
                    rp_dir.mkdir(parents=True, exist_ok=True)

                    with open(rp_dir / "manifest.json", "w") as f:
                        json.dump(result["resource_pack_manifest"], f, indent=2)

                    result["resource_manifest_path"] = f"{output_dir}/resource_pack/manifest.json"
                    result["files_created"].append(result["resource_manifest_path"])

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error generating manifests: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def generate_enhanced_manifests(self, data: Dict[str, Any]) -> Tuple[Dict, Dict]:
        """
        Generate enhanced Bedrock manifests.

        Args:
            data: Dict containing mod data

        Returns:
            Tuple of (behavior_pack_manifest, resource_pack_manifest)
        """
        from agents.bedrock_manifest_generator import BedrockManifestGenerator

        generator = BedrockManifestGenerator()
        return generator.generate_manifests(data)
