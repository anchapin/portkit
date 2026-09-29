"""Manifest Generator — Bedrock definition file generation for the architect.

Seam: extracted ``_generate_placeholder_definition`` and the four thin
``_generate_<type>_definitions`` wrappers. The Bedrock manifest/definition
shape lives here; the agent class binds the wrapper methods onto itself for
backward-compat with the typed tool subclasses.

Issue #1707 — Extracted from bedrock_architect_original.py for subpackage layout.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def generate_placeholder_definition(component_data_str: str, component_type: str) -> str:
    """Generate a placeholder Bedrock definition JSON for the given component type.

    The four ``generate_<type>_definitions`` tool implementations previously
    inlined this function inside :class:`BedrockArchitectAgent`. It now lives
    here so the manifest-shape knowledge is co-located with future real
    definition generators.

    Args:
        component_data_str: JSON string with at least ``id`` (or ``identifier``)
            and ``name`` keys.
        component_type: One of ``"block"``, ``"item"``, ``"recipe"`` or
            ``"entity"`` — controls which ``minecraft:<type>`` wrapper and
            default components are emitted.

    Returns:
        JSON string with ``success``, ``component_type``, ``identifier`` and
        ``definition_json`` keys on success, or ``success: False`` with an
        ``error`` on JSON-decode or unexpected failure.
    """
    try:
        component_data = json.loads(component_data_str)
        identifier = component_data.get(
            "identifier", f"custom:{component_data.get('id', f'{component_type}_placeholder')}"
        )
        name = component_data.get("name", f"Custom {component_type.capitalize()}")

        # Basic placeholder structure common to many Bedrock definitions
        placeholder_definition: Dict[str, Any] = {
            "format_version": "1.20.0",  # Using a recent common version
            f"minecraft:{component_type}": {
                "description": {"identifier": identifier},
                "components": {
                    "minecraft:display_name": {  # Common component for user-visible name
                        "value": name
                    },
                    # Specific components would vary greatly depending on component_type
                    # Example: A block might have "minecraft:material_instances"
                    # An item might have "minecraft:icon"
                    # An entity might have "minecraft:collision_box"
                },
                "metadata_generated": {  # Custom section for our tool's info
                    "source_java_id": component_data.get("id", "unknown_java_id"),
                    "conversion_tool": "ModPorterAI_BedrockArchitect",
                    "conversion_notes": (
                        f"This is an AI-generated placeholder {component_type} "
                        "definition. Review and refine."
                    ),
                },
            },
        }

        # Add type-specific components if needed for a basic valid structure
        if component_type == "block":
            placeholder_definition[f"minecraft:{component_type}"]["components"][
                "minecraft:loot"
            ] = f"loot_tables/blocks/{component_data.get('id', 'placeholder_block')}.json"
            placeholder_definition[f"minecraft:{component_type}"]["components"][
                "minecraft:destructible_by_mining"
            ] = {"seconds_to_destroy": 1.0}
        elif component_type == "item":
            placeholder_definition[f"minecraft:{component_type}"]["components"][
                "minecraft:icon"
            ] = {"texture": component_data.get("id", "placeholder_item_icon")}
            placeholder_definition[f"minecraft:{component_type}"]["components"][
                "minecraft:max_stack_size"
            ] = 64
        elif component_type == "entity":
            placeholder_definition[f"minecraft:{component_type}"]["components"][
                "minecraft:type_family"
            ] = {"family": [component_type, "mob"]}
            placeholder_definition[f"minecraft:{component_type}"]["components"][
                "minecraft:health"
            ] = {"value": 20, "max": 20}

        logger.info(
            f"Generated placeholder {component_type} definition for identifier: {identifier}"
        )
        return json.dumps(
            {
                "success": True,
                "component_type": component_type,
                "identifier": identifier,
                "definition_json": placeholder_definition,
                "message": (
                    f"Placeholder {component_type} definition generated successfully "
                    f"for {identifier}."
                ),
            },
            indent=2,
        )

    except json.JSONDecodeError as e:
        logger.error(
            f"Invalid JSON input for placeholder {component_type} definition: "
            f"{str(e)} - Input: {component_data_str[:500]}...",
            exc_info=True,
        )  # Log part of the input
        return json.dumps(
            {
                "success": False,
                "error": f"Invalid JSON input for {component_type} definition: {str(e)}",
            },
            indent=2,
        )
    except Exception as e:
        logger.error(
            f"Error generating placeholder {component_type} definition: {e}", exc_info=True
        )
        return json.dumps(
            {
                "success": False,
                "error": (f"Failed to generate placeholder {component_type} definition: {str(e)}"),
            },
            indent=2,
        )


__all__ = [
    "generate_placeholder_definition",
]
