"""
Attribute Mapper for mapping Java entity attributes to Bedrock entity components.
Part of the entity/ subpackage for Issue #1276 refactoring.
"""

from typing import Any, Dict, List

from agents.entity.nbt_parser import EntityProperties, EntityType


BASE_COMPONENTS = {
    "minecraft:type_family": {"family": ["mob"]},
    "minecraft:collision_box": {"width": 0.6, "height": 1.8},
    "minecraft:health": {"value": 20, "max": 20},
    "minecraft:movement": {"value": 0.25},
    "minecraft:navigation.walk": {
        "can_path_over_water": True,
        "avoid_water": True,
        "avoid_damage_at_all_costs": True,
    },
    "minecraft:movement.basic": {},
    "minecraft:jump.static": {},
    "minecraft:can_climb": {},
    "minecraft:physics": {},
}

BEHAVIOR_MAPPINGS = {
    "follow_player": "minecraft:behavior.follow_player",
    "follow_owner": "minecraft:behavior.follow_owner",
    "look_at_player": "minecraft:behavior.look_at_player",
    "random_look_around": "minecraft:behavior.random_look_around",
    "random_stroll": "minecraft:behavior.random_stroll",
    "random_float": "minecraft:behavior.float",
    "float": "minecraft:behavior.float",
    "swim": "minecraft:behavior.swim",
    "fly": "minecraft:behavior.fly",
    "wander": "minecraft:behavior.wander",
    "move_towards_target": "minecraft:behavior.move_towards_target",
    "move_through_village": "minecraft:behavior.move_through_village",
    "move_to_land": "minecraft:behavior.move_to_land",
    "mount_pathing": "minecraft:behavior.mount_pathing",
    "panic": "minecraft:behavior.panic",
    "melee_attack": "minecraft:behavior.melee_attack",
    "ranged_attack": "minecraft:behavior.ranged_attack",
    "attack_entity": "minecraft:behavior.attack_entity",
    "attack_with_range": "minecraft:behavior.attack_with_range",
    "knockback_roar": "minecraft:behavior.knockback_roar",
    "charge_attack": "minecraft:behavior.charge",
    "strafing": "minecraft:behavior.strafe",
    "siege": "minecraft:behavior.siege",
    "breed": "minecraft:behavior.breed",
    "tempt": "minecraft:behavior.tempt",
    "nudge": "minecraft:behavior.nudge",
    "celebrate": "minecraft:behavior.celebrate",
    "get_angry": "minecraft:behavior.get_angry",
    "become_angry": "minecraft:behavior.become_angry",
    "avoid_entity": "minecraft:behavior.avoid_entity",
    "avoid_block": "minecraft:behavior.avoid_block",
    "flee_sun": "minecraft:behavior.flee_sun",
    "restrict_sun": "minecraft:behavior.restrict_sun",
    "seek_shelter": "minecraft:behavior.seek_shelter",
    "leave_water": "minecraft:behavior.leave_water",
    "play_dead": "minecraft:behavior.play_dead",
    "tame": "minecraft:behavior.tame",
    "owner_hurt_by_target": "minecraft:behavior.owner_hurt_by_target",
    "owner_hurt_target": "minecraft:behavior.owner_hurt_target",
    "leash": "minecraft:behavior.leash",
    "unleash": "minecraft:behavior.unleash",
    "equipped_item_chance": "minecraft:behavior.equipped_item_chance",
    "find_mount": "minecraft:behavior.find_mount",
    "jump_to_block": "minecraft:behavior.jump_to_block",
    "lay_spawn": "minecraft:behavior.lay_spawn",
    "lay_egg": "minecraft:behavior.lay_egg",
    "item_consume": "minecraft:behavior.item_consume",
    "pickup_items": "minecraft:behavior.pickup_items",
    "trade": "minecraft:behavior.trade_with_player",
    "look_at_trading": "minecraft:behavior.look_at_trading",
    "interact": "minecraft:behavior.interact",
    "ocelot_sneeze": "minecraft:behavior.ocelot_sneeze",
    "parrot_poop": "minecraft:behavior.parrot_poop",
    "ram_attack": "minecraft:behavior.ram_attack",
    "skeleton_ride": "minecraft:behavior.skeleton_ride",
    "swell": "minecraft:behavior.swell",
    "spit": "minecraft:behavior.spit",
    "vex_copy_owner_target": "minecraft:behavior.vex_copy_owner_target",
    "fish_jump": "minecraft:behavior.fish_jump",
    "flop": "minecraft:behavior.flop",
}

