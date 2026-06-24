"""
Shared base for the custom recipe-type converters plus the Forge recipe-type
registry loader.

Extracted from the original ``custom_types.py`` monolith (issue #1745) so the
per-mod conversion logic can live in focused, domain-scoped modules
(``create_converter.py``, ``immersive_engineering_converter.py``).

Public surface:
- ``CustomConverterBase`` — holds the item-mapping callable and the shared
  manual-review helper used by every per-mod converter mixin.
- ``CUSTOM_RECIPE_TYPES`` / ``_load_custom_recipe_types`` — Forge recipe-type
  registry loaded from ``data/custom_recipe_types.json``.
- ``is_custom_recipe_type`` — membership check against the registry.
"""

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def _load_custom_recipe_types() -> Dict:
    """Load custom Forge recipe type definitions from the bundled JSON file.

    Returns:
        Dictionary mapping recipe type IDs to their metadata

    The mappings are loaded from data/custom_recipe_types.json.
    """
    try:
        data_dir = Path(__file__).parent.parent.parent / "data"
        mappings_file = data_dir / "custom_recipe_types.json"

        if not mappings_file.exists():
            logger.warning(
                f"Custom recipe types file not found at {mappings_file}. Falling back to empty dict."
            )
            return {}

        with open(mappings_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        types = data.get("types", {})
        metadata = data.get("metadata", {})
        logger.info(
            f"Loaded {len(types)} custom recipe types from {mappings_file} "
            f"(type_count: {metadata.get('type_count', 'unknown')})"
        )
        return types

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing custom recipe types JSON: {e}. Falling back to empty dict.")
        return {}
    except Exception as e:
        logger.error(f"Error loading custom recipe types: {e}. Falling back to empty dict.")
        return {}


CUSTOM_RECIPE_TYPES = _load_custom_recipe_types()


def is_custom_recipe_type(recipe_type: str) -> bool:
    """Check if a recipe type is a known custom Forge recipe type."""
    for custom_type in CUSTOM_RECIPE_TYPES.keys():
        if custom_type in recipe_type:
            return True
    return False


class CustomConverterBase:
    """Shared base for custom recipe-type converters.

    Holds the Java->Bedrock item-mapping callable provided by the host
    converter agent and exposes the shared ``_create_manual_review_result``
    helper used by every per-mod converter mixin.
    """

    def __init__(self, map_java_item_to_bedrock_fn):
        self._map_java_item = map_java_item_to_bedrock_fn

    def _create_manual_review_result(self, namespace: str, recipe_name: str, reason: str) -> Dict:
        """Create a result indicating the recipe requires manual review."""
        return {
            "format_version": "1.20.10",
            "manual_review_required": True,
            "reason": reason,
            "original_recipe": f"{namespace}:{recipe_name}",
            "description": {"identifier": f"{namespace}:{recipe_name}"},
            "portkit:unresolved_tag": True,
        }


__all__ = [
    "CUSTOM_RECIPE_TYPES",
    "CustomConverterBase",
    "_load_custom_recipe_types",
    "is_custom_recipe_type",
]
