"""
Minecraft Contract - Schema validation and automatic repair for Bedrock code.

Implements a contract-based validation system inspired by GeoContra's geospatial
contract framework. Enforces game-logic rules and schema validity during translation
from Java to Bedrock Minecraft add-ons.

Key contract rules:
- Entity component nesting (events must be inside entity definitions)
- Coordinate semantics for spawn rules
- Component required vs optional fields
- Value ranges for numeric properties (e.g., damage 0-32767)
- Event handler validity (must match Script API surface)
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ContractViolation:
    severity: Severity
    message: str
    location: str
    suggestion: str
    rule_id: str
    contract_type: str = "minecraft_contract"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value if isinstance(self.severity, Enum) else self.severity,
            "message": self.message,
            "location": self.location,
            "suggestion": self.suggestion,
            "rule_id": self.rule_id,
            "contract_type": self.contract_type,
        }


VALID_SCRIPT_API_METHODS = {
    "Entity": {
        "addTag",
        "getTags",
        "removeTag",
        "hasTag",
        "getId",
        "getRotation",
        "setRotation",
        "getVelocity",
        "setVelocity",
        "getPosition",
        "setPosition",
        "dimension",
        "kill",
        "isValid",
        "matches",
        "name",
        "hasComponent",
        "getComponent",
        "getComponents",
        "applyDamage",
        "getEntityData",
    },
    "Player": {
        "addTag",
        "getTags",
        "removeTag",
        "hasTag",
        "getId",
        "getRotation",
        "setRotation",
        "getVelocity",
        "setVelocity",
        "getPosition",
        "setPosition",
        "dimension",
        "kill",
        "isValid",
        "matches",
        "name",
        "hasComponent",
        "getComponent",
        "getComponents",
        "applyDamage",
        "getEntityData",
        "sendMessage",
        "getInventory",
        "isSneaking",
        "isSprinting",
    },
    "World": {
        "getAllEntities",
        "getEntities",
        "getBlock",
        "getDimension",
        "setBlock",
        "getPlayers",
        "getEntity",
        "broadcastMessage",
        "getTime",
    },
    "Block": {
        "getId",
        "getType",
        "setType",
        "getPosition",
        "isAir",
        "isLiquid",
        "getRedstonePower",
        "getBlockData",
    },
    "ItemStack": {
        "amount",
        "setAmount",
        "getId",
        "getName",
        "setName",
        "isStackable",
        "clone",
        "getMaxAmount",
    },
    "Container": {
        "addItem",
        "getItem",
        "setItem",
        "removeItem",
        "clear",
        "getSize",
        "getSlot",
        "setSlot",
    },
    "Dimension": {
        "getBlock",
        "spawnEntity",
        "getEntities",
        "getPlayers",
        "getTime",
        "setTime",
        "getWeather",
        "setWeather",
    },
    "Location": {
        "x",
        "y",
        "z",
        "dimension",
        "distance",
        "clone",
        "add",
        "subtract",
    },
    "Vector3": {
        "x",
        "y",
        "z",
        "length",
        "normalize",
        "add",
        "subtract",
        "multiply",
        "dot",
        "cross",
    },
}

COMPONENT_SCHEMA = {
    "minecraft:entity": {
        "required_fields": ["description", "components", "events"],
        "events": {"required": True, "type": "object"},
        "components": {"required": True, "type": "object"},
    },
    "minecraft:block": {
        "required_fields": ["description", "components"],
        "components": {"required": True, "type": "object"},
    },
    "minecraft:item": {
        "required_fields": ["description", "components"],
        "components": {"required": True, "type": "object"},
    },
}

ENTITY_COMPONENTS = {
    "minecraft:health",
    "minecraft:health_scaling",
    "minecraft:attack",
    "minecraft:burning",
    "minecraft:falling",
    "minecraft:fire_immune",
    "minecraft:flying",
    "minecraft:pushable",
    "minecraft:pushable_by_piston",
    "minecraft:loot",
    "minecraft:equipment",
    "minecraft:equippable",
    "minecraft:interact",
    "minecraft:behavior",
    "minecraft:movement",
    "minecraft:navigation",
    "minecraft:physics",
    "minecraft:spawn_conditions",
}

NUMERIC_RANGES = {
    "damage": (0, 32767),
    "health": (0, 2048),
    "max_stack_size": (1, 127),
    "armor_bonus": (0, 127),
    "attack_damage": (0, 32767),
    "movement_speed": (0.0, 10.0),
    "knockback_resistance": (0.0, 1.0),
    "scale": (0.001, 10.0),
    "player_step_height": (0.0, 10.0),
}

COORDINATE_SCHEMA = {
    "x": {"type": "number", "min": -30000000, "max": 30000000},
    "y": {"type": "number", "min": -64, "max": 320},
    "z": {"type": "number", "min": -30000000, "max": 30000000},
}

VALID_BEDROCK_BEHAVIORS: set = {
    "minecraft:behavior.acquiring_target",
    "minecraft:behavior.admire_item",
    "minecraft:behavior.avoid_block",
    "minecraft:behavior.avoid_entity",
    "minecraft:behavior.barter",
    "minecraft:behavior.behavior",
    "minecraft:behavior.beg",
    "minecraft:behavior.break_door",
    "minecraft:behavior.breed",
    "minecraft:behavior.celebrate",
    "minecraft:behavior.charge",
    "minecraft:behavior.claim",
    "minecraft:behavior.tempt",
    "minecraft:behavior.look_at",
    "minecraft:behavior.look_at_player",
    "minecraft:behavior.look_at_trading",
    "minecraft:behavior.melee_attack",
    "minecraft:behavior.mount_pathing",
    "minecraft:behavior.move_to_land",
    "minecraft:behavior.move_through_village",
    "minecraft:behavior.move_towards_target",
    "minecraft:behavior.nectar_gathering",
    "minecraft:behavior.nearest_attackable",
    "minecraft:behavior.nearest_entity",
    "minecraft:behavior.ocelot_sneeze",
    "minecraft:behavior.offer_flower",
    "minecraft:behavior.open_door",
    "minecraft:behavior.parent",
    "minecraft:behavior.panic",
    "minecraft:behavior.parrot_poop",
    "minecraft:behavior.perch",
    "minecraft:behavior.pet_sleep_with_owner",
    "minecraft:behavior.pickup_items",
    "minecraft:behavior.player_water_transport",
    "minecraft:behavior.raid_garden",
    "minecraft:behavior.random_look_around",
    "minecraft:behavior.random_stroll",
    "minecraft:behavior.ride_tamed_horse",
    "minecraft:behavior.skeleton_ride",
    "minecraft:behavior.sleep",
    "minecraft:behavior.slime_attack",
    "minecraft:behavior.spin_attack",
    "minecraft:behavior.stay_while_sitting",
    "minecraft:behavior.stomp",
    "minecraft:behavior.strider_wander",
    "minecraft:behavior.swell",
    "minecraft:behavior.take_flower",
    "minecraft:behavior.tame",
    "minecraft:behavior.target_nearest",
    "minecraft:behavior.target_when_pushed",
    "minecraft:behavior.trade_interest",
    "minecraft:behavior.trade_with_player",
    "minecraft:behavior.villager_baby",
    "minecraft:behavior.villager_work",
    "minecraft:behavior.walk_towards_point",
    "minecraft:behavior.walk_back_home",
    "minecraft:behavior.wander",
    "minecraft:behavior.wolf_defend_owner",
    "minecraft:behavior.vex_copy_owner_target",
    "minecraft:behavior.jump_to_block",
    "minecraft:behavior.lay_spawn",
    "minecraft:behavior.lay_egg",
    "minecraft:behavior.item_consume",
    "minecraft:behavior.interact",
    "minecraft:behavior.fish_jump",
    "minecraft:behavior.flop",
    "minecraft:behavior.float",
    "minecraft:behavior.fly",
    "minecraft:behavior.follow_entity",
    "minecraft:behavior.follow_owner",
    "minecraft:behavior.follow_player",
    "minecraft:behavior.flee_sun",
    "minecraft:behavior.freeze",
    "minecraft:behavior.get_angry",
    "minecraft:behavior.graze",
    "minecraft:behavior.guardian_attack",
    "minecraft:behavior.hero_of_the_village",
    "minecraft:behavior.honey_consume",
    "minecraft:behavior.horse_walk",
    "minecraft:behavior.hunt",
    "minecraft:behavior.investigate_suspicious",
    "minecraft:behavior.irongolem_walk",
    "minecraft:behavior.jump",
    "minecraft:behavior.leap_at_target",
    "minecraft:behavior.leash",
    "minecraft:behavior.leave_water",
    "minecraft:behavior.limited_water_temperature",
    "minecraft:behavior.llama_trade",
    "minecraft:behavior.love",
    "minecraft:behavior.mark_territory",
    "minecraft:behavior.mate",
    "minecraft:behavior.minecd",
    "minecraft:behavior.modify_sentence",
    "minecraft:behavior.mount_pathing",
    "minecraft:behavior.move_towards_target",
    "minecraft:behavior.nearest_prioritized",
    "minecraft:behavior.neighbor_check",
    "minecraft:behavior.npc_work",
    "minecraft:behavior.ocelot_sneeze",
    "minecraft:behavior.other_selected",
    "minecraft:behavior.owner_hurt_by_target",
    "minecraft:behavior.owner_hurt_target",
    "minecraft:behavior.panic",
    "minecraft:behavior.parent",
    "minecraft:behavior.peak",
    "minecraft:behavior.people_automation",
    "minecraft:behavior.pet_sleep_with_owner",
    "minecraft:behavior.pickup_items",
    "minecraft:behavior.play_dead",
    "minecraft:behavior.player_water_transport",
    "minecraft:behavior.raid_garden",
    "minecraft:behavior.random_look_around",
    "minecraft:behavior.random_sitting",
    "minecraft:behavior.random_stroll",
    "minecraft:behavior.receive_love",
    "minecraft:behavior.relax_on_owner",
    "minecraft:behavior.ride_tamed_horse",
    "minecraft:behavior.rise_and_walk",
    "minecraft:behavior.sandstorm",
    "minecraft:behavior.search_for_interesting_door_to_open",
    "minecraft:behavior.seek_shelter",
    "minecraft:behavior.shared_pathing",
    "minecraft:behavior.shear",
    "minecraft:behavior.shelter",
    "minecraft:behavior.silverfish_wake_up_friends",
    "minecraft:behavior.skeleton_ranged_attack",
    "minecraft:behavior.sleep",
    "minecraft:behavior.slime_float",
    "minecraft:behavior.smooth_sitting",
    "minecraft:behavior.snacking",
    "minecraft:behavior.sneak",
    "minecraft:behavior.sniff",
    "minecraft:behavior.stalk",
    "minecraft:behavior.stay_while_sitting",
    "minecraft:behavior.stomp",
    "minecraft:behavior.strider_wander",
    "minecraft:behavior.swim",
    "minecraft:behavior.swim_in_water",
    "minecraft:behavior.take_flower",
    "minecraft:behavior.tame",
    "minecraft:behavior.target_nearest",
    "minecraft:behavior.target_when_pushed",
    "minecraft:behavior.tempt",
    "minecraft:behavior.trade_interest",
    "minecraft:behavior.trade_with_player",
    "minecraft:behavior.unequip",
    "minecraft:behavior.unleash",
    "minecraft:behavior.vex_copy_owner_target",
    "minecraft:behavior.walk_back_home",
    "minecraft:behavior.walk_towards_point",
    "minecraft:behavior.wander",
    "minecraft:behavior.warden_walk",
    "minecraft:behavior.wolf_defend_owner",
    "minecraft:behavior.wolf_seduce",
    "minecraft:behavior.zombie_attack",
    "minecraft:behavior.door_interact",
    "minecraft:behavior.strafe",
    "minecraft:behavior.siege",
    "minecraft:behavior.nudge",
    "minecraft:behavior.become_angry",
    "minecraft:behavior.equipped_item_chance",
    "minecraft:behavior.find_mount",
    "minecraft:behavior.ram_attack",
    "minecraft:behavior.spit",
    "minecraft:behavior.swell",
    "Offers:behavior.trade_with_player",
}

SPAWN_RULE_COORDS = {
    "x": {"type": "integer", "min": -30000000, "max": 30000000},
    "y": {"type": "integer", "min": -64, "max": 320},
    "z": {"type": "integer", "min": -30000000, "max": 30000000},
}


@dataclass
class MinecraftContract:
    strict_mode: bool = True
    max_violations: int = 100
    repair_threshold: int = 5

    def __post_init__(self):
        self.violations: List[ContractViolation] = []

    def validate_bedrock_json(
        self, data: Dict[str, Any], file_path: str
    ) -> Tuple[bool, List[ContractViolation]]:
        self.violations = []
        self._validate_entity_nesting(data, file_path)
        self._validate_component_fields(data, file_path)
        self._validate_numeric_ranges(data, file_path)
        self._validate_coordinate_semantics(data, file_path)
        self._validate_entity_behaviors(data, file_path)
        passed = len(self.violations) == 0
        return passed, self.violations

    def validate_bedrock_file(self, file_path: Path) -> Tuple[bool, List[ContractViolation]]:
        self.violations = []
        try:
            content = json.loads(file_path.read_text(encoding="utf-8"))
            return self.validate_bedrock_json(content, str(file_path))
        except json.JSONDecodeError as e:
            self.violations.append(
                ContractViolation(
                    severity=Severity.CRITICAL,
                    message=f"Invalid JSON: {e}",
                    location=str(file_path),
                    suggestion="Fix JSON syntax errors",
                    rule_id="json_syntax",
                )
            )
            return False, self.violations
        except Exception as e:
            self.violations.append(
                ContractViolation(
                    severity=Severity.CRITICAL,
                    message=f"Failed to read file: {e}",
                    location=str(file_path),
                    suggestion="Check file permissions and format",
                    rule_id="file_read",
                )
            )
            return False, self.violations

    def validate_directory(
        self, dir_path: Path, pattern: str = "*.json"
    ) -> Tuple[bool, List[ContractViolation]]:
        all_violations = []
        for file_path in dir_path.rglob(pattern):
            _, violations = self.validate_bedrock_file(file_path)
            all_violations.extend(violations)
            if len(all_violations) >= self.max_violations:
                break
        return len(all_violations) == 0, all_violations

    def validate_script_api(
        self, script_content: str, file_path: str
    ) -> Tuple[bool, List[ContractViolation]]:
        self.violations = []
        self._extract_and_validate_api_calls(script_content, file_path)
        passed = len(self.violations) == 0
        return passed, self.violations

    def validate_script_file(self, file_path: Path) -> Tuple[bool, List[ContractViolation]]:
        self.violations = []
        try:
            content = file_path.read_text(encoding="utf-8")
            return self.validate_script_api(content, str(file_path))
        except Exception as e:
            self.violations.append(
                ContractViolation(
                    severity=Severity.CRITICAL,
                    message=f"Failed to read script file: {e}",
                    location=str(file_path),
                    suggestion="Check file permissions",
                    rule_id="file_read",
                )
            )
            return False, self.violations

    def _extract_and_validate_api_calls(self, content: str, file_path: str) -> None:
        api_pattern = re.compile(r"(\w+)\.(\w+)\s*\(")
        matches = api_pattern.findall(content)
        valid_objects_lower = {k.lower(): k for k in VALID_SCRIPT_API_METHODS}
        for obj, method in matches:
            obj_lower = obj.lower()
            if obj_lower in valid_objects_lower:
                canonical = valid_objects_lower[obj_lower]
                if method not in VALID_SCRIPT_API_METHODS[canonical]:
                    self.violations.append(
                        ContractViolation(
                            severity=Severity.MEDIUM,
                            message=f"Unknown method '{method}' on Script API object '{obj}'",
                            location=f"{file_path}",
                            suggestion=f"Use a valid method from {canonical}. Valid methods: {', '.join(list(VALID_SCRIPT_API_METHODS[canonical])[:10])}...",
                            rule_id="script_api_method",
                        )
                    )
            elif obj_lower not in [
                "console",
                "json",
                "math",
                "array",
                "object",
                "string",
                "number",
                "boolean",
                "promise",
                "module",
                "require",
                "exports",
            ]:
                common_props = {
                    "afterEvents",
                    "beforeEvents",
                    "getEntity",
                    "subscribe",
                    "unsubscribe",
                    "then",
                    "catch",
                    "finally",
                    "on",
                    "off",
                    "once",
                    "emit",
                    "listen",
                }
                if method in common_props:
                    continue
                self.violations.append(
                    ContractViolation(
                        severity=Severity.LOW,
                        message=f"Unknown object '{obj}' - not in Script API surface",
                        location=f"{file_path}",
                        suggestion=f"Verify '{obj}' is a valid Script API object",
                        rule_id="script_api_object",
                    )
                )

    def _validate_entity_nesting(self, data: Dict[str, Any], file_path: str) -> None:
        if not isinstance(data, dict):
            return
        if "minecraft:entity" in data:
            entity = data["minecraft:entity"]
            if "events" in entity and "components" not in entity:
                self.violations.append(
                    ContractViolation(
                        severity=Severity.HIGH,
                        message="Events defined outside entity components",
                        location=f"{file_path}:minecraft:entity",
                        suggestion="Move events inside the entity definition under the 'components' key or ensure components are defined",
                        rule_id="entity_event_nesting",
                    )
                )
        for value in data.values():
            if isinstance(value, dict):
                self._validate_entity_nesting(value, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._validate_entity_nesting(item, file_path)

    def _validate_entity_behaviors(self, data: Dict[str, Any], file_path: str) -> None:
        if not isinstance(data, dict):
            return
        if "minecraft:entity" in data:
            entity = data["minecraft:entity"]
            if isinstance(entity, dict):
                components = entity.get("components", {})
                if isinstance(components, dict):
                    self._check_behavior_components(components, file_path)
                component_groups = entity.get("component_groups", {})
                if isinstance(component_groups, dict):
                    for group in component_groups.values():
                        if isinstance(group, dict):
                            group_components = group.get("components", {})
                            if isinstance(group_components, dict):
                                self._check_behavior_components(group_components, file_path)
        for value in data.values():
            if isinstance(value, dict):
                self._validate_entity_behaviors(value, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._validate_entity_behaviors(item, file_path)

    def _check_behavior_components(self, components: Dict[str, Any], file_path: str) -> None:
        for key in components:
            if key.startswith("minecraft:behavior."):
                if key not in VALID_BEDROCK_BEHAVIORS:
                    self.violations.append(
                        ContractViolation(
                            severity=Severity.HIGH,
                            message=f"Unknown entity behavior '{key}' is not a valid Bedrock behavior",
                            location=f"{file_path}:{key}",
                            suggestion=f"Remove '{key}' or replace with a valid Bedrock behavior component. See Bedrock entity behavior documentation.",
                            rule_id="entity_behavior_contract",
                        )
                    )

    def _validate_component_fields(self, data: Dict[str, Any], file_path: str) -> None:
        if not isinstance(data, dict):
            return
        for key, schema in COMPONENT_SCHEMA.items():
            if key in data:
                component = data[key]
                if isinstance(component, dict):
                    for req_field in schema.get("required_fields", []):
                        if req_field not in component:
                            self.violations.append(
                                ContractViolation(
                                    severity=Severity.HIGH,
                                    message=f"Missing required field '{req_field}' in {key}",
                                    location=f"{file_path}:{key}",
                                    suggestion=f"Add required field '{req_field}' to {key}",
                                    rule_id="required_field",
                                )
                            )
        for value in data.values():
            if isinstance(value, dict):
                self._validate_component_fields(value, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._validate_component_fields(item, file_path)

    def _validate_numeric_ranges(self, data: Dict[str, Any], file_path: str) -> None:
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            check_key = key.replace("minecraft:", "") if key.startswith("minecraft:") else key
            if check_key in NUMERIC_RANGES:
                min_val, max_val = NUMERIC_RANGES[check_key]
                if isinstance(value, (int, float)):
                    if not min_val <= value <= max_val:
                        self.violations.append(
                            ContractViolation(
                                severity=Severity.MEDIUM,
                                message=f"Value {value} for '{key}' outside valid range [{min_val}, {max_val}]",
                                location=f"{file_path}:{key}",
                                suggestion=f"Adjust '{key}' to be between {min_val} and {max_val}",
                                rule_id="numeric_range",
                            )
                        )
                elif isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        if sub_key in NUMERIC_RANGES and isinstance(sub_val, (int, float)):
                            min_val, max_val = NUMERIC_RANGES[sub_key]
                            if not min_val <= sub_val <= max_val:
                                self.violations.append(
                                    ContractViolation(
                                        severity=Severity.MEDIUM,
                                        message=f"Value {sub_val} for '{sub_key}' outside valid range [{min_val}, {max_val}]",
                                        location=f"{file_path}:{key}.{sub_key}",
                                        suggestion=f"Adjust '{sub_key}' to be between {min_val} and {max_val}",
                                        rule_id="numeric_range",
                                    )
                                )
                        elif sub_key == "value" and isinstance(sub_val, (int, float)):
                            if not min_val <= sub_val <= max_val:
                                self.violations.append(
                                    ContractViolation(
                                        severity=Severity.MEDIUM,
                                        message=f"Value {sub_val} for '{key}.{sub_key}' outside valid range [{min_val}, {max_val}]",
                                        location=f"{file_path}:{key}.{sub_key}",
                                        suggestion=f"Adjust '{key}' value to be between {min_val} and {max_val}",
                                        rule_id="numeric_range",
                                    )
                                )
        for value in data.values():
            if isinstance(value, dict):
                self._validate_numeric_ranges(value, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._validate_numeric_ranges(item, file_path)
        for value in data.values():
            if isinstance(value, dict):
                self._validate_numeric_ranges(value, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._validate_numeric_ranges(item, file_path)

    def _validate_coordinate_semantics(self, data: Dict[str, Any], file_path: str) -> None:
        if not isinstance(data, dict):
            return
        for coord_key in ["x", "y", "z"]:
            if coord_key in data:
                value = data[coord_key]
                schema = COORDINATE_SCHEMA.get(coord_key, {})
                if isinstance(value, (int, float)):
                    min_val = schema.get("min", float("-inf"))
                    max_val = schema.get("max", float("inf"))
                    if not min_val <= value <= max_val:
                        self.violations.append(
                            ContractViolation(
                                severity=Severity.HIGH,
                                message=f"Coordinate {coord_key}={value} outside world bounds",
                                location=f"{file_path}",
                                suggestion=f"Ensure {coord_key} is between {min_val} and {max_val}",
                                rule_id="coordinate_bounds",
                            )
                        )
        for value in data.values():
            if isinstance(value, dict):
                self._validate_coordinate_semantics(value, file_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._validate_coordinate_semantics(item, file_path)

    def repair_contract_violations(
        self, violations: List[ContractViolation], bedrock_content: str, context: str = ""
    ) -> Dict[str, Any]:
        critical_count = sum(1 for v in violations if v.severity == Severity.CRITICAL)
        high_count = sum(1 for v in violations if v.severity == Severity.HIGH)
        total_violations = len(violations)
        needs_repair = total_violations >= self.repair_threshold or critical_count > 0
        if not needs_repair:
            return {
                "needs_repair": False,
                "original_content": bedrock_content,
                "violations_count": total_violations,
            }
        repair_prompt = self._build_repair_prompt(violations, bedrock_content, context)
        return {
            "needs_repair": True,
            "original_content": bedrock_content,
            "violations_count": total_violations,
            "critical_count": critical_count,
            "high_count": high_count,
            "repair_prompt": repair_prompt,
            "violations": [v.to_dict() for v in violations],
        }

    def _build_repair_prompt(
        self, violations: List[ContractViolation], content: str, context: str
    ) -> str:
        violation_summary = []
        for v in violations[:10]:
            violation_summary.append(
                f"- [{v.severity.value.upper()}] {v.rule_id}: {v.message} at {v.location}"
            )
            if v.suggestion:
                violation_summary.append(f"  Suggestion: {v.suggestion}")
        if len(violations) > 10:
            violation_summary.append(f"... and {len(violations) - 10} more violations")
        prompt = f"""Repair the following Bedrock code to fix Minecraft contract violations:

