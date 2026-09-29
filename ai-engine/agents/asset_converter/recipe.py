"""
Asset Converter Agent - Recipe module.

Contains recipe-related conversion functionality.
Note: This module provides interfaces to the recipe subpackage for
integration with the asset converter system.
"""

from typing import Dict, List

# Import from the recipe subpackage if available
try:
    from agents.recipe import (
        convert_shaped_recipe,
        convert_shapeless_recipe,
        convert_furnace_recipe,
        resolve_recipe_tags,
    )

    HAS_RECIPE_SUPPORT = True
except ImportError:
    HAS_RECIPE_SUPPORT = False


# If recipe support is not available, provide stub functions
if not HAS_RECIPE_SUPPORT:

    def convert_shaped_recipe(recipe_data: Dict) -> Dict:
        """Convert a shaped recipe (stub when recipe package unavailable)."""
        return {"success": False, "error": "Recipe package not available"}

    def convert_shapeless_recipe(recipe_data: Dict) -> Dict:
        """Convert a shapeless recipe (stub when recipe package unavailable)."""
        return {"success": False, "error": "Recipe package not available"}

    def convert_furnace_recipe(recipe_data: Dict) -> Dict:
        """Convert a furnace recipe (stub when recipe package unavailable)."""
        return {"success": False, "error": "Recipe package not available"}

    def resolve_recipe_tags(tags: List[str]) -> List[str]:
        """Resolve recipe tags (stub when recipe package unavailable)."""
        return []
