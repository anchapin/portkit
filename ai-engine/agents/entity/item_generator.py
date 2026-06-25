"""
Item Generator for Bedrock item JSON and model resolution.
Part of the entity/ subpackage for Issue #1276 refactoring.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.entity.block_state_parser import determine_item_category, CREATIVE_CATEGORIES
from agents.entity.nbt_parser import (
    ArmorProperties,
    ArmorType,
    ConsumableProperties,
    ItemProperties,
    RareItemProperties,
    RangedWeaponProperties,
    ToolProperties,
    ToolType,
    parse_java_item_properties,
)

ITEM_TEMPLATE = {
    "format_version": "1.19.0",
    "minecraft:item": {
        "description": {"identifier": "", "register_to_creative_menu": True},
        "components": {},
    },
}


def create_item_definition(item_id: str, namespace: str = "modporter") -> Dict[str, Any]:
    """
    Create a new Bedrock item definition template.

    Args:
        item_id: Item identifier
        namespace: Namespace for the item

    Returns:
        Item definition dictionary
    """
    full_id = f"{namespace}:{item_id}"
    return {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {},
        },
    }


def convert_java_item(java_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single Java item to Bedrock format.

    Args:
        java_item: Java item definition

    Returns:
        Bedrock item definition
    """
    item_id = java_item.get("id", "unknown_item")
    namespace = java_item.get("namespace", "modporter")
    full_id = f"{namespace}:{item_id}"

    bedrock_item = {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {},
        },
    }

    properties = parse_java_item_properties(java_item)

    components = bedrock_item["minecraft:item"]["components"]

    components["minecraft:max_stack_size"] = properties.stack_size
    components["minecraft:icon"] = {"texture": item_id}

    if properties.durability and properties.is_tool:
        components["minecraft:durability"] = {"max_durability": properties.durability}
        components["minecraft:repairable"] = {
            "repair_items": [
                {
                    "items": [full_id],
                    "repair_amount": "context.other->q.remaining_durability + 0.05 * context.other->q.max_durability",
                }
            ]
        }

    if properties.is_food:
        components["minecraft:food"] = {
            "nutrition": properties.nutrition,
            "saturation_modifier": properties.saturation,
        }
        if properties.can_always_eat:
            components["minecraft:food"]["can_always_eat"] = True

    category = determine_item_category(java_item)
    if category:
        components["minecraft:creative_category"] = {"category": category}

    return bedrock_item


def generate_tool_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a Bedrock tool item definition.

    Args:
        data: Dictionary containing tool data

    Returns:
        Bedrock item definition JSON
    """
    item_id = data.get("id", "unknown_tool")
    namespace = data.get("namespace", "modporter")
    full_id = f"{namespace}:{item_id}"

    props = data.get("properties", {})
    if isinstance(props, dict):
        tool_props = ToolProperties(
            tool_type=ToolType(props.get("tool_type", "pickaxe")),
            mining_level=props.get("mining_level", 1),
            durability=props.get("durability", 250),
            mining_speed=props.get("mining_speed", 1.0),
            attack_damage=props.get("attack_damage", 1.0),
            enchantable=props.get("enchantable", True),
        )
    else:
        tool_props = props

    bedrock_item = {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {
                "minecraft:max_stack_size": 1,
                "minecraft:icon": {"texture": item_id},
                "minecraft:durability": {"max_durability": tool_props.durability},
                "minecraft:mining_speed": tool_props.mining_speed,
                "minecraft:damage": tool_props.attack_damage,
                "minecraft:creative_category": {"category": CREATIVE_CATEGORIES["tools"]},
            },
        },
    }

    components = bedrock_item["minecraft:item"]["components"]
    components["minecraft:repairable"] = {
        "repair_items": [
            {
                "items": [full_id],
                "repair_amount": "context.other->q.remaining_durability + 0.05 * context.other->q.max_durability",
            }
        ]
    }

    if tool_props.enchantable:
        components["minecraft:enchantable"] = {"slot": "all"}

    components["minecraft:tool"] = {"tier": tool_props.mining_level}

    return bedrock_item


def generate_armor_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a Bedrock armor item definition.

    Args:
        data: Dictionary containing armor data

    Returns:
        Bedrock item definition JSON
    """
    item_id = data.get("id", "unknown_armor")
    namespace = data.get("namespace", "modporter")
    full_id = f"{namespace}:{item_id}"

    props = data.get("properties", {})
    if isinstance(props, dict):
        armor_props = ArmorProperties(
            armor_type=ArmorType(props.get("armor_type", "chestplate")),
            armor_value=props.get("armor_value", 1),
            durability=props.get("durability", 100),
            enchantable=props.get("enchantable", True),
        )
    else:
        armor_props = props

    bedrock_item = {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {
                "minecraft:max_stack_size": 1,
                "minecraft:icon": {"texture": item_id},
                "minecraft:durability": {"max_durability": armor_props.durability},
                "minecraft:armor": {
                    "slot": armor_props.armor_type.value,
                    "protection": armor_props.armor_value,
                },
                "minecraft:creative_category": {"category": CREATIVE_CATEGORIES["combat"]},
            },
        },
    }

    components = bedrock_item["minecraft:item"]["components"]
    components["minecraft:repairable"] = {
        "repair_items": [
            {
                "items": [full_id],
                "repair_amount": "context.other->q.remaining_durability + 0.05 * context.other->q.max_durability",
            }
        ]
    }

    if armor_props.enchantable:
        components["minecraft:enchantable"] = {"slot": "armor"}

    return bedrock_item


