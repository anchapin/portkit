"""
Entity Converter for converting Java entities to Bedrock format.
Part of the entity/ subpackage for Issue #1276 refactoring.
Provides the same public API as the original entity_converter module.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from converters.loot_table_generator import LootTableGenerator
from converters.rendering_converter import convert_animation_controller
from converters.spawn_rule_generator import SpawnRuleGenerator

from agents.entity.attribute_mapper import (
    BASE_COMPONENTS,
    add_entity_behaviors,
    add_legacy_goal,
    apply_entity_properties,
    build_behavior_config,
)
from agents.entity.client_entity_generator import generate_client_entity
from agents.entity.nbt_parser import EntityProperties, EntityType
from agents.entity.type_registry import add_ai_goals, create_entity_description

logger = logging.getLogger(__name__)


class EntityConverter:
    """
    Converter for Java entities to Bedrock entity format.
    Handles entity definitions, behaviors, and animations.
    """

    def __init__(self):
        self.entity_template = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {
                    "identifier": "",
                    "is_spawnable": True,
                    "is_summonable": True,
                    "is_experimental": False,
                },
                "component_groups": {},
                "components": {},
                "events": {},
            },
        }

        self.spawn_rule_generator = SpawnRuleGenerator()
        self.loot_table_generator = LootTableGenerator()
        self.base_components = BASE_COMPONENTS.copy()

        self.behavior_mappings = {
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

        self.goal_mappings = {
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

    def convert_entities(self, java_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert Java entities to Bedrock format.

        Args:
            java_entities: List of Java entity definitions

        Returns:
            Dictionary of Bedrock entity definitions
        """
        logger.info(f"Converting {len(java_entities)} Java entities to Bedrock format")
        bedrock_entities = {}

        for java_entity in java_entities:
            try:
                bedrock_entity = self._convert_java_entity(java_entity)
                entity_id = bedrock_entity["minecraft:entity"]["description"]["identifier"]
                bedrock_entities[entity_id] = bedrock_entity

                spawn_rules = self.spawn_rule_generator.generate_spawn_rules(java_entity)
                if spawn_rules.get("minecraft:spawn_rules", {}).get("conditions"):
                    bedrock_entities[f"{entity_id}_spawn_rules"] = spawn_rules

                loot_table = self._generate_entity_loot_table(java_entity, entity_id)
                if loot_table:
                    bedrock_entities[f"{entity_id}_loot_table"] = loot_table

                behaviors = self._generate_entity_behaviors(java_entity)
                animations = self._generate_entity_animations(java_entity)

                if behaviors:
                    bedrock_entities[f"{entity_id}_behaviors"] = behaviors
                if animations:
                    bedrock_entities[f"{entity_id}_animations"] = animations

                animation_controllers = self._generate_animation_controllers(java_entity, entity_id)
                if animation_controllers:
                    bedrock_entities[f"{entity_id}_animation_controllers"] = animation_controllers

                # Issue #1773: emit the resource-pack client-entity definition that
                # binds this identifier to geometry/texture/material/render controllers
                # so the mob actually renders in Bedrock. Mirrors the identifier and
                # the animation-controller keys computed above to keep BP/RP in parity.
                client_entity = generate_client_entity(bedrock_entity, java_entity)
                if client_entity:
                    bedrock_entities[f"{entity_id}_client_entity"] = client_entity

            except Exception as e:
                logger.error(f"Failed to convert entity {java_entity.get('id', 'unknown')}: {e}")
                continue

        logger.info(f"Successfully converted {len(bedrock_entities)} entities")
        return bedrock_entities

    def generate_hostile_mob(self, java_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a Bedrock hostile mob definition with AI behaviors."""
        return self._create_hostile_mob_entity(java_entity)

    def generate_passive_mob(self, java_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a Bedrock passive mob definition with AI behaviors."""
        return self._create_passive_mob_entity(java_entity)

    def _create_hostile_mob_entity(self, java_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Bedrock hostile mob entity with aggressive AI behaviors."""
        entity_id = java_entity.get("id", "unknown_hostile")
        namespace = java_entity.get("namespace", "modporter")
        full_id = f"{namespace}:{entity_id}"

        properties = self._parse_java_entity_properties(java_entity)
        properties.entity_type = EntityType.HOSTILE

        bedrock_entity = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {
                    "identifier": full_id,
                    "is_spawnable": java_entity.get("spawnable", True),
                    "is_summonable": java_entity.get("summonable", True),
                    "is_experimental": False,
                },
                "component_groups": {},
                "components": {},
                "events": {},
            },
        }

        components = bedrock_entity["minecraft:entity"]["components"]
        components.update(self.base_components.copy())
        self._apply_entity_properties(components, properties)
        self._add_hostile_ai_behaviors(components, java_entity)

        if java_entity.get("can_attack", True):
            components["minecraft:attack"] = {
                "damage": properties.attack_damage if properties.attack_damage > 0 else 4.0
            }

        components["minecraft:type_family"]["family"] = ["mob", "monster", "hostile"]

        if java_entity.get("has_spawn_egg", True):
            components["minecraft:spawn_egg"] = {
                "base_color": java_entity.get("spawn_egg_primary", "#5A1D1D"),
                "overlay_color": java_entity.get("spawn_egg_secondary", "#1D1D1D"),
            }

        if "loot_table" in java_entity:
            components["minecraft:loot"] = {"table": java_entity["loot_table"]}

        return bedrock_entity

    def _create_passive_mob_entity(self, java_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Bedrock passive mob entity with peaceful AI behaviors."""
        entity_id = java_entity.get("id", "unknown_passive")
        namespace = java_entity.get("namespace", "modporter")
        full_id = f"{namespace}:{entity_id}"

        properties = self._parse_java_entity_properties(java_entity)
        properties.entity_type = EntityType.PASSIVE

        bedrock_entity = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {
                    "identifier": full_id,
                    "is_spawnable": java_entity.get("spawnable", True),
                    "is_summonable": java_entity.get("summonable", True),
                    "is_experimental": False,
                },
                "component_groups": {},
                "components": {},
                "events": {},
            },
        }

        components = bedrock_entity["minecraft:entity"]["components"]
        components.update(self.base_components.copy())
        self._apply_entity_properties(components, properties)
        self._add_passive_ai_behaviors(components, java_entity)

        if "minecraft:attack" in components:
            del components["minecraft:attack"]

        components["minecraft:type_family"]["family"] = ["mob", "passive"]

        if java_entity.get("has_spawn_egg", True):
            components["minecraft:spawn_egg"] = {
                "base_color": java_entity.get("spawn_egg_primary", "#1D5D1D"),
                "overlay_color": java_entity.get("spawn_egg_secondary", "#FFFFFF"),
            }

        if java_entity.get("can_breed", True):
            components["minecraft:behavior.breed"] = {"priority": 4}

        if java_entity.get("is_tameable", False):
            components["minecraft:tameable"] = {
                "probability": java_entity.get("tame_probability", 0.33),
                "tame_event": {"event": "minecraft:on_tame", "target": "self"},
            }

        if "loot_table" in java_entity:
            components["minecraft:loot"] = {"table": java_entity["loot_table"]}

        return bedrock_entity

    def _add_hostile_ai_behaviors(self, components: Dict[str, Any], java_entity: Dict[str, Any]):
        """Add AI behaviors specific to hostile mobs."""
        components["minecraft:behavior.melee_attack"] = {
            "priority": 3,
            "speed_multiplier": 1.0,
            "track_target": True,
            "reach_multiplier": 0.8,
        }

        components["minecraft:behavior.look_at_player"] = {
            "priority": 5,
            "look_distance": 8.0,
            "look_time": [2, 4],
        }

        components["minecraft:behavior.move_towards_target"] = {
            "priority": 4,
            "speed_multiplier": 1.0,
            "target_distance": 4.0,
        }

        components["minecraft:behavior.wander"] = {
            "priority": 6,
            "speed_multiplier": 0.8,
            "wander_distance": 10,
            "start_chance": 0.2,
        }

        components["minecraft:behavior.panic"] = {
            "priority": 1,
            "speed_multiplier": 1.25,
            "panic_sound": "mob.hostile.hurt",
        }

        if "behaviors" in java_entity:
            self._add_entity_behaviors(components, java_entity)

        if "ai_goals" in java_entity:
            self._add_ai_goals(components, java_entity["ai_goals"])

    def _add_passive_ai_behaviors(self, components: Dict[str, Any], java_entity: Dict[str, Any]):
        """Add AI behaviors specific to passive mobs."""
        components["minecraft:behavior.follow_player"] = {
            "priority": 6,
            "speed_multiplier": 1.0,
            "start_distance": 5.0,
            "stop_distance": 2.0,
        }

        components["minecraft:behavior.random_look_around"] = {
            "priority": 8,
            "look_distance": 6.0,
            "look_time": [4, 8],
        }

        components["minecraft:behavior.wander"] = {
            "priority": 7,
            "speed_multiplier": 0.5,
            "wander_distance": 5,
            "start_chance": 0.3,
        }

        components["minecraft:behavior.float"] = {"priority": 0}

        if "behaviors" in java_entity:
            self._add_entity_behaviors(components, java_entity)

        if "ai_goals" in java_entity:
            self._add_ai_goals(components, java_entity["ai_goals"])

    def _convert_java_entity(self, java_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single Java entity to Bedrock format."""
        entity_id = java_entity.get("id", "unknown_entity")
        namespace = java_entity.get("namespace", "modporter")
        full_id = f"{namespace}:{entity_id}"

        bedrock_entity = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {
                    "identifier": full_id,
                    "is_spawnable": java_entity.get("spawnable", True),
                    "is_summonable": java_entity.get("summonable", True),
                    "is_experimental": False,
                },
                "component_groups": {},
                "components": {},
                "events": {},
            },
        }

        properties = self._parse_java_entity_properties(java_entity)

        components = bedrock_entity["minecraft:entity"]["components"]
        components.update(self.base_components.copy())

        self._apply_entity_properties(components, properties)
        self._add_entity_behaviors(components, java_entity)

        if "ai_goals" in java_entity:
            self._add_ai_goals(components, java_entity["ai_goals"])

        if "loot_table" in java_entity:
            components["minecraft:loot"] = {"table": java_entity["loot_table"]}

        if java_entity.get("has_spawn_egg", False):
            components["minecraft:spawn_egg"] = {
                "base_color": java_entity.get("spawn_egg_primary", "#7F7F7F"),
                "overlay_color": java_entity.get("spawn_egg_secondary", "#FFFFFF"),
            }

        return bedrock_entity

    def _parse_java_entity_properties(self, java_entity: Dict[str, Any]) -> EntityProperties:
        """Parse Java entity properties."""
        from agents.entity.nbt_parser import parse_java_entity_properties as parse
        return parse(java_entity)

    def _apply_entity_properties(self, components: Dict[str, Any], properties: EntityProperties):
        """Apply entity properties to Bedrock components."""
        apply_entity_properties(components, properties)

    def _add_entity_behaviors(self, components: Dict[str, Any], java_entity: Dict[str, Any]):
        """Add behavior components based on Java entity behaviors."""
        add_entity_behaviors(components, java_entity)

    def _add_ai_goals(self, components: Dict[str, Any], ai_goals: List[Dict[str, Any]]):
        """Add AI goals as behavior components."""
        add_ai_goals(components, ai_goals)

    def _build_behavior_config(
        self, goal_type: str, priority: int, goal_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build Bedrock behavior config from Java goal config."""
        return build_behavior_config(goal_type, priority, goal_config)

    def _add_legacy_goal(
        self, components: Dict[str, Any], goal_type: str, priority: int, goal_config: Dict[str, Any]
    ):
        """Handle legacy goal types not in goal_mappings."""
        add_legacy_goal(components, goal_type, priority, goal_config)

    def _generate_entity_loot_table(
        self, java_entity: Dict[str, Any], entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """Generate loot table for an entity."""
        loot_table_data = java_entity.get("loot_table_data", {})

        if not loot_table_data and not java_entity.get("has_loot_table", False):
            return None

        if loot_table_data:
            return self.loot_table_generator.generate_loot_table(loot_table_data, entity_id)

        return self.loot_table_generator.generate_entity_loot_table(entity_id)

    def _generate_animation_controllers(
        self, java_entity: Dict[str, Any], entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """Generate animation controllers for an entity."""
        controllers = java_entity.get("animation_controllers", [])
        if not controllers:
            return None

        result = {"format_version": "1.19.0", "animation_controllers": {}}

        for controller in controllers:
            try:
                converted = convert_animation_controller(controller)
                controller_id = converted.identifier
                result["animation_controllers"][controller_id] = {
                    "initial_state": converted.initial_state,
                    "states": converted.states,
                }
            except Exception as e:
                logger.warning(f"Failed to convert animation controller: {e}")
                continue

        return result["animation_controllers"] or None

    def convert_ai_goals(self, java_goals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Convert Java AI goals to Bedrock behaviors.

        Args:
            java_goals: List of Java AI goal definitions

        Returns:
            Dictionary of Bedrock behavior components
        """
        from agents.entity.type_registry import convert_ai_goals as convert
        return convert(java_goals)

    def _generate_entity_behaviors(self, java_entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate separate behavior file for complex entities."""
        return None

    def _generate_entity_animations(self, java_entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate animation definitions for entities."""
        animations = java_entity.get("animations", [])
        if not animations:
            return None

        animation_definitions = {"format_version": "1.19.0", "animations": {}}

        for animation in animations:
            anim_name = animation.get("name", "default")
            animation_definitions["animations"][
                f"animation.{java_entity.get('id', 'entity')}.{anim_name}"
            ] = {
                "loop": animation.get("loop", False),
                "animation_length": animation.get("length", 1.0),
                "bones": animation.get("bones", {}),
            }

        return animation_definitions if animation_definitions["animations"] else None

    def write_entities_to_disk(
        self, entities: Dict[str, Any], bp_path: Path, rp_path: Path
    ) -> Dict[str, List[Path]]:
        """
        Write entity definitions to disk.

        Args:
            entities: Dictionary of entity definitions
            bp_path: Behavior pack path
            rp_path: Resource pack path

        Returns:
            Dictionary of written file paths
        """
        written_files = {
            "entities": [],
            "behaviors": [],
            "animations": [],
            "spawn_rules": [],
            "loot_tables": [],
            "entities_rp": [],
        }

        bp_entities_dir = bp_path / "entities"
        bp_entities_dir.mkdir(parents=True, exist_ok=True)

        rp_entity_dir = rp_path / "entity"
        rp_entity_dir.mkdir(parents=True, exist_ok=True)

        bp_spawn_rules_dir = bp_path / "spawn_rules"
        bp_spawn_rules_dir.mkdir(parents=True, exist_ok=True)
        bp_loot_tables_dir = bp_path / "loot_tables" / "entities"
        bp_loot_tables_dir.mkdir(parents=True, exist_ok=True)

        for entity_key, entity_data in entities.items():
            try:
                if entity_key.endswith("_spawn_rules"):
                    entity_id = entity_key.replace("_spawn_rules", "")
                    spawn_rules_file = bp_spawn_rules_dir / f"{entity_id.split(':')[-1]}.json"
                    with open(spawn_rules_file, "w", encoding="utf-8") as f:
                        json.dump(entity_data, f, indent=2, ensure_ascii=False)
                    written_files["spawn_rules"].append(spawn_rules_file)

                elif entity_key.endswith("_loot_table"):
                    entity_id = entity_key.replace("_loot_table", "")
                    loot_table_file = bp_loot_tables_dir / f"{entity_id.split(':')[-1]}.json"
                    with open(loot_table_file, "w", encoding="utf-8") as f:
                        json.dump(entity_data, f, indent=2, ensure_ascii=False)
                    written_files["loot_tables"].append(loot_table_file)

                elif entity_key.endswith("_behaviors"):
                    entity_id = entity_key.replace("_behaviors", "")
                    behavior_file = bp_entities_dir / f"{entity_id.split(':')[-1]}_behaviors.json"
                    with open(behavior_file, "w", encoding="utf-8") as f:
                        json.dump(entity_data, f, indent=2, ensure_ascii=False)
                    written_files["behaviors"].append(behavior_file)

                elif entity_key.endswith("_animations"):
                    entity_id = entity_key.replace("_animations", "")
                    anim_file = rp_entity_dir / f"{entity_id.split(':')[-1]}_animations.json"
                    with open(anim_file, "w", encoding="utf-8") as f:
                        json.dump(entity_data, f, indent=2, ensure_ascii=False)
                    written_files["animations"].append(anim_file)

                elif entity_key.endswith("_client_entity"):
                    # Issue #1773: write the resource-pack client-entity
                    # definition (minecraft:client_entity) that wires
                    # geometry/texture/material/render controllers so the
                    # mob renders in Bedrock.
                    entity_id = entity_key.replace("_client_entity", "")
                    client_file = rp_entity_dir / f"{entity_id.split(':')[-1]}.entity.json"
                    with open(client_file, "w", encoding="utf-8") as f:
                        json.dump(entity_data, f, indent=2, ensure_ascii=False)
                    written_files["entities_rp"].append(client_file)

                else:
                    entity_file = bp_entities_dir / f"{entity_key.split(':')[-1]}.json"
                    with open(entity_file, "w", encoding="utf-8") as f:
                        json.dump(entity_data, f, indent=2, ensure_ascii=False)
                    written_files["entities"].append(entity_file)

            except Exception as e:
                logger.error(f"Failed to write entity {entity_key}: {e}")
                continue

        logger.info(
            f"Written {len(written_files['entities'])} entities, "
            f"{len(written_files['behaviors'])} behaviors, "
            f"{len(written_files['animations'])} animations, "
            f"{len(written_files['spawn_rules'])} spawn_rules, "
            f"{len(written_files['loot_tables'])} loot_tables, "
            f"{len(written_files['entities_rp'])} client_entities to disk"
        )

        return written_files


class EntityType:
    """Entity type enum for backward compatibility."""
    PASSIVE = "passive"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    BOSS = "boss"
    AMBIENT = "ambient"
    MISC = "misc"


class MobCategory:
    """Mob category enum for backward compatibility."""
    HOSTILE = "hostile"
    PASSIVE = "passive"
    NEUTRAL = "neutral"
    BOSS = "boss"