"""
Folder structure builder for Bedrock addon packages.

This module delegates to ResourceMapper for resource operations.
Extracted from the original folder_builder logic per issue #1581/#1642.

Per issue #1278: Split packaging_agent.py (42K) + packaging_validator.py (31K) into packaging/ subpackage
"""

import json
import logging
import os
from typing import Any

from .resource_mapper import ResourceMapper

logger = logging.getLogger(__name__)


class FolderBuilder:
    """Handles behaviors/resources/scripts folder structure assembly."""

    def __init__(self):
        self._resource_mapper = ResourceMapper()
        self.pack_structures = self._resource_mapper.pack_structures

    def create_package_structure(self, structure_data: Any) -> str:
        """Create package structure for Bedrock addon."""
        try:
            if isinstance(structure_data, str):
                try:
                    data = json.loads(structure_data)
                except json.JSONDecodeError:
                    return json.dumps(
                        {"success": False, "error": "Invalid JSON input for structure_data"}
                    )
            else:
                data = structure_data

            output_dir = data.get("output_dir")
            mod_name = data.get("mod_name", "converted_mod")

            if not output_dir:
                raise ValueError("output_dir is required for creating package structure")

            behavior_pack_path = os.path.join(output_dir, f"{mod_name}_BP")
            resource_pack_path = os.path.join(output_dir, f"{mod_name}_RP")

            os.makedirs(behavior_pack_path, exist_ok=True)
            os.makedirs(resource_pack_path, exist_ok=True)

            os.makedirs(os.path.join(behavior_pack_path, "entities"), exist_ok=True)
            os.makedirs(os.path.join(behavior_pack_path, "scripts"), exist_ok=True)
            os.makedirs(os.path.join(resource_pack_path, "textures"), exist_ok=True)
            os.makedirs(os.path.join(resource_pack_path, "models"), exist_ok=True)

            return json.dumps(
                {
                    "success": True,
                    "behavior_pack_path": behavior_pack_path,
                    "resource_pack_path": resource_pack_path,
                    "message": "Package structure created successfully",
                }
            )

        except Exception as e:
            logger.error(f"Structure creation error: {e}")
            return json.dumps({"success": False, "error": f"Structure creation failed: {str(e)}"})

    def analyze_conversion_components(self, component_data: str) -> str:
        """Analyze conversion components for packaging."""
        return self._resource_mapper.analyze_conversion_components(component_data)

    def validate_package(self, validation_data: str) -> str:
        """Validate the package structure."""
        return self._resource_mapper.analyze_conversion_components(validation_data)

    def get_pack_structures(self) -> dict:
        """Get pack structure templates."""
        return self.pack_structures