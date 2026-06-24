"""
Shaped recipe converter for crafting table shaped recipes.
"""

from typing import Dict


class ShapedRecipeConverter:
    """Converter for shaped crafting recipes."""

    def __init__(self, map_java_item_to_bedrock_fn):
        self._map_java_item = map_java_item_to_bedrock_fn

    def convert_to_bedrock(self, normalized_recipe: Dict, namespace: str, recipe_name: str) -> Dict:
        """Convert a shaped recipe to Bedrock format."""
        pattern = normalized_recipe.get("pattern", [])
        key = normalized_recipe.get("key", {})

        bedrock_key = {}
        for key_char, ingredient in key.items():
            if isinstance(ingredient, list):
                item_data = ingredient[0] if ingredient else "minecraft:air"
                item_count = 1
                item_data_val = 0
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)

            bedrock_item = self._map_java_item(item_data)
            if bedrock_item is None:
                return self._create_manual_review_result(
                    namespace,
                    recipe_name,
                    f"Unresolved tag ingredient: {item_data}",
                )

            key_entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                key_entry["count"] = item_count

            bedrock_key[key_char] = key_entry

        result_item = normalized_recipe.get("result_item", "")
        bedrock_result_item = self._map_java_item(result_item)
        if bedrock_result_item is None:
            return self._create_manual_review_result(
                namespace,
                recipe_name,
                f"Unresolved tag ingredient: {result_item}",
            )

        bedrock_result = {
            "item": bedrock_result_item,
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        bedrock_recipe = {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["crafting_table"],
                "pattern": pattern,
                "key": bedrock_key,
                "result": bedrock_result,
            },
        }

        return bedrock_recipe

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


__all__ = ["ShapedRecipeConverter"]