def generate_consumable_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a Bedrock consumable item definition (food, potions).

    Args:
        data: Dictionary containing consumable data

    Returns:
        Bedrock item definition JSON
    """
    item_id = data.get("id", "unknown_consumable")
    namespace = data.get("namespace", "modporter")
    full_id = f"{namespace}:{item_id}"

    props = data.get("properties", {})
    if isinstance(props, dict):
        consumable_props = ConsumableProperties(
            nutrition=props.get("nutrition", 1),
            saturation=props.get("saturation", 0.6),
            can_always_eat=props.get("can_always_eat", False),
            drink=props.get("drink", False),
            effect=props.get("effect"),
            effect_duration=props.get("effect_duration", 0),
            effect_amplifier=props.get("effect_amplifier", 0),
        )
    else:
        consumable_props = props

    category = (
        CREATIVE_CATEGORIES["brewing"] if consumable_props.drink else CREATIVE_CATEGORIES["food"]
    )

    bedrock_item = {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {
                "minecraft:max_stack_size": 64,
                "minecraft:icon": {"texture": item_id},
                "minecraft:food": {
                    "nutrition": consumable_props.nutrition,
                    "saturation_modifier": consumable_props.saturation,
                    "can_always_eat": consumable_props.can_always_eat,
                },
                "minecraft:creative_category": {"category": category},
            },
        },
    }

    if consumable_props.effect:
        components = bedrock_item["minecraft:item"]["components"]
        components["minecraft:food"]["effects"] = [
            {
                "name": consumable_props.effect,
                "duration": consumable_props.effect_duration,
                "amplifier": consumable_props.effect_amplifier,
            }
        ]

    return bedrock_item


def generate_ranged_weapon_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a Bedrock ranged weapon item definition (bow, crossbow).

    Args:
        data: Dictionary containing ranged weapon data

    Returns:
        Bedrock item definition JSON
    """
    item_id = data.get("id", "unknown_ranged")
    namespace = data.get("namespace", "modporter")
    full_id = f"{namespace}:{item_id}"

    props = data.get("properties", {})
    if isinstance(props, dict):
        weapon_props = RangedWeaponProperties(
            damage=props.get("damage", 9.0),
            draw_speed=props.get("draw_speed", 1.0),
            durability=props.get("durability", 384),
            enchantable=props.get("enchantable", True),
            infinite_arrows=props.get("infinite_arrows", False),
        )
    else:
        weapon_props = props

    bedrock_item = {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {
                "minecraft:max_stack_size": 1,
                "minecraft:icon": {"texture": item_id},
                "minecraft:durability": {"max_durability": weapon_props.durability},
                "minecraft:damage": weapon_props.damage,
                "minecraft:creative_category": {"category": CREATIVE_CATEGORIES["combat"]},
            },
        },
    }

    components = bedrock_item["minecraft:item"]["components"]
    components["minecraft:repairable"] = {
        "repair_items": [
            {
                "items": [full_id],
                "repair_amount": "context.other->q.remaining_durability + 0.05 * context.other->q.max_durability",
            }
        ]
    }

    if weapon_props.enchantable:
        components["minecraft:enchantable"] = {"slot": "bow"}

    components["minecraft:ranged_weapon"] = {
        "max_draw_duration": weapon_props.draw_speed,
        "speed_multiplier": weapon_props.draw_speed,
        "charged": False,
    }

    if weapon_props.infinite_arrows:
        components["minecraft:infinite"] = {}

    return bedrock_item


