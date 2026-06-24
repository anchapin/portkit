"""
Tag resolver for Forge tag to Bedrock ID resolution.

Provides FORGE_TAG_MAPPINGS for translating Forge tags to Bedrock item IDs,
and loads Java to Bedrock item ID mappings from bundled JSON.

Includes a resolve_tag_to_bedrock() function that provides fallback resolution
for Forge tags not in FORGE_TAG_MAPPINGS by extracting material/category patterns
and looking up candidate items in JAVA_TO_BEDROCK_ITEM_MAP.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _load_forge_tags() -> Dict[str, str]:
    """Load Forge tag to Bedrock item ID mappings from the bundled JSON file.

    Returns:
        Dictionary mapping Forge tags to Bedrock item IDs

    The mappings are loaded from data/forge_tag_mappings.json.
    """
    try:
        data_dir = Path(__file__).parent.parent.parent / "data"
        mappings_file = data_dir / "forge_tag_mappings.json"

        if not mappings_file.exists():
            logger.warning(
                f"Forge tag mappings file not found at {mappings_file}. Falling back to empty mappings."
            )
            return {}

        with open(mappings_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        mappings = data.get("mappings", {})
        metadata = data.get("metadata", {})
        logger.info(
            f"Loaded {len(mappings)} Forge tag mappings from {mappings_file} "
            f"(tag_count: {metadata.get('tag_count', 'unknown')})"
        )
        return mappings

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing Forge tag mappings JSON: {e}. Falling back to empty mappings.")
        return {}
    except Exception as e:
        logger.error(f"Error loading Forge tag mappings: {e}. Falling back to empty mappings.")
        return {}


def _load_item_mappings() -> Dict[str, str]:
    """Load Java to Bedrock item ID mappings from the bundled JSON file.

    Returns:
        Dictionary mapping Java item IDs to Bedrock item IDs

    The mappings are loaded from data/item_mappings.json which is generated
    by scripts/generate_item_mappings.py using minecraft-data.
    """
    try:
        data_dir = Path(__file__).parent.parent.parent / "data"
        mappings_file = data_dir / "item_mappings.json"

        if not mappings_file.exists():
            logger.warning(
                f"Item mappings file not found at {mappings_file}. Falling back to empty mappings."
            )
            return {}

        with open(mappings_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        mappings = data.get("mappings", {})
        metadata = data.get("metadata", {})
        logger.info(
            f"Loaded {len(mappings)} item mappings from {mappings_file} "
            f"(version: {metadata.get('version', 'unknown')})"
        )
        return mappings

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing item mappings JSON: {e}. Falling back to empty mappings.")
        return {}
    except Exception as e:
        logger.error(f"Error loading item mappings: {e}. Falling back to empty mappings.")
        return {}


JAVA_TO_BEDROCK_ITEM_MAP = _load_item_mappings()


FORGE_TAG_MAPPINGS = _load_forge_tags()

_TAG_PATTERN_CACHE: Dict[str, Optional[str]] = {}

_TAG_CATEGORY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^#forge:ingots/([^/]+)$"), "minecraft:{material}_ingot"),
    (re.compile(r"^#forge:nuggets/([^/]+)$"), "minecraft:{material}_nugget"),
    (re.compile(r"^#forge:storage_blocks/([^/]+)$"), "minecraft:{material}_block"),
    (re.compile(r"^#forge:ores/([^/]+)$"), "minecraft:{material}_ore"),
    (re.compile(r"^#forge:gems/([^/]+)$"), "minecraft:{material}"),
    (re.compile(r"^#forge:crops/([^/]+)$"), "minecraft:{material}"),
    (re.compile(r"^#forge:seeds/([^/]+)$"), "minecraft:{material}_seeds"),
    (re.compile(r"^#forge:wood/([^/]+)$"), "minecraft:{material}_log"),
    (re.compile(r"^#forge:planks/([^/]+)$"), "minecraft:{material}_planks"),
]


def resolve_tag_to_bedrock(tag: str) -> Optional[str]:
    """Resolve a Forge tag to a Bedrock item ID using pattern-based lookup.

    This function provides fallback resolution for Forge tags not explicitly mapped
    in FORGE_TAG_MAPPINGS. It extracts the material and category from the tag path
    and attempts to construct a candidate Minecraft item ID, which is then looked up
    in JAVA_TO_BEDROCK_ITEM_MAP.

    Args:
        tag: A Forge tag string like "#forge:ingots/iron" or "#forge:storage_blocks/coal"

    Returns:
        A Bedrock item ID string if resolution succeeds, None if resolution fails.
        Returns None for mod-only tags with no vanilla Minecraft representative.

    Examples:
        >>> resolve_tag_to_bedrock("#forge:ingots/iron")
        'minecraft:iron_ingot'
        >>> resolve_tag_to_bedrock("#forge:storage_blocks/diamond")
        'minecraft:diamond_block'
        >>> resolve_tag_to_bedrock("#forge:ores/gold")
        'minecraft:gold_ore'
        >>> resolve_tag_to_bedrock("#forge:something_mod_only")  # returns None
    """
    if tag in _TAG_PATTERN_CACHE:
        return _TAG_PATTERN_CACHE[tag]

    if tag in FORGE_TAG_MAPPINGS:
        _TAG_PATTERN_CACHE[tag] = FORGE_TAG_MAPPINGS[tag]
        return FORGE_TAG_MAPPINGS[tag]

    if not tag.startswith("#forge:") and not tag.startswith("#minecraft:"):
        _TAG_PATTERN_CACHE[tag] = None
        return None

    result = None
    for pattern, candidate_template in _TAG_CATEGORY_PATTERNS:
        match = pattern.match(tag)
        if match:
            material = match.group(1)
            candidate = candidate_template.format(material=material)
            if candidate in JAVA_TO_BEDROCK_ITEM_MAP:
                result = JAVA_TO_BEDROCK_ITEM_MAP[candidate]
                logger.debug(f"Resolved tag {tag} to {result} via pattern {candidate_template}")
                break

    _TAG_PATTERN_CACHE[tag] = result
    return result


def clear_tag_pattern_cache() -> None:
    """Clear the internal tag resolution cache.

    Useful for testing or when FORGE_TAG_MAPPINGS has been updated.
    """
    _TAG_PATTERN_CACHE.clear()


__all__ = [
    "FORGE_TAG_MAPPINGS",
    "JAVA_TO_BEDROCK_ITEM_MAP",
    "_load_item_mappings",
    "_load_forge_tags",
    "resolve_tag_to_bedrock",
    "clear_tag_pattern_cache",
]