GOAL_MAPPINGS = {
    "move": "minecraft:behavior.move_towards_target",
    "wander": "minecraft:behavior.wander",
    "stroll": "minecraft:behavior.wander",
    "swim": "minecraft:behavior.swim",
    "fly": "minecraft:behavior.fly",
    "climb": "minecraft:behavior.climb",
    "jump": "minecraft:behavior.jump",
    "float": "minecraft:behavior.float",
    "look_at_player": "minecraft:behavior.look_at_player",
    "look_at_target": "minecraft:behavior.look_at_target",
    "look_randomly": "minecraft:behavior.random_look_around",
    "melee_attack": "minecraft:behavior.melee_attack",
    "ranged_attack": "minecraft:behavior.attack_with_range",
    "hurt_target": "minecraft:behavior.attack_entity",
    "attack": "minecraft:behavior.melee_attack",
    "breed": "minecraft:behavior.breed",
    "tempt": "minecraft:behavior.tempt",
    "follow": "minecraft:behavior.follow_player",
    "tame": "minecraft:behavior.tame",
    "panic": "minecraft:behavior.panic",
    "flee": "minecraft:behavior.avoid_entity",
    "avoid": "minecraft:behavior.avoid_entity",
    "hide": "minecraft:behavior.seek_shelter",
    "rest": "minecraft:behavior.restrict_sun",
    "seek_water": "minecraft:behavior.leave_water",
    "interact": "minecraft:behavior.interact",
    "trade": "Offers:behavior.trade_with_player",
    "open_door": "minecraft:behavior.door_interact",
    "use_item": "minecraft:behavior.item_consume",
    "pickup": "minecraft:behavior.pickup_items",
    "celebrate": "minecraft:behavior.celebrate",
    "eat": "minecraft:behavior.item_consume",
    "graze": "minecraft:behavior.graze",
    "sleep": "minecraft:behavior.sleep",
    "raid": "minecraft:behavior.raid",
}

LEGACY_GOAL_MAPPINGS = {
    "move": "minecraft:behavior.move_towards_target",
    "look": "minecraft:behavior.look_at_player",
    "swim": "minecraft:behavior.swim",
    "fly": "minecraft:behavior.fly",
    "climb": "minecraft:behavior.climb",
    "jump": "minecraft:behavior.jump",
    "flee": "minecraft:behavior.avoid_entity",
    "hide": "minecraft:behavior.seek_shelter",
    "rest": "minecraft:behavior.restrict_sun",
    "seek_water": "minecraft:behavior.leave_water",
    "breed": "minecraft:behavior.breed",
    "tempt": "minecraft:behavior.tempt",
    "interact": "minecraft:behavior.interact",
    "trade": "Offers:behavior.trade_with_player",
    "pickup": "minecraft:behavior.pickup_items",
    "eat": "minecraft:behavior.item_consume",
}


def apply_entity_properties(components: Dict[str, Any], properties: EntityProperties) -> None:
    """
    Apply entity properties to Bedrock components.

    Args:
        components: Bedrock entity components dict
        properties: EntityProperties with parsed values
    """
    components["minecraft:health"]["value"] = properties.health
    components["minecraft:health"]["max"] = properties.health
    components["minecraft:movement"]["value"] = properties.movement_speed

    if properties.attack_damage > 0:
        components["minecraft:damage"] = {
            "range": [properties.attack_damage, properties.attack_damage]
        }
        components["minecraft:attack"] = {"damage": properties.attack_damage}

    if properties.armor > 0:
        components["minecraft:damage_sensor"] = {
            "triggers": [
                {
                    "cause": "all",
                    "damage_modifier": -(properties.armor * 4),
                }
            ]
        }

    if properties.knockback_resistance > 0:
        components["minecraft:knockback_resistance"] = {"value": properties.knockback_resistance}

    if not properties.can_swim:
        components["minecraft:navigation.walk"]["avoid_water"] = True

    if properties.can_climb:
        components["minecraft:can_climb"] = {}

    if properties.can_fly:
        components["minecraft:can_fly"] = {}
        components["minecraft:movement.fly"] = {}

    if not properties.breathes_air:
        components["minecraft:breathable"] = {
            "breathes_air": False,
            "breathes_water": properties.breathes_water,
            "generates_bubbles": False,
        }

    if not properties.pushable:
        components["minecraft:pushable"] = {
            "is_pushable": False,
            "is_pushable_by_piston": False,
        }

    type_families = ["mob"]
    if properties.entity_type == EntityType.HOSTILE:
        type_families.extend(["monster", "hostile"])
    elif properties.entity_type == EntityType.PASSIVE:
        type_families.append("passive")
    elif properties.entity_type == EntityType.NEUTRAL:
        type_families.append("neutral")
    elif properties.entity_type == EntityType.BOSS:
        type_families.extend(["boss", "hostile"])

    components["minecraft:type_family"]["family"] = type_families


