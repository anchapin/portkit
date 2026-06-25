"""
Block Generator for Bedrock block behavior JSON assembly.
Part of the entity/ subpackage for Issue #1276 refactoring.
"""

from pathlib import Path
from typing import Any, Dict, List

from agents.entity.block_state_parser import determine_block_category
from agents.entity.nbt_parser import BlockProperties, parse_java_block_properties

BLOCK_TEMPLATE = {
    "format_version": "1.19.0",
    "minecraft:block": {
        "description": {"identifier": "", "register_to_creative_menu": True},
        "components": {},
        "events": {},
    },
}


def create_block_definition(block_id: str, namespace: str = "modporter") -> Dict[str, Any]:
    """
    Create a new Bedrock block definition template.

    Args:
        block_id: Block identifier
        namespace: Namespace for the block

    Returns:
        Block definition dictionary
    """
    full_id = f"{namespace}:{block_id}"
    return {
        "format_version": "1.19.0",
        "minecraft:block": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {},
            "events": {},
        },
    }


def convert_java_block(java_block: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single Java block to Bedrock format.

    Args:
        java_block: Java block definition

    Returns:
        Bedrock block definition
    """
    block_id = java_block.get("id", "unknown_block")
    namespace = java_block.get("namespace", "modporter")
    full_id = f"{namespace}:{block_id}"

    bedrock_block = {
        "format_version": "1.19.0",
        "minecraft:block": {
            "description": {"identifier": full_id, "register_to_creative_menu": True},
            "components": {},
            "events": {},
        },
    }

    properties = parse_java_block_properties(java_block)

    components = bedrock_block["minecraft:block"]["components"]

    if properties.material_type:
        components["minecraft:material_instances"] = {
            "*": {"texture": block_id, "render_method": "opaque"}
        }

    components["minecraft:destructible_by_mining"] = {"seconds_to_destroy": properties.hardness}
    components["minecraft:destructible_by_explosion"] = {
        "explosion_resistance": properties.resistance
    }

    if properties.light_emission > 0:
        components["minecraft:light_emission"] = properties.light_emission

    if properties.light_dampening != 15:
        components["minecraft:light_dampening"] = properties.light_dampening

    if properties.is_solid:
        components["minecraft:collision_box"] = True
        components["minecraft:selection_box"] = True
    else:
        components["minecraft:collision_box"] = False

    if properties.flammable:
        components["minecraft:flammable"] = {"flame_odds": 5, "burn_odds": 5}

    components["minecraft:map_color"] = properties.map_color

    category = determine_block_category(java_block)
    if category:
        components["minecraft:creative_category"] = {"category": category}

    return bedrock_block


def generate_blocks(java_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate Bedrock block definitions from Java blocks.

    Args:
        java_blocks: List of Java block definitions

    Returns:
        Dictionary of Bedrock block definitions
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"Generating Bedrock blocks for {len(java_blocks)} Java blocks")
    bedrock_blocks = {}

    for java_block in java_blocks:
        try:
            bedrock_block = convert_java_block(java_block)
            block_id = bedrock_block["minecraft:block"]["description"]["identifier"]
            bedrock_blocks[block_id] = bedrock_block
        except Exception as e:
            logger.error(f"Failed to convert block {java_block.get('id', 'unknown')}: {e}")
            continue

    logger.info(f"Successfully generated {len(bedrock_blocks)} Bedrock blocks")
    return bedrock_blocks


def write_blocks_to_disk(blocks: Dict[str, Any], bp_path: Path, rp_path: Path) -> List[Path]:
    """
    Write block definitions to disk.

    Args:
        blocks: Dictionary of block definitions
        bp_path: Behavior pack path
        rp_path: Resource pack path

    Returns:
        List of written file paths
    """
    import json

    written_files = []

    if blocks:
        bp_blocks_dir = bp_path / "blocks"
        bp_blocks_dir.mkdir(parents=True, exist_ok=True)

        rp_blocks_dir = rp_path / "blocks"
        rp_blocks_dir.mkdir(parents=True, exist_ok=True)

        for block_id, block_def in blocks.items():
            file_name = f"{block_id.split(':')[-1]}.json"

            bp_file = bp_blocks_dir / file_name
            with open(bp_file, "w", encoding="utf-8") as f:
                json.dump(block_def, f, indent=2, ensure_ascii=False)
            written_files.append(bp_file)

            rp_block = {
                "format_version": "1.19.0",
                "minecraft:block": {
                    "description": {
                        "identifier": block_def["minecraft:block"]["description"]["identifier"]
                    }
                },
            }
            rp_file = rp_blocks_dir / file_name
            with open(rp_file, "w", encoding="utf-8") as f:
                json.dump(rp_block, f, indent=2, ensure_ascii=False)

    return written_files
