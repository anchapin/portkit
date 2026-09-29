"""
NBT Parser for extracting properties from Java entity data structures.
Part of the entity/ subpackage for Issue #1276 refactoring.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MobCategory(Enum):
    """Categories for different mob types in Bedrock."""

    HOSTILE = "hostile"
    PASSIVE = "passive"
    NEUTRAL = "neutral"
    BOSS = "boss"


class EntityType(Enum):
    PASSIVE = "passive"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    BOSS = "boss"
    AMBIENT = "ambient"
    MISC = "misc"


@dataclass
class EntityProperties:
    """Properties for Java entity extraction."""

    health: float = 20.0
    movement_speed: float = 0.25
    follow_range: float = 16.0
    attack_damage: float = 0.0
    armor: float = 0.0
    knockback_resistance: float = 0.0
    can_swim: bool = True
    can_climb: bool = False
    can_fly: bool = False
    breathes_air: bool = True
    breathes_water: bool = False
    pushable: bool = True
    entity_type: EntityType = EntityType.PASSIVE


@dataclass
class BlockProperties:
    """Properties for Java block extraction."""

    hardness: float = 1.0
    resistance: float = 1.0
    light_emission: int = 0
    light_dampening: int = 15
    is_solid: bool = True
    can_contain_liquid: bool = False
    material_type: str = "stone"
    flammable: bool = False
    map_color: str = "#8F7748"


@dataclass
class ItemProperties:
    """Properties for Java item extraction."""

    stack_size: int = 64
    durability: Optional[int] = None
    is_tool: bool = False
    is_food: bool = False
    nutrition: int = 0
    saturation: float = 0.0
    can_always_eat: bool = False


class MaterialType(Enum):
    """Material types for blocks."""

    STONE = "stone"
    WOOD = "wood"
    METAL = "metal"
    GLASS = "glass"
    CLOTH = "cloth"
    DIRT = "dirt"
    SAND = "sand"
    SNOW = "snow"
    ICE = "ice"
    WATER = "water"
    LAVA = "lava"


class ToolType(Enum):
    """Tool types for items."""

    PICKAXE = "pickaxe"
    AXE = "axe"
    SHOVEL = "shovel"
    HOE = "hoe"
    SWORD = "sword"
    SHEARS = "shears"
    BOW = "bow"
    CROSSBOW = "crossbow"
    TRIDENT = "trident"


class ArmorType(Enum):
    """Armor types for items."""

    HELMET = "helmet"
    CHESTPLATE = "chestplate"
    LEGGINGS = "leggings"
    BOOTS = "boots"


@dataclass
class ToolProperties:
    """Properties for tool items (pickaxe, axe, shovel, hoe, sword)."""

    tool_type: ToolType = ToolType.PICKAXE
    mining_level: int = 1
    durability: int = 250
    mining_speed: float = 1.0
    attack_damage: float = 1.0
    enchantable: bool = True


@dataclass
class ArmorProperties:
    """Properties for armor items (helmet, chestplate, leggings, boots)."""

    armor_type: ArmorType = ArmorType.CHESTPLATE
    armor_value: int = 1
    durability: int = 100
    enchantable: bool = True


@dataclass
class ConsumableProperties:
    """Properties for consumable items (food, potions)."""

    nutrition: int = 1
    saturation: float = 0.6
    can_always_eat: bool = False
    drink: bool = False
    effect: Optional[str] = None
    effect_duration: int = 0
    effect_amplifier: int = 0


@dataclass
class RangedWeaponProperties:
    """Properties for ranged weapons (bows, crossbows)."""

    damage: float = 9.0
    draw_speed: float = 1.0
    durability: int = 384
    enchantable: bool = True
    infinite_arrows: bool = False


@dataclass
class RareItemProperties:
    """Properties for rare/special items with enchantments."""

    stack_size: int = 1
    durability: Optional[int] = None
    enchantable: bool = True
    enchantment_level: int = 1
    is_rare: bool = True
    lore: Optional[str] = None


def parse_java_entity_properties(java_entity: Dict[str, Any]) -> EntityProperties:
    """
    Parse Java entity properties from entity data.

    Args:
        java_entity: Java entity definition dictionary

    Returns:
        EntityProperties instance with parsed values
    """
    properties = EntityProperties()

    if "attributes" in java_entity:
        attrs = java_entity["attributes"]
        properties.health = attrs.get("max_health", 20.0)
        properties.movement_speed = attrs.get("movement_speed", 0.25)
        properties.follow_range = attrs.get("follow_range", 16.0)
        properties.attack_damage = attrs.get("attack_damage", 0.0)
        properties.armor = attrs.get("armor", 0.0)
        properties.knockback_resistance = attrs.get("knockback_resistance", 0.0)

    entity_category = java_entity.get("category", "passive").lower()
    try:
        properties.entity_type = EntityType(entity_category)
    except ValueError:
        logger.warning(f"Unknown entity category: {entity_category}, using passive")
        properties.entity_type = EntityType.PASSIVE

    properties.can_swim = java_entity.get("can_swim", True)
    properties.can_climb = java_entity.get("can_climb", False)
    properties.can_fly = java_entity.get("can_fly", False)
    properties.breathes_air = java_entity.get("breathes_air", True)
    properties.breathes_water = java_entity.get("breathes_water", False)
    properties.pushable = java_entity.get("pushable", True)

    return properties


def parse_java_block_properties(java_block: Dict[str, Any]) -> BlockProperties:
    """
    Parse Java block properties from block data.

    Args:
        java_block: Java block definition dictionary

    Returns:
        BlockProperties instance with parsed values
    """
    properties = BlockProperties()

    if "properties" in java_block:
        props = java_block["properties"]

        properties.hardness = props.get("hardness", 1.0)
        properties.resistance = props.get("resistance", properties.hardness)
        properties.light_emission = props.get("light_level", 0)
        properties.is_solid = props.get("solid", True)
        properties.flammable = props.get("flammable", False)

        material_str = props.get("material", "stone").lower()
        try:
            properties.material_type = material_str
        except ValueError:
            logger.warning(f"Unknown material type: {material_str}, using stone")
            properties.material_type = "stone"

    return properties


def parse_java_item_properties(java_item: Dict[str, Any]) -> ItemProperties:
    """
    Parse Java item properties from item data.

    Args:
        java_item: Java item definition dictionary

    Returns:
        ItemProperties instance with parsed values
    """
    properties = ItemProperties()

    if "properties" in java_item:
        props = java_item["properties"]

        properties.stack_size = props.get("max_stack_size", 64)
        properties.durability = props.get("max_damage")
        properties.is_tool = props.get("is_tool", False)
        properties.is_food = props.get("is_food", False)

        if properties.is_food:
            properties.nutrition = props.get("nutrition", 1)
            properties.saturation = props.get("saturation", 0.6)
            properties.can_always_eat = props.get("can_always_eat", False)

    return properties