def add_entity_behaviors(components: Dict[str, Any], java_entity: Dict[str, Any]) -> None:
    """
    Add behavior components based on Java entity behaviors.

    Args:
        components: Bedrock entity components dict
        java_entity: Java entity definition
    """
    behaviors = java_entity.get("behaviors", [])

    for behavior in behaviors:
        behavior_type = behavior.get("type", "")
        bedrock_behavior = BEHAVIOR_MAPPINGS.get(behavior_type)

        if bedrock_behavior:
            behavior_config = behavior.get("config", {})
            components[bedrock_behavior] = behavior_config


def build_behavior_config(
    goal_type: str, priority: int, goal_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build Bedrock behavior config from Java goal config.

    Args:
        goal_type: The goal type (e.g., "melee_attack")
        priority: Goal priority
        goal_config: Goal-specific configuration

    Returns:
        Bedrock behavior configuration dict
    """
    config = {"priority": priority}

    speed_mappings = ["speed", "speed_multiplier", "movement_speed"]
    for key in speed_mappings:
        if key in goal_config:
            config["speed_multiplier"] = goal_config[key]
            break
    else:
        if goal_type in ["melee_attack", "attack", "hurt_target"]:
            config["speed_multiplier"] = 1.0
        elif goal_type in ["follow", "follow_player"]:
            config["speed_multiplier"] = 1.0
        elif goal_type in ["wander", "stroll", "random_stroll"]:
            config["speed_multiplier"] = 0.8
        elif goal_type in ["panic", "flee", "avoid"]:
            config["speed_multiplier"] = 1.25

    if "range" in goal_config:
        if goal_type in ["look_at_player", "look", "look_at_target"]:
            config["look_distance"] = goal_config["range"]
        elif goal_type in ["ranged_attack", "attack_with_range"]:
            config["attack_radius"] = goal_config["range"]
        elif goal_type in ["tempt", "follow"]:
            config["within_radius"] = goal_config["range"]

    if "distance" in goal_config:
        if goal_type in ["follow", "follow_player"]:
            config["start_distance"] = goal_config["distance"]
            config["stop_distance"] = goal_config.get("stop_distance", goal_config["distance"] / 2)

    if goal_type in ["melee_attack", "attack", "attack_entity"]:
        config["track_target"] = goal_config.get("track_target", True)

    if "reach_multiplier" in goal_config:
        config["reach_multiplier"] = goal_config["reach_multiplier"]

    for key, value in goal_config.items():
        if key not in [
            "priority",
            "speed",
            "speed_multiplier",
            "movement_speed",
            "range",
            "distance",
            "stop_distance",
            "track_target",
            "reach_multiplier",
        ]:
            config[key] = value

    return config


def add_legacy_goal(
    components: Dict[str, Any], goal_type: str, priority: int, goal_config: Dict[str, Any]
) -> None:
    """
    Handle legacy goal types not in goal_mappings.

    Args:
        components: Bedrock entity components dict
        goal_type: The legacy goal type
        priority: Goal priority
        goal_config: Goal-specific configuration
    """
    bedrock_behavior = LEGACY_GOAL_MAPPINGS.get(goal_type)
    if bedrock_behavior:
        config = {"priority": priority}
        if "speed" in goal_config:
            config["speed_multiplier"] = goal_config["speed"]
        if "range" in goal_config:
            config["look_distance"] = goal_config["range"]
        components[bedrock_behavior] = config