def generate_rare_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a Bedrock rare/special item definition with enchantments.

    Args:
        data: Dictionary containing rare item data

    Returns:
        Bedrock item definition JSON
    """
    item_id = data.get("id", "unknown_rare")
    namespace = data.get("namespace", "modporter")
    full_id = f"{namespace}:{item_id}"

    props = data.get("properties", {})
    if isinstance(props, dict):
        rare_props = RareItemProperties(
            stack_size=props.get("stack_size", 1),
            durability=props.get("durability"),
            enchantable=props.get("enchantable", True),
            enchantment_level=props.get("enchantment_level", 1),
            is_rare=props.get("is_rare", True),
            lore=props.get("lore"),
        )
    else:
        rare_props = props

    bedrock_item = {
        "format_version": "1.19.0",
        "minecraft:item": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {
                "minecraft:max_stack_size": rare_props.stack_size,
                "minecraft:icon": {"texture": item_id},
                "minecraft:creative_category": {"category": CREATIVE_CATEGORIES["misc"]},
            },
        },
    }

    components = bedrock_item["minecraft:item"]["components"]

    if rare_props.durability:
        components["minecraft:durability"] = {"max_durability": rare_props.durability}
        components["minecraft:repairable"] = {
            "repair_items": [
                {
                    "items": [full_id],
                    "repair_amount": "context.other->q.remaining_durability + 0.05 * context.other->q.max_durability",
                }
            ]
        }

    if rare_props.enchantable:
        components["minecraft:enchantable"] = {
            "slot": "all",
            "value": rare_props.enchantment_level,
        }

    if rare_props.lore:
        components["minecraft:display_name"] = {"value": rare_props.lore}

    if rare_props.is_rare:
        components["minecraft:can_place_on"] = {"predicates": {}}

    return bedrock_item


def generate_items(java_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate Bedrock item definitions from Java items.

    Args:
        java_items: List of Java item definitions

    Returns:
        Dictionary of Bedrock item definitions
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"Generating Bedrock items for {len(java_items)} Java items")
    bedrock_items = {}

    for java_item in java_items:
        try:
            bedrock_item = convert_java_item(java_item)
            item_id = bedrock_item["minecraft:item"]["description"]["identifier"]
            bedrock_items[item_id] = bedrock_item
        except Exception as e:
            logger.error(f"Failed to convert item {java_item.get('id', 'unknown')}: {e}")
            continue

    logger.info(f"Successfully generated {len(bedrock_items)} Bedrock items")
    return bedrock_items


def write_items_to_disk(items: Dict[str, Any], bp_path: Path) -> List[Path]:
    """
    Write item definitions to disk.

    Args:
        items: Dictionary of item definitions
        bp_path: Behavior pack path

    Returns:
        List of written file paths
    """
    import json

    written_files = []

    if items:
        bp_items_dir = bp_path / "items"
        bp_items_dir.mkdir(parents=True, exist_ok=True)

        for item_id, item_def in items.items():
            file_path = bp_items_dir / f"{item_id.split(':')[-1]}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(item_def, f, indent=2, ensure_ascii=False)
            written_files.append(file_path)

    return written_files
