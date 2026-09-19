"""
Entity Behavior Patterns Module

Provides comprehensive behavior patterns for converting Java entity AI to Bedrock format.
Part of the Bedrock Add-on Generation System

Issue: #6 - Entity Converter
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityBehaviorType(Enum):
    """Types of entity behaviors in Bedrock."""

    MOVEMENT = "movement"
    COMBAT = "combat"
    SOCIAL = "social"
    ENVIRONMENTAL = "environmental"
    INTERACTION = "interaction"
    SPECIALIZED = "specialized"


class JavaAIGoal(Enum):
    """Java AI Goal types for mapping to Bedrock."""

    # Movement
    MOVE_TOWARDS = "move_towards"
    WANDER = "wander"
    STROLL = "stroll"
    SWIM = "swim"
    FLY = "fly"
    CLIMB = "climb"
    JUMP = "jump"
    FLOAT = "float"

    # Targeting
    LOOK_AT_PLAYER = "look_at_player"
    LOOK_AT_TARGET = "look_at_target"
    LOOK_RANDOMLY = "look_randomly"

    # Attack
    MELEE_ATTACK = "melee_attack"
    RANGED_ATTACK = "ranged_attack"
    HURT_TARGET = "hurt_target"
    ATTACK = "attack"

    # Social
    BREED = "breed"
    TEMPT = "tempt"
    FOLLOW = "follow"
    TAME = "tame"

    # Survival
    PANIC = "panic"
    FLEE = "flee"
    AVOID = "avoid"
    HIDE = "hide"
    REST = "rest"
    SEEK_WATER = "seek_water"

    # Interaction
    INTERACT = "interact"
    TRADE = "trade"
    OPEN_DOOR = "open_door"
    USE_ITEM = "use_item"
    PICKUP = "pickup"


@dataclass
class BehaviorPattern:
    """Pattern for entity behavior conversion."""

    java_goal: str
    bedrock_behavior: str
    priority: int
    default_config: Dict[str, Any]
    description: str


# Comprehensive behavior patterns for entity conversion
ENTITY_BEHAVIOR_PATTERNS: Dict[str, BehaviorPattern] = {
    # Movement Patterns
    "move_towards": BehaviorPattern(
        java_goal="move_towards",
        bedrock_behavior="minecraft:behavior.move_towards_target",
        priority=4,
        default_config={
            "speed_multiplier": 1.0,
            "target_distance": 4.0,
            "track_target": True,
        },
        description="Move towards a target entity or location",
    ),
    "wander": BehaviorPattern(
        java_goal="wander",
        bedrock_behavior="minecraft:behavior.wander",
        priority=6,
        default_config={
            "speed_multiplier": 0.8,
            "wander_distance": 10,
            "start_chance": 0.2,
        },
        description="Wander randomly when idle",
    ),
    "random_stroll": BehaviorPattern(
        java_goal="random_stroll",
        bedrock_behavior="minecraft:behavior.wander",
        priority=7,
        default_config={
            "speed_multiplier": 0.5,
            "wander_distance": 5,
            "start_chance": 0.3,
        },
        description="Random strolling behavior",
    ),
    "swim": BehaviorPattern(
        java_goal="swim",
        bedrock_behavior="minecraft:behavior.swim",
        priority=2,
        default_config={
            "sound_interval": 150,
            "success_interval": 120,
        },
        description="Swimming behavior for aquatic mobs",
    ),
    "fly": BehaviorPattern(
        java_goal="fly",
        bedrock_behavior="minecraft:behavior.fly",
        priority=3,
        default_config={
            "speed_multiplier": 1.0,
        },
        description="Flying behavior for aerial mobs",
    ),
    "float": BehaviorPattern(
        java_goal="float",
        bedrock_behavior="minecraft:behavior.float",
        priority=0,
        default_config={},
        description="Floating/suspended behavior",
    ),
    # Targeting Patterns
    "look_at_player": BehaviorPattern(
        java_goal="look_at_player",
        bedrock_behavior="minecraft:behavior.look_at_player",
        priority=5,
        default_config={
            "look_distance": 8.0,
            "look_time": [2, 4],
        },
        description="Look at nearby players",
    ),
    "look_at_target": BehaviorPattern(
        java_goal="look_at_target",
        bedrock_behavior="minecraft:behavior.look_at_target",
        priority=5,
        default_config={
            "look_distance": 6.0,
        },
        description="Look at current target",
    ),
    "random_look_around": BehaviorPattern(
        java_goal="random_look_around",
        bedrock_behavior="minecraft:behavior.random_look_around",
        priority=8,
        default_config={
            "look_distance": 6.0,
            "look_time": [4, 8],
        },
        description="Randomly look around",
    ),
    # Combat Patterns
    "melee_attack": BehaviorPattern(
        java_goal="melee_attack",
        bedrock_behavior="minecraft:behavior.melee_attack",
        priority=3,
        default_config={
            "speed_multiplier": 1.0,
            "track_target": True,
            "reach_multiplier": 0.8,
        },
        description="Melee attack behavior",
    ),
    "ranged_attack": BehaviorPattern(
        java_goal="ranged_attack",
        bedrock_behavior="minecraft:behavior.attack_with_range",
        priority=3,
        default_config={
            "speed_multiplier": 1.0,
            "attack_interval_min": 1,
            "attack_interval_max": 3,
            "attack_radius": 10.0,
        },
        description="Ranged attack behavior",
    ),
    "panic": BehaviorPattern(
        java_goal="panic",
        bedrock_behavior="minecraft:behavior.panic",
        priority=1,
        default_config={
            "speed_multiplier": 1.25,
            "panic_sound": "mob.hostile.hurt",
        },
        description="Panic behavior when hurt",
    ),
    "attack_entity": BehaviorPattern(
        java_goal="attack_entity",
        bedrock_behavior="minecraft:behavior.attack_entity",
        priority=3,
        default_config={
            "speed_multiplier": 1.0,
            "track_target": True,
        },
        description="Attack specific entity",
    ),
    # Social Patterns
    "breed": BehaviorPattern(
        java_goal="breed",
        bedrock_behavior="minecraft:behavior.breed",
        priority=4,
        default_config={
            "speed_multiplier": 1.0,
        },
        description="Breeding behavior",
    ),
    "tempt": BehaviorPattern(
        java_goal="tempt",
        bedrock_behavior="minecraft:behavior.tempt",
        priority=5,
        default_config={
            "speed_multiplier": 1.0,
            "within_radius": 10.0,
        },
        description="Tempted by items",
    ),
    "follow_player": BehaviorPattern(
        java_goal="follow_player",
        bedrock_behavior="minecraft:behavior.follow_player",
        priority=6,
        default_config={
            "speed_multiplier": 1.0,
            "start_distance": 5.0,
            "stop_distance": 2.0,
        },
        description="Follow the player",
    ),
    "tame": BehaviorPattern(
        java_goal="tame",
        bedrock_behavior="minecraft:behavior.tame",
        priority=3,
        default_config={
            "probability": 0.33,
        },
        description="Taming behavior",
    ),
    # Survival Patterns
    "flee": BehaviorPattern(
        java_goal="flee",
        bedrock_behavior="minecraft:behavior.avoid_entity",
        priority=2,
        default_config={
            "speed_multiplier": 1.0,
            "max_dist": 10.0,
            "ignore_visibility": False,
        },
        description="Flee from entities",
    ),
    "avoid_entity": BehaviorPattern(
        java_goal="avoid_entity",
        bedrock_behavior="minecraft:behavior.avoid_entity",
        priority=3,
        default_config={
            "speed_multiplier": 1.0,
            "max_dist": 6.0,
            "ignore_visibility": False,
        },
        description="Avoid specific entities",
    ),
    "seek_shelter": BehaviorPattern(
        java_goal="seek_shelter",
        bedrock_behavior="minecraft:behavior.seek_shelter",
        priority=2,
        default_config={
            "speed_multiplier": 1.0,
        },
        description="Seek shelter during storms",
    ),
    "leave_water": BehaviorPattern(
        java_goal="leave_water",
        bedrock_behavior="minecraft:behavior.leave_water",
        priority=3,
        default_config={
            "speed_multiplier": 1.0,
        },
        description="Leave water body",
    ),
    "restrict_sun": BehaviorPattern(
        java_goal="restrict_sun",
        bedrock_behavior="minecraft:behavior.restrict_sun",
        priority=4,
        default_config={},
        description="Avoid direct sunlight",
    ),
    # Interaction Patterns
    "interact": BehaviorPattern(
        java_goal="interact",
        bedrock_behavior="minecraft:behavior.interact",
        priority=7,
        default_config={
            "speed_multiplier": 1.0,
            "target_distance": 3.0,
        },
        description="Interact with entities/blocks",
    ),
    "trade": BehaviorPattern(
        java_goal="trade",
        bedrock_behavior="Offers:behavior.trade_with_player",
        priority=6,
        default_config={},
        description="Trading with villagers",
    ),
    "pickup_items": BehaviorPattern(
        java_goal="pickup_items",
        bedrock_behavior="minecraft:behavior.pickup_items",
        priority=5,
        default_config={
            "speed_multiplier": 1.0,
            "pickup_below_distance": 2.0,
        },
        description="Pick up nearby items",
    ),
    "item_consume": BehaviorPattern(
        java_goal="item_consume",
        bedrock_behavior="minecraft:behavior.item_consume",
        priority=4,
        default_config={
            "speed_multiplier": 1.0,
        },
        description="Consume items (food, potions)",
    ),
    # Specialized Patterns
    "celebrate": BehaviorPattern(
        java_goal="celebrate",
        bedrock_behavior="minecraft:behavior.celebrate",
        priority=6,
        default_config={
            "speed_multiplier": 1.0,
            "celebration_time": 200,
        },
        description="Celebration behavior",
    ),
    "find_mount": BehaviorPattern(
        java_goal="find_mount",
        bedrock_behavior="minecraft:behavior.find_mount",
        priority=3,
        default_config={
            "max_distance": 5.0,
            "max_height": 10,
        },
        description="Find entity to mount",
    ),
    "lay_egg": BehaviorPattern(
        java_goal="lay_egg",
        bedrock_behavior="minecraft:behavior.lay_egg",
        priority=4,
        default_config={
            "speed_multiplier": 0.5,
        },
        description="Lay eggs (chickens)",
    ),
}


def get_behavior_pattern(java_goal: str) -> Optional[BehaviorPattern]:
    """
    Get behavior pattern for a Java AI goal.

    Args:
        java_goal: The Java AI goal name

    Returns:
        BehaviorPattern if found, None otherwise
    """
    return ENTITY_BEHAVIOR_PATTERNS.get(java_goal.lower())


def get_all_behavior_patterns() -> Dict[str, BehaviorPattern]:
    """Get all entity behavior patterns."""
    return ENTITY_BEHAVIOR_PATTERNS.copy()


def get_behaviors_by_type(behavior_type: EntityBehaviorType) -> List[BehaviorPattern]:
    """
    Get behavior patterns by type.

    Args:
        behavior_type: Type of behavior to filter

    Returns:
        List of matching behavior patterns
    """
    type_mapping = {
        EntityBehaviorType.MOVEMENT: [
            "move",
            "wander",
            "stroll",
            "swim",
            "fly",
            "climb",
            "jump",
            "float",
        ],
        EntityBehaviorType.COMBAT: ["attack", "melee", "ranged", "panic", "hurt", "combat"],
        EntityBehaviorType.SOCIAL: ["breed", "tempt", "follow", "tame", "social"],
        EntityBehaviorType.ENVIRONMENTAL: [
            "flee",
            "avoid",
            "hide",
            "rest",
            "shelter",
            "water",
            "sun",
        ],
        EntityBehaviorType.INTERACTION: ["interact", "trade", "pickup", "item", "door"],
        EntityBehaviorType.SPECIALIZED: ["celebrate", "mount", "egg", "special"],
    }

    keywords = type_mapping.get(behavior_type, [])
    return [
        pattern
        for key, pattern in ENTITY_BEHAVIOR_PATTERNS.items()
        if any(kw in key.lower() for kw in keywords)
    ]


_unmapped_goal_count = 0


def convert_java_goal_to_bedrock(
    java_goal: Dict[str, Any],
    override_defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert a Java AI goal to Bedrock behavior component.

    Args:
        java_goal: Java goal definition with 'type' and optional 'config'
        override_defaults: Optional overrides for default config

    Returns:
        Bedrock behavior component dictionary; unmapped goals return
        {"minecraft:behavior.<unmapped>": {...}, "_unmapped": True}
    """
    global _unmapped_goal_count
    goal_type = java_goal.get("type", "").strip().lower()
    goal_config = java_goal.get("config", {})
    priority = java_goal.get("priority", None)

    pattern = get_behavior_pattern(goal_type)
    if not pattern:
        _unmapped_goal_count += 1
        unmapped_config = {"priority": priority} if priority is not None else {}
        if goal_config:
            unmapped_config["_raw_config"] = goal_config
        return {
            f"minecraft:behavior.{goal_type}": unmapped_config,
            "_unmapped": True,
        }

    result = pattern.default_config.copy()

    if goal_config:
        result.update(goal_config)

    if override_defaults:
        result.update(override_defaults)

    if priority is not None:
        result["priority"] = priority
    else:
        result["priority"] = pattern.priority

    return {pattern.bedrock_behavior: result}


