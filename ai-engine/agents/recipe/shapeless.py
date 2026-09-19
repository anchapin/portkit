"""
Shapeless recipe converter for crafting table shapeless recipes.
"""

from typing import Dict


class ShapelessRecipeConverter:
    """Converter for shapeless crafting recipes."""

    def __init__(self, map_java_item_to_bedrock_fn):
        self._map_java_item = map_java_item_to_bedrock_fn

    def convert_to_bedrock(self, normalized_recipe: Dict, namespace: str, recipe_name: str) -> Dict:
        """Convert a shapeless recipe to Bedrock format."""
        ingredients = normalized_recipe.get("ingredients", [])

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
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

                ingredient_entry = {"item": bedrock_item, "data": item_data_val}
                if item_count > 1:
                    ingredient_entry["count"] = item_count

                bedrock_ingredients.append(ingredient_entry)
            elif isinstance(ingredient, str):
                bedrock_item = self._map_java_item(ingredient)
                if bedrock_item is None:
                    return self._create_manual_review_result(
                        namespace,
                        recipe_name,
                        f"Unresolved tag ingredient: {ingredient}",
                    )
                bedrock_ingredients.append({"item": bedrock_item, "data": 0})

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
            "minecraft:recipe_shapeless": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["crafting_table"],
                "ingredients": bedrock_ingredients,
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


__all__ = ["ShapelessRecipeConverter"]
