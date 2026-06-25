"""
Block/item/entity/sound/model schema checks.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


VALID_BLOCK_COMPONENTS = {
    "minecraft:block",
    "minecraft:collision_box",
    "minecraft:selection_box",
    "minecraft:material_instances",
    "minecraft:unit_cube",
    "minecraft:pick_collision",
    "minecraft:break_time",
    "minecraft:destroy_time",
    "minecraft:explode",
    "minecraft:friction",
    "minecraft:light_emission",
    "minecraft:light_absorption",
    "minecraft:loot",
    "minecraft:map_color",
    "minecraft:block_material",
    "minecraft:block_entity_data",
    "minecraft:queued_ticking",
    "minecraft:random_ticking",
    "minecraft:rotation",
    "minecraft:scale",
    "minecraft:breathability",
    "minecraft:creative_category",
    "minecraft:entity_collision",
    "minecraft:geometry",
    "minecraft:handle_secondary_anim_state",
    "minecraft:material",
    "minecraft:pick_block",
    "minecraft:placement_filter",
    "minecraft:preferred_path",
    "minecraft:push_through",
    "minecraft:random_display_offset",
    "minecraft:render_offsets",
    "minecraft:rumble",
    "minecraft:spawn_entity",
    "minecraft:step_on",
    "minecraft:ticking",
    "minecraft:use_modifier",
    "minecraft:wall_collision",
}

VALID_SOUND_FORMATS = {".ogg", ".wav", ".mp3", ".fsb"}
MAX_SOUND_FILE_SIZE = 10 * 1024 * 1024

VALID_ENTITY_COMPONENTS = {
    "minecraft:entity",
    "minecraft:identity",
    "minecraft:damage_sensor",
    "minecraft:equipment",
    "minecraft:equippable",
    "minecraft:variant",
    "minecraft:rideable",
    "minecraft:physics",
    "minecraft:nameable",
    "minecraft:health",
    "minecraft:movement",
    "minecraft:movement.basic",
    "minecraft:movement.hover",
    "minecraft:movement.fly",
    "minecraft:movement.glide",
    "minecraft:movement.jump",
    "minecraft:movement.swim",
    "minecraft:movement.walk",
    "minecraft:navigation.climb",
    "minecraft:navigation.float",
    "minecraft:navigation.fly",
    "minecraft:navigation.swim",
    "minecraft:navigation.walk",
    "minecraft:behavior.attack",
    "minecraft:behavior.breed",
    "minecraft:behavior.come_to_stone",
    "minecraft:behavior.drink_milk",
    "minecraft:behavior.eat_block",
    "minecraft:behavior.flee_sun",
    "minecraft:behavior.follow_entity",
    "minecraft:behavior.follow_owner",
    "minecraft:behavior.hurt_by_target",
    "minecraft:behavior.look_at_player",
    "minecraft:behavior.melee_attack",
    "minecraft:behavior.move_to_block",
    "minecraft:behavior.move_to_entity",
    "minecraft:behavior.nearest_attackable_target",
    "minecraft:behavior.panic",
    "minecraft:behavior.random_stroll",
    "minecraft:behavior.sleep",
    "minecraft:behavior.stay_while_sitting",
    "minecraft:behavior.swim",
    "minecraft:behavior.take_flower",
    "minecraft:behavior.tempt",
    "minecraft:behavior.trade_interest",
    "minecraft:behavior.trade_machine",
    "minecraft:breedable",
    "minecraft:color",
    "minecraft:desired_stack_size",
    "minecraft:economy_trade_table",
    "minecraft:family",
    "minecraft:fire_immune",
    "minecraft:floats_in_liquid",
    "minecraft:follow_range",
    "minecraft:friction_modifier",
    "minecraft:genetics",
    "minecraft:healable",
    "minecraft:height_range",
    "minecraft:home",
    "minecraft:horse.jump_strength",
    "minecraft:input_container",
    "minecraft:interact",
    "minecraft:is_baby",
    "minecraft:is_charged",
    "minecraft:is_illager_captain",
    "minecraft:is_saddled",
    "minecraft:is_shaking",
    "minecraft:is_sheared",
    "minecraft:is_stunned",
    "minecraft:is_tamed",
    "minecraft:item_controllable",
    "minecraft:leashable",
    "minecraft:loot",
    "minecraft:mark_variant",
    "minecraft:pushable",
    "minecraft:rail_movement",
    "minecraft:rail_activator",
    "minecraft:raven",
    "minecraft:scale_by_age",
    "minecraft:silk_touch",
    "minecraft:skin_id",
    "minecraft:spawn_entity",
    "minecraft:spawn_reinforcements",
    "minecraft:tamable",
    "minecraft:teleport",
    "minecraft:tick_world",
    "minecraft:trade_resupply",
    "minecraft:type_family",
    "minecraft:walk_animation_speed",
}


def validate_block_definition(block: dict, path: str) -> Dict[str, Any]:
    """Validate block definition against Bedrock schema."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    checks += 1
    has_format = "format_version" in block
    has_block = "minecraft:block" in block
    if has_format and has_block:
        passed += 1
    else:
        missing = []
        if not has_format:
            missing.append("format_version")
        if not has_block:
            missing.append("minecraft:block")
        errors.append(f"{path}: Missing required fields: {missing}")

    if has_format:
        checks += 1
        if isinstance(block["format_version"], str):
            passed += 1
        else:
            warnings.append(f"{path}: format_version should be string")

    if has_block:
        block_data = block["minecraft:block"]

        checks += 1
        if "description" in block_data and "identifier" in block_data["description"]:
            identifier = block_data["description"]["identifier"]
            if ":" in identifier and identifier.count(":") == 1:
                passed += 1
            else:
                errors.append(f"{path}: Invalid identifier format: {identifier}")
        else:
            errors.append(f"{path}: Missing description.identifier")

        if "components" in block_data:
            components = block_data["components"]
            checks += 1

            if isinstance(components, dict):
                passed += 1

                invalid_comps = [c for c in components.keys() if c not in VALID_BLOCK_COMPONENTS]
                if invalid_comps:
                    warnings.append(
                        f"{path}: Unknown component(s): {invalid_comps[:3]} - may not work in Bedrock"
                    )

                for comp_name, comp_value in components.items():
                    if comp_name == "minecraft:material_instances":
                        checks += 1
                        if isinstance(comp_value, dict):
                            passed += 1
                        else:
                            warnings.append(f"{path}: {comp_name} should be an object")

                    elif comp_name == "minecraft:loot":
                        checks += 1
                        if isinstance(comp_value, str):
                            passed += 1
                        else:
                            warnings.append(
                                f"{path}: {comp_name} should be a string (loot table path)"
                            )

        if "permutations" in block_data:
            checks += 1
            if isinstance(block_data["permutations"], list):
                passed += 1

                for i, perm in enumerate(block_data["permutations"]):
                    if not isinstance(perm, dict):
                        warnings.append(f"{path}: Permutation {i} should be an object")
                    elif "condition" not in perm:
                        warnings.append(f"{path}: Permutation {i} missing 'condition' field")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_item_definition(item: dict, path: str) -> Dict[str, Any]:
    """Validate item definition against Bedrock schema."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    checks += 1
    has_format = "format_version" in item
    has_item = "minecraft:item" in item
    if has_format and has_item:
        passed += 1
    else:
        missing = []
        if not has_format:
            missing.append("format_version")
        if not has_item:
            missing.append("minecraft:item")
        errors.append(f"{path}: Missing required fields: {missing}")

    if has_item:
        item_data = item["minecraft:item"]

        checks += 1
        if "description" in item_data and "identifier" in item_data["description"]:
            identifier = item_data["description"]["identifier"]
            if ":" in identifier:
                passed += 1
            else:
                warnings.append(f"{path}: Unusual identifier format: {identifier}")
        else:
            errors.append(f"{path}: Missing description.identifier")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_entity_definition(entity: dict, path: str) -> Dict[str, Any]:
    """Validate entity definition against Bedrock schema."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    checks += 1
    has_format = "format_version" in entity
    has_entity = "minecraft:entity" in entity
    if has_format and has_entity:
        passed += 1
    else:
        missing = []
        if not has_format:
            missing.append("format_version")
        if not has_entity:
            missing.append("minecraft:entity")
        errors.append(f"{path}: Missing required fields: {missing}")

    if has_format:
        checks += 1
        if isinstance(entity["format_version"], str):
            passed += 1
        else:
            warnings.append(f"{path}: format_version should be string")

    if has_entity:
        entity_data = entity["minecraft:entity"]

        checks += 1
        if "description" in entity_data:
            desc = entity_data["description"]
            if "identifier" in desc:
                identifier = desc["identifier"]
                if ":" in identifier and identifier.count(":") == 1:
                    passed += 1
                else:
                    errors.append(f"{path}: Invalid identifier format: {identifier}")

                if "is_spawnable" in desc:
                    checks += 1
                    if isinstance(desc["is_spawnable"], bool):
                        passed += 1
                if "is_experimental" in desc:
                    checks += 1
                    if isinstance(desc["is_experimental"], bool):
                        passed += 1
        else:
            errors.append(f"{path}: Missing description.identifier")

        if "components" in entity_data:
            components = entity_data["components"]
            checks += 1

            if isinstance(components, dict):
                invalid_comps = [c for c in components.keys() if c not in VALID_ENTITY_COMPONENTS]

                if invalid_comps:
                    warnings.append(
                        f"{path}: Unknown component(s): {invalid_comps[:3]} - may not work correctly"
                    )
                passed += 1

                for comp_name, comp_value in components.items():
                    if comp_name == "minecraft:health":
                        checks += 1
                        if isinstance(comp_value, dict) and "value" in comp_value:
                            if (
                                isinstance(comp_value["value"], (int, float))
                                and comp_value["value"] > 0
                            ):
                                passed += 1
                            else:
                                errors.append(f"{path}: {comp_name} has invalid value")
                        else:
                            warnings.append(f"{path}: {comp_name} has unusual structure")

                    elif comp_name == "minecraft:movement":
                        checks += 1
                        if isinstance(comp_value, dict):
                            passed += 1
                        else:
                            warnings.append(f"{path}: {comp_name} should be an object")

        if "component_groups" in entity_data:
            checks += 1
            if isinstance(entity_data["component_groups"], dict):
                passed += 1
            else:
                warnings.append(f"{path}: component_groups should be an object")

        if "events" in entity_data:
            checks += 1
            if isinstance(entity_data["events"], dict):
                passed += 1

                for event_name, event_data in entity_data["events"].items():
                    if not isinstance(event_data, dict):
                        warnings.append(f"{path}: Event '{event_name}' should be an object")
            else:
                warnings.append(f"{path}: events should be an object")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_blocks_in_archive(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate all block definitions in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    block_files = [
        name
        for name in namelist
        if name.startswith("behavior_packs/") and "/blocks/" in name and name.endswith(".json")
    ]

    for block_file in block_files:
        try:
            with zipf.open(block_file) as f:
                block_data = json.load(f)

            result = validate_block_definition(block_data, block_file)
            checks += result["checks"]
            passed += result["passed"]
            errors.extend(result["errors"])
            warnings.extend(result["warnings"])

        except json.JSONDecodeError:
            checks += 1
            errors.append(f"Invalid JSON in block file: {block_file}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_items_in_archive(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate all item definitions in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    item_files = [
        name
        for name in namelist
        if name.startswith("behavior_packs/") and "/items/" in name and name.endswith(".json")
    ]

    for item_file in item_files:
        try:
            with zipf.open(item_file) as f:
                item_data = json.load(f)

            result = validate_item_definition(item_data, item_file)
            checks += result["checks"]
            passed += result["passed"]
            errors.extend(result["errors"])
            warnings.extend(result["warnings"])

        except json.JSONDecodeError:
            checks += 1
            errors.append(f"Invalid JSON in item file: {item_file}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_entities_in_archive(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate all entity definitions in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    entity_files = [
        name
        for name in namelist
        if name.startswith("behavior_packs/") and "/entities/" in name and name.endswith(".json")
    ]

    for entity_file in entity_files:
        try:
            with zipf.open(entity_file) as f:
                entity_data = json.load(f)

            result = validate_entity_definition(entity_data, entity_file)
            checks += result["checks"]
            passed += result["passed"]
            errors.extend(result["errors"])
            warnings.extend(result["warnings"])

        except json.JSONDecodeError:
            checks += 1
            errors.append(f"Invalid JSON in entity file: {entity_file}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_sounds_in_archive(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate sound files in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    sound_files = [
        name for name in namelist if any(name.lower().endswith(ext) for ext in VALID_SOUND_FORMATS)
    ]

    for sound_file in sound_files:
        checks += 1
        try:
            info = zipf.getinfo(sound_file)
            if info.file_size > MAX_SOUND_FILE_SIZE:
                warnings.append(
                    f"{sound_file}: Sound file exceeds {MAX_SOUND_FILE_SIZE // (1024 * 1024)}MB limit"
                )
            else:
                passed += 1

            ext = Path(sound_file).suffix.lower()
            if ext == ".ogg":
                with zipf.open(sound_file) as f:
                    header = f.read(4)
                    if header != b"OggS":
                        warnings.append(f"{sound_file}: Possible invalid OGG file")
            elif ext == ".wav":
                with zipf.open(sound_file) as f:
                    header = f.read(4)
                    if header != b"RIFF":
                        warnings.append(f"{sound_file}: Possible invalid WAV file")
        except Exception as e:
            warnings.append(f"{sound_file}: Could not validate: {str(e)}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_models_in_archive(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate model files in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    model_files = [
        name
        for name in namelist
        if name.endswith(".geo.json") or (name.endswith(".json") and "/models/" in name)
    ]

    for model_file in model_files:
        checks += 1
        try:
            with zipf.open(model_file) as f:
                model_data = json.load(f)

            if "minecraft:geometry" in model_data or "format_version" in model_data:
                passed += 1

                if "minecraft:geometry" in model_data:
                    geometry = model_data["minecraft:geometry"]
                    if isinstance(geometry, list) and len(geometry) > 0:
                        geo_data = geometry[0] if isinstance(geometry[0], dict) else {}
                        if "bones" in geo_data:
                            vertex_count = sum(
                                len(b.get("cubes", [])) * 8
                                for b in geo_data["bones"]
                                if isinstance(b, dict)
                            )
                            if vertex_count > 3000:
                                warnings.append(
                                    f"{model_file}: High vertex count ({vertex_count}) may impact performance"
                                )
            else:
                warnings.append(f"{model_file}: Missing expected geometry structure")
        except json.JSONDecodeError:
            errors.append(f"{model_file}: Invalid JSON format")
        except Exception as e:
            warnings.append(f"{model_file}: Could not validate: {str(e)}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}
