"""
Type Registry for Java entity/block/item type to Bedrock identifier lookups.
Part of the entity/ subpackage for Issue #1276 refactoring.
"""

from typing import Any, Dict, List, Optional

from agents.entity.attribute_mapper import GOAL_MAPPINGS, build_behavior_config
from agents.entity.nbt_parser import EntityProperties, EntityType, parse_java_entity_properties


TYPE_MAPPINGS = {
    "zombie": "minecraft:zombie",
    "skeleton": "minecraft:skeleton",
    "creeper": "minecraft:creeper",
    "spider": "minecraft:spider",
    "pig": "minecraft:pig",
    "cow": "minecraft:cow",
    "sheep": "minecraft:sheep",
    "chicken": "minecraft:chicken",
    "horse": "minecraft:horse",
    "wolf": "minecraft:wolf",
}


def lookup_bedrock_entity_id(java_entity_type: str) -> str:
    """
    Look up Bedrock entity identifier for Java entity type.

    Args:
        java_entity_type: Java entity type string

    Returns:
        Bedrock entity identifier
    """
    return TYPE_MAPPINGS.get(java_entity_type.lower(), f"modporter:{java_entity_type}")


def lookup_bedrock_block_id(java_block_type: str) -> str:
    """
    Look up Bedrock block identifier for Java block type.

    Args:
        java_block_type: Java block type string

    Returns:
        Bedrock block identifier
    """
    return f"modporter:{java_block_type}"


def lookup_bedrock_item_id(java_item_type: str) -> str:
    """
    Look up Bedrock item identifier for Java item type.

    Args:
        java_item_type: Java item type string

    Returns:
        Bedrock item identifier
    """
    return f"modporter:{java_item_type}"


def create_entity_description(
    java_entity: Dict[str, Any], default_namespace: str = "modporter"
) -> Dict[str, Any]:
    """
    Create entity description dictionary from Java entity.

    Args:
        java_entity: Java entity definition
        default_namespace: Default namespace to use

    Returns:
        Entity description dict with identifier and flags
    """
    entity_id = java_entity.get("id", "unknown_entity")
    namespace = java_entity.get("namespace", default_namespace)
    full_id = f"{namespace}:{entity_id}"

    return {
        "identifier": full_id,
        "is_spawnable": java_entity.get("spawnable", True),
        "is_summonable": java_entity.get("summonable", True),
        "is_experimental": False,
    }


def convert_ai_goals(java_goals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Convert Java AI goals to Bedrock behaviors.

    Args:
        java_goals: List of Java AI goal definitions

    Returns:
        Dictionary of Bedrock behavior components
    """
    result = {}
    for goal in java_goals:
        goal_type = goal.get("type", "").lower()
        priority = goal.get("priority", 1)
        goal_config = goal.get("config", {})

        bedrock_behavior = GOAL_MAPPINGS.get(goal_type)
        if bedrock_behavior:
            result[bedrock_behavior] = build_behavior_config(goal_type, priority, goal_config)

    return result


def add_ai_goals(components: Dict[str, Any], ai_goals: List[Dict[str, Any]]) -> None:
    """
    Add AI goals as behavior components.

    Args:
        components: Bedrock entity components dict
        ai_goals: List of Java AI goal definitions
    """
    from agents.entity.attribute_mapper import add_legacy_goal

    for goal in ai_goals:
        goal_type = goal.get("type", "").lower()
        priority = goal.get("priority", 1)
        goal_config = goal.get("config", {})

        bedrock_behavior = GOAL_MAPPINGS.get(goal_type)

        if bedrock_behavior:
            behavior_config = build_behavior_config(goal_type, priority, goal_config)
            components[bedrock_behavior] = behavior_config
        else:
            add_legacy_goal(components, goal_type, priority, goal_config)
