"""Behavior Planner — Bedrock block/entity/item/recipe behavior file generation.

Provides functions for generating Bedrock behavior pack definitions for blocks,
entities, items, and recipes based on Java mod feature analysis.

Issue #1619 — Extracted from bedrock_architect.py for single responsibility.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ComponentType(Enum):
    """Type of Bedrock component being generated."""

    BLOCK = "block"
    ITEM = "item"
    ENTITY = "entity"
    RECIPE = "recipe"


@dataclass
class DefinitionOptions:
    """Options for generating Bedrock component definitions."""

    format_version: str = "1.20.0"
    identifier: Optional[str] = None
    name: Optional[str] = None
    source_java_id: Optional[str] = None
    extra_components: Optional[Dict[str, Any]] = None


# Block-specific component defaults
BLOCK_DEFAULT_COMPONENTS = {
    "minecraft:destructible_by_mining": {"seconds_to_destroy": 1.0},
    "minecraft:loot": "loot_tables/blocks/{id}.json",
}

# Item-specific component defaults
ITEM_DEFAULT_COMPONENTS = {
    "minecraft:icon": {"texture": "{id}"},
    "minecraft:max_stack_size": 64,
}

# Entity-specific component defaults
ENTITY_DEFAULT_COMPONENTS = {
    "minecraft:type_family": {"family": ["entity", "mob"]},
    "minecraft:health": {"value": 20, "max": 20},
}


def _build_description(component_type: ComponentType, identifier: str) -> Dict[str, Any]:
    """Build the description section for a component."""
    return {"identifier": identifier}


def _build_components(
    component_type: ComponentType,
    identifier: str,
    options: DefinitionOptions,
) -> Dict[str, Any]:
    """Build the components section based on type."""
    components: Dict[str, Any] = {}

    if component_type == ComponentType.BLOCK:
        components["minecraft:display_name"] = {"value": options.name or identifier}
        for key, val_template in BLOCK_DEFAULT_COMPONENTS.items():
            if isinstance(val_template, str):
                components[key] = val_template.replace("{id}", identifier.split(":")[-1])
            else:
                components[key] = val_template

    elif component_type == ComponentType.ITEM:
        components["minecraft:display_name"] = {"value": options.name or identifier}
        icon_texture = identifier.split(":")[-1] if ":" in identifier else identifier
        components["minecraft:icon"] = {"texture": options.identifier or icon_texture}
        components["minecraft:max_stack_size"] = 64

    elif component_type == ComponentType.ENTITY:
        components["minecraft:display_name"] = {"value": options.name or identifier}
        family_name = identifier.split(":")[-1] if ":" in identifier else identifier
        components["minecraft:type_family"] = {"family": [component_type.value, family_name]}
        components["minecraft:health"] = {"value": 20, "max": 20}

    elif component_type == ComponentType.RECIPE:
        components["minecraft:display_name"] = {"value": options.name or identifier}

    # Merge extra components
    if options.extra_components:
        components.update(options.extra_components)

    return components


def _build_metadata(options: DefinitionOptions, component_type: ComponentType) -> Dict[str, Any]:
    """Build custom metadata section for tracking conversion info."""
    return {
        "source_java_id": options.source_java_id or "unknown_java_id",
        "conversion_tool": "ModPorterAI_BedrockArchitect",
        "conversion_notes": (
            f"This is an AI-generated placeholder {component_type.value} "
            "definition. Review and refine."
        ),
    }


def generate_block_definition(
    block_data: Dict[str, Any], options: Optional[DefinitionOptions] = None
) -> Dict[str, Any]:
    """Generate a Bedrock block definition.

    Args:
        block_data: Dictionary with block information (id, name, etc.).
        options: Optional DefinitionOptions for customization.

    Returns:
        Complete Bedrock block definition dictionary.
    """
    if options is None:
        options = DefinitionOptions()

    options.identifier = options.identifier or block_data.get(
        "identifier", f"custom:{block_data.get('id', 'block_placeholder')}"
    )
    options.name = options.name or block_data.get("name", "Custom Block")
    options.source_java_id = options.source_java_id or block_data.get("id", "unknown_java_id")

    identifier = options.identifier

    definition: Dict[str, Any] = {
        "format_version": options.format_version,
        f"minecraft:{ComponentType.BLOCK.value}": {
            "description": _build_description(ComponentType.BLOCK, identifier),
            "components": _build_components(ComponentType.BLOCK, identifier, options),
            "metadata_generated": _build_metadata(options, ComponentType.BLOCK),
        },
    }

    logger.info(f"Generated block definition for identifier: {identifier}")
    return definition


def generate_item_definition(
    item_data: Dict[str, Any], options: Optional[DefinitionOptions] = None
) -> Dict[str, Any]:
    """Generate a Bedrock item definition.

    Args:
        item_data: Dictionary with item information (id, name, etc.).
        options: Optional DefinitionOptions for customization.

    Returns:
        Complete Bedrock item definition dictionary.
    """
    if options is None:
        options = DefinitionOptions()

    options.identifier = options.identifier or item_data.get(
        "identifier", f"custom:{item_data.get('id', 'item_placeholder')}"
    )
    options.name = options.name or item_data.get("name", "Custom Item")
    options.source_java_id = options.source_java_id or item_data.get("id", "unknown_java_id")

    identifier = options.identifier

    definition: Dict[str, Any] = {
        "format_version": options.format_version,
        f"minecraft:{ComponentType.ITEM.value}": {
            "description": _build_description(ComponentType.ITEM, identifier),
            "components": _build_components(ComponentType.ITEM, identifier, options),
            "metadata_generated": _build_metadata(options, ComponentType.ITEM),
        },
    }

    logger.info(f"Generated item definition for identifier: {identifier}")
    return definition


def generate_entity_definition(
    entity_data: Dict[str, Any], options: Optional[DefinitionOptions] = None
) -> Dict[str, Any]:
    """Generate a Bedrock entity definition.

    Args:
        entity_data: Dictionary with entity information (id, name, etc.).
        options: Optional DefinitionOptions for customization.

    Returns:
        Complete Bedrock entity definition dictionary.
    """
    if options is None:
        options = DefinitionOptions()

    options.identifier = options.identifier or entity_data.get(
        "identifier", f"custom:{entity_data.get('id', 'entity_placeholder')}"
    )
    options.name = options.name or entity_data.get("name", "Custom Entity")
    options.source_java_id = options.source_java_id or entity_data.get("id", "unknown_java_id")

    identifier = options.identifier

    definition: Dict[str, Any] = {
        "format_version": options.format_version,
        f"minecraft:{ComponentType.ENTITY.value}": {
            "description": _build_description(ComponentType.ENTITY, identifier),
            "components": _build_components(ComponentType.ENTITY, identifier, options),
            "metadata_generated": _build_metadata(options, ComponentType.ENTITY),
        },
    }

    logger.info(f"Generated entity definition for identifier: {identifier}")
    return definition


def generate_recipe_definition(
    recipe_data: Dict[str, Any], options: Optional[DefinitionOptions] = None
) -> Dict[str, Any]:
    """Generate a Bedrock recipe definition.

    Args:
        recipe_data: Dictionary with recipe information (id, name, etc.).
        options: Optional DefinitionOptions for customization.

    Returns:
        Complete Bedrock recipe definition dictionary.
    """
    if options is None:
        options = DefinitionOptions()

    options.identifier = options.identifier or recipe_data.get(
        "identifier", f"custom:{recipe_data.get('id', 'recipe_placeholder')}"
    )
    options.name = options.name or recipe_data.get("name", "Custom Recipe")
    options.source_java_id = options.source_java_id or recipe_data.get("id", "unknown_java_id")

    identifier = options.identifier

    definition: Dict[str, Any] = {
        "format_version": options.format_version,
        "minecraft:recipe_furnace": {
            "description": _build_description(ComponentType.RECIPE, identifier),
            "components": _build_components(ComponentType.RECIPE, identifier, options),
            "metadata_generated": _build_metadata(options, ComponentType.RECIPE),
        },
    }

    logger.info(f"Generated recipe definition for identifier: {identifier}")
    return definition


def generate_definition_json(component_data_str: str, component_type: str) -> str:
    """Generate a component definition JSON string from raw input.

    This is the main entry point used by the legacy tool interface.

    Args:
        component_data_str: JSON string with component data.
        component_type: Type of component ("block", "item", "entity", "recipe").

    Returns:
        JSON string with generated definition or error.
    """
    try:
        component_data = json.loads(component_data_str)
        component_type_lower = component_type.lower()

        if component_type_lower == "block":
            definition = generate_block_definition(component_data)
        elif component_type_lower == "item":
            definition = generate_item_definition(component_data)
        elif component_type_lower == "entity":
            definition = generate_entity_definition(component_data)
        elif component_type_lower == "recipe":
            definition = generate_recipe_definition(component_data)
        else:
            return json.dumps(
                {"success": False, "error": f"Unknown component type: {component_type}"},
                indent=2,
            )

        return json.dumps(
            {
                "success": True,
                "component_type": component_type,
                "identifier": component_data.get(
                    "identifier",
                    f"custom:{component_data.get('id', f'{component_type}_placeholder')}",
                ),
                "definition_json": definition,
                "message": f"Placeholder {component_type} definition generated successfully.",
            },
            indent=2,
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input for placeholder {component_type} definition: {e}")
        return json.dumps(
            {"success": False, "error": f"Invalid JSON input for {component_type} definition: {e}"},
            indent=2,
        )
    except Exception as e:
        logger.error(
            f"Error generating placeholder {component_type} definition: {e}", exc_info=True
        )
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to generate placeholder {component_type} definition: {e}",
            },
            indent=2,
        )


class BehaviorPlanner:
    """High-level planner for generating Bedrock behavior definitions.

    Use this class when you need to generate multiple related definitions
    with consistent configuration.
    """

    def __init__(self, format_version: str = "1.20.0") -> None:
        """Initialize planner with format version.

        Args:
            format_version: Bedrock format version to use for all definitions.
        """
        self.format_version = format_version
        self._definitions: List[Dict[str, Any]] = []

    def add_block(self, block_data: Dict[str, Any]) -> BehaviorPlanner:
        """Add a block definition to the plan.

        Args:
            block_data: Block data dictionary.

        Returns:
            Self for chaining.
        """
        options = DefinitionOptions(format_version=self.format_version)
        self._definitions.append(generate_block_definition(block_data, options))
        return self

    def add_item(self, item_data: Dict[str, Any]) -> BehaviorPlanner:
        """Add an item definition to the plan.

        Args:
            item_data: Item data dictionary.

        Returns:
            Self for chaining.
        """
        options = DefinitionOptions(format_version=self.format_version)
        self._definitions.append(generate_item_definition(item_data, options))
        return self

    def add_entity(self, entity_data: Dict[str, Any]) -> BehaviorPlanner:
        """Add an entity definition to the plan.

        Args:
            entity_data: Entity data dictionary.

        Returns:
            Self for chaining.
        """
        options = DefinitionOptions(format_version=self.format_version)
        self._definitions.append(generate_entity_definition(entity_data, options))
        return self

    def add_recipe(self, recipe_data: Dict[str, Any]) -> BehaviorPlanner:
        """Add a recipe definition to the plan.

        Args:
            recipe_data: Recipe data dictionary.

        Returns:
            Self for chaining.
        """
        options = DefinitionOptions(format_version=self.format_version)
        self._definitions.append(generate_recipe_definition(recipe_data, options))
        return self

    def get_definitions(self) -> List[Dict[str, Any]]:
        """Get all generated definitions.

        Returns:
            List of definition dictionaries.
        """
        return self._definitions.copy()

    def clear(self) -> None:
        """Clear all generated definitions."""
        self._definitions.clear()