Context: {context or "Standard Bedrock addon conversion"}

Violations found:
{chr(10).join(violation_summary)}

Original Bedrock code:
{content[:2000]}

Instructions:
1. Fix all contract violations listed above
2. Preserve the original functionality and intent
3. Ensure the repaired code follows Bedrock schema rules
4. Return only the repaired code without explanation
"""
        return prompt

    def get_contract_score(self, violations: List[ContractViolation]) -> float:
        if not violations:
            return 100.0
        weights = {
            Severity.CRITICAL: 25,
            Severity.HIGH: 15,
            Severity.MEDIUM: 5,
            Severity.LOW: 1,
        }
        total_penalty = sum(weights.get(v.severity, 5) for v in violations)
        score = max(0.0, 100.0 - total_penalty)
        return round(score, 1)

    def format_violation_report(self, violations: List[ContractViolation]) -> str:
        if not violations:
            return "No contract violations found."
        report_lines = [f"Contract Violation Report ({len(violations)} violations)"]
        report_lines.append("=" * 60)
        by_severity = {}
        for v in violations:
            sev = v.severity.value if isinstance(v.severity, Enum) else v.severity
            by_severity.setdefault(sev, []).append(v)
        for severity in ["critical", "high", "medium", "low"]:
            if severity in by_severity:
                report_lines.append(f"\n{severity.upper()} ({len(by_severity[severity])}):")
                for v in by_severity[severity]:
                    report_lines.append(f"  - {v.message}")
                    report_lines.append(f"    Location: {v.location}")
                    if v.suggestion:
                        report_lines.append(f"    Fix: {v.suggestion}")
        return "\n".join(report_lines)


def validate_bedrock_json(
    data: Dict[str, Any], file_path: str = ""
) -> Tuple[bool, List[ContractViolation]]:
    contract = MinecraftContract()
    return contract.validate_bedrock_json(data, file_path)


def validate_script_api(
    script_content: str, file_path: str = ""
) -> Tuple[bool, List[ContractViolation]]:
    contract = MinecraftContract()
    return contract.validate_script_api(script_content, file_path)


def repair_contract_violations(
    violations: List[ContractViolation], bedrock_content: str, context: str = ""
) -> Dict[str, Any]:
    contract = MinecraftContract()
    return contract.repair_contract_violations(violations, bedrock_content, context)