def get_entity_ai_templates() -> Dict[str, Dict[str, Any]]:
    """
    Get predefined AI behavior templates for common entity types.

    Returns:
        Dictionary of entity type templates
    """
    return {
        "hostile_mob": {
            "description": "Standard hostile mob AI",
            "behaviors": [
                {"type": "melee_attack", "config": {"priority": 3}},
                {"type": "look_at_player", "config": {"priority": 5}},
                {"type": "move_towards_target", "config": {"priority": 4}},
                {"type": "wander", "config": {"priority": 6}},
                {"type": "panic", "config": {"priority": 1}},
            ],
        },
        "passive_mob": {
            "description": "Standard passive mob AI",
            "behaviors": [
                {"type": "follow_player", "config": {"priority": 6}},
                {"type": "random_look_around", "config": {"priority": 8}},
                {"type": "wander", "config": {"priority": 7}},
                {"type": "float", "config": {"priority": 0}},
            ],
        },
        "water_mob": {
            "description": "Aquatic mob AI",
            "behaviors": [
                {"type": "swim", "config": {"priority": 2}},
                {"type": "random_look_around", "config": {"priority": 6}},
                {"type": "wander", "config": {"priority": 5}},
                {"type": "flee", "config": {"priority": 3}},
            ],
        },
        "flying_mob": {
            "description": "Flying mob AI",
            "behaviors": [
                {"type": "fly", "config": {"priority": 2}},
                {"type": "look_at_player", "config": {"priority": 5}},
                {"type": "melee_attack", "config": {"priority": 3}},
                {"type": "panic", "config": {"priority": 1}},
            ],
        },
        "tameable_mob": {
            "description": "Tameable pet AI",
            "behaviors": [
                {"type": "follow_player", "config": {"priority": 5}},
                {"type": "tame", "config": {"priority": 2}},
                {"type": "look_at_player", "config": {"priority": 6}},
                {"type": "wander", "config": {"priority": 7}},
            ],
        },
        "villager": {
            "description": "Villager AI with trading",
            "behaviors": [
                {"type": "wander", "config": {"priority": 5}},
                {"type": "trade", "config": {"priority": 4}},
                {"type": "look_at_trading", "config": {"priority": 6}},
                {"type": "interact", "config": {"priority": 3}},
            ],
        },
    }


def get_behavior_stats() -> Dict[str, int]:
    """Get statistics about available behavior patterns."""
    return {
        "total_patterns": len(ENTITY_BEHAVIOR_PATTERNS),
        "movement_behaviors": len(get_behaviors_by_type(EntityBehaviorType.MOVEMENT)),
        "combat_behaviors": len(get_behaviors_by_type(EntityBehaviorType.COMBAT)),
        "social_behaviors": len(get_behaviors_by_type(EntityBehaviorType.SOCIAL)),
        "environmental_behaviors": len(get_behaviors_by_type(EntityBehaviorType.ENVIRONMENTAL)),
        "interaction_behaviors": len(get_behaviors_by_type(EntityBehaviorType.INTERACTION)),
        "specialized_behaviors": len(get_behaviors_by_type(EntityBehaviorType.SPECIALIZED)),
        "entity_templates": len(get_entity_ai_templates()),
        "unmapped_goal_count": _unmapped_goal_count,
    }


def reset_unmapped_goal_count() -> None:
    """Reset the unmapped goal counter (for testing)."""
    global _unmapped_goal_count
    _unmapped_goal_count = 0


# Export commonly used items
__all__ = [
    "EntityBehaviorType",
    "JavaAIGoal",
    "BehaviorPattern",
    "ENTITY_BEHAVIOR_PATTERNS",
    "get_behavior_pattern",
    "get_all_behavior_patterns",
    "get_behaviors_by_type",
    "convert_java_goal_to_bedrock",
    "get_entity_ai_templates",
    "get_behavior_stats",
    "reset_unmapped_goal_count",
]
