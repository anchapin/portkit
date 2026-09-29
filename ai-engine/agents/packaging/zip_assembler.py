"""
Zip assembly logic for MCADDON archive creation.

This module handles the construction of .mcaddon zip archives.
Extracted from bundler.py per issue #1581/#1641.

Per issue #1278: Split packaging_agent.py (42K) + packaging_validator.py (31K) into packaging/ subpackage
"""

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ZipAssembler:
    """Handles zip archive construction for MCADDON files."""

    def __init__(self):
        self.package_constraints = {
            "max_total_size_mb": 500,
            "max_files": 1000,
            "required_files": ["manifest.json"],
            "forbidden_extensions": [".exe", ".dll", ".bat", ".sh"],
            "max_manifest_size_kb": 10,
        }

    def build_mcaddon(self, build_data: Any) -> str:
        """Build the final mcaddon package."""
        try:
            if isinstance(build_data, str):
                data = json.loads(build_data)
            else:
                data = build_data

            output_path = data.get("output_path")
            mod_name = data.get("mod_name", "converted_mod")
            source_directories = data.get("source_directories", [])
            behavior_pack_path = data.get("behavior_pack_path")
            resource_pack_path = data.get("resource_pack_path")

            if not output_path:
                raise ValueError("Missing required output_path for building .mcaddon")

            output_file = Path(output_path)
            if output_file.is_dir():
                output_path = os.path.join(output_path, f"{mod_name}.mcaddon")
            elif not str(output_path).endswith(".mcaddon") and not str(output_path).endswith(
                ".zip"
            ):
                if "/" in str(output_path) and not os.path.exists(os.path.dirname(output_path)):
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                if source_directories:
                    for source_dir in source_directories:
                        source_path = Path(source_dir)
                        if source_path.exists():
                            if (
                                source_path.name == "behavior_pack"
                                or (source_path / "manifest.json").exists()
                            ):
                                for root, _, files in os.walk(source_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        arcname = os.path.join(
                                            source_path.name,
                                            os.path.relpath(file_path, source_path),
                                        )
                                        zipf.write(file_path, arcname)
                            elif source_path.name == "resource_pack":
                                for root, _, files in os.walk(source_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        arcname = os.path.join(
                                            source_path.name,
                                            os.path.relpath(file_path, source_path),
                                        )
                                        zipf.write(file_path, arcname)

                if behavior_pack_path and os.path.exists(behavior_pack_path):
                    for root, _, files in os.walk(behavior_pack_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.join(
                                "behaviors", os.path.relpath(file_path, behavior_pack_path)
                            )
                            zipf.write(file_path, arcname)

                if resource_pack_path and os.path.exists(resource_pack_path):
                    for root, _, files in os.walk(resource_pack_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.join(
                                "resources", os.path.relpath(file_path, resource_pack_path)
                            )
                            zipf.write(file_path, arcname)

            post_validation = {"is_valid_zip": True, "file_count": 0, "contains_manifests": False}

            try:
                with zipfile.ZipFile(output_path, "r") as zf:
                    namelist = zf.namelist()
                    post_validation["file_count"] = len(namelist)
                    post_validation["contains_manifests"] = any(
                        "manifest.json" in name for name in namelist
                    )
            except Exception as e:
                post_validation["is_valid_zip"] = False
                post_validation["error"] = str(e)

            return json.dumps(
                {"success": True, "output_path": output_path, "post_validation": post_validation}
            )

        except Exception as e:
            logger.error(f"Build error: {e}")
            return json.dumps({"success": False, "error": f"Build failed: {str(e)}"})

    def build_mcaddon_mvp(
        self, temp_dir: str, output_path: str, mod_name: str = None
    ) -> Dict[str, Any]:
        """Build .mcaddon file from temp directory structure for MVP pipeline."""
        try:
            temp_path = Path(temp_dir)

            if not temp_path.exists():
                raise ValueError(f"Temp directory does not exist: {temp_dir}")

            behavior_pack_dir = temp_path / "behavior_pack"
            resource_pack_dir = temp_path / "resource_pack"

            if not behavior_pack_dir.is_dir() and not resource_pack_dir.is_dir():
                raise ValueError(
                    f"No behavior_pack or resource_pack directories found in {temp_dir}"
                )

            if behavior_pack_dir.exists() and not behavior_pack_dir.is_dir():
                raise ValueError(
                    f"behavior_pack exists but is not a directory: {behavior_pack_dir}"
                )

            if resource_pack_dir.exists() and not resource_pack_dir.is_dir():
                raise ValueError(
                    f"resource_pack exists but is not a directory: {resource_pack_dir}"
                )

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if output_file.is_dir() or output_path.endswith("/"):
                filename = f"{mod_name or 'converted_mod'}.mcaddon"
                output_file = output_file / filename

            with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                if behavior_pack_dir.exists():
                    pack_name = (
                        behavior_pack_dir.name
                        if behavior_pack_dir.name != "behavior_pack"
                        else f"{mod_name or 'converted_mod'}_bp"
                    )
                    for file_path in behavior_pack_dir.rglob("*"):
                        if file_path.is_file():
                            arcname = f"behavior_packs/{pack_name}/{file_path.relative_to(behavior_pack_dir)}"
                            zipf.write(file_path, arcname)

                if resource_pack_dir.exists():
                    pack_name = (
                        resource_pack_dir.name
                        if resource_pack_dir.name != "resource_pack"
                        else f"{mod_name or 'converted_mod'}_rp"
                    )
                    for file_path in resource_pack_dir.rglob("*"):
                        if file_path.is_file():
                            arcname = f"resource_packs/{pack_name}/{file_path.relative_to(resource_pack_dir)}"
                            zipf.write(file_path, arcname)

            validation_info = self._validate_mcaddon_file(output_file)

            return {
                "success": True,
                "output_path": str(output_file),
                "file_size": output_file.stat().st_size,
                "validation": validation_info,
            }

        except Exception as e:
            logger.error(f"MVP build error: {e}")
            return {"success": False, "error": str(e)}

    def _validate_mcaddon_file(self, mcaddon_path: Path) -> Dict[str, Any]:
        """Validate a created .mcaddon file."""
        validation = {
            "is_valid_zip": False,
            "file_count": 0,
            "has_behavior_pack": False,
            "has_resource_pack": False,
            "manifest_count": 0,
            "errors": [],
        }

        try:
            with zipfile.ZipFile(mcaddon_path, "r") as zipf:
                validation["is_valid_zip"] = True
                namelist = zipf.namelist()
                validation["file_count"] = len(namelist)

                validation["has_behavior_pack"] = any(
                    name.startswith("behavior_packs/") for name in namelist
                )
                validation["has_resource_pack"] = any(
                    name.startswith("resource_packs/") for name in namelist
                )

                has_legacy_bp = any(name.startswith("behavior_pack/") for name in namelist)
                has_legacy_rp = any(name.startswith("resource_pack/") for name in namelist)
                if has_legacy_bp or has_legacy_rp:
                    validation["errors"].append(
                        "Found legacy incorrect folder structure (behavior_pack/ or resource_pack/)"
                    )

                validation["manifest_count"] = sum(
                    1 for name in namelist if "manifest.json" in name
                )

                if validation["manifest_count"] == 0:
                    validation["errors"].append("No manifest.json files found")

                if not validation["has_behavior_pack"] and not validation["has_resource_pack"]:
                    validation["errors"].append(
                        "No behavior_packs/ or resource_packs/ found in correct Bedrock structure"
                    )

        except zipfile.BadZipFile as e:
            validation["errors"].append(f"Invalid ZIP file: {e}")
        except Exception as e:
            validation["errors"].append(f"Validation error: {e}")

        validation["is_valid"] = len(validation["errors"]) == 0
        return validation

    def get_package_constraints(self) -> Dict[str, Any]:
        """Get package constraints."""
        return self.package_constraints
