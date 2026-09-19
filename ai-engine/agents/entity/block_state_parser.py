"""
Block State Parser for resolving block state variants.
Part of the entity/ subpackage for Issue #1276 refactoring.
"""

import logging
from typing import Any, Dict, Optional

from agents.entity.nbt_parser import MaterialType

logger = logging.getLogger(__name__)


CREATIVE_CATEGORIES = {
    "building": "itemGroup.name.construction",
    "decoration": "itemGroup.name.decoration",
    "redstone": "itemGroup.name.redstone",
    "transportation": "itemGroup.name.transportation",
    "misc": "itemGroup.name.misc",
    "food": "itemGroup.name.food",
    "tools": "itemGroup.name.tools",
    "combat": "itemGroup.name.combat",
    "brewing": "itemGroup.name.brewing",
}


def determine_block_category(java_block: Dict[str, Any]) -> Optional[str]:
    """
    Determine appropriate creative menu category for block.

    Args:
        java_block: Java block definition

    Returns:
        Creative category string or None
    """
    return _determine_category(
        java_block,
        "building",
        {
            "building": (["building", "construction"], []),
            "decoration": (["decoration", "decorative"], ["door", "gate"]),
            "redstone": (["redstone", "power"], []),
        },
    )


def _determine_category(
    java_data: Dict[str, Any], default_category: str, category_rules: Dict[str, tuple]
) -> Optional[str]:
    """
    Helper method to determine creative menu category based on tags and type.

    Args:
        java_data: Java data definition
        default_category: Default category key
        category_rules: Dictionary of category rules

    Returns:
        Creative category string or None
    """
    tags = java_data.get("tags", [])
    data_type = java_data.get("type", "").lower()

    for category, (tag_matches, type_matches) in category_rules.items():
        if any(tag in tag_matches for tag in tags):
            return CREATIVE_CATEGORIES[category]
        if any(match in data_type for match in type_matches):
            return CREATIVE_CATEGORIES[category]

    return CREATIVE_CATEGORIES[default_category]


def determine_item_category(java_item: Dict[str, Any]) -> Optional[str]:
    """
    Determine appropriate creative menu category for item.

    Args:
        java_item: Java item definition

    Returns:
        Creative category string or None
    """
    return _determine_category(
        java_item,
        "misc",
        {
            "tools": (["tool", "tools"], ["pickaxe", "axe", "shovel", "hoe"]),
            "combat": (["weapon", "combat"], ["sword", "bow"]),
            "food": (["food", "edible"], []),
        },
    )
