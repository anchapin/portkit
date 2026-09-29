"""
Furnace recipe converter for smelting, blasting, smoking, and campfire recipes.

Handles:
- Furnace/smelting recipes
- Blast furnace recipes
- Smoking recipes
- Campfire cooking recipes
- Stonecutter recipes
- Smithing recipes
"""

from typing import Dict


class FurnaceRecipeConverter:
    """Converter for furnace-type recipes (smelting, blasting, smoking, campfire)."""

    def __init__(self, map_java_item_to_bedrock_fn):
        self._map_java_item = map_java_item_to_bedrock_fn

    def convert_smelting_to_bedrock(
        self,
        normalized_recipe: Dict,
        namespace: str,
        recipe_name: str,
        recipe_type: str = "smelting",
    ) -> Dict:
        """Convert a furnace-type recipe to Bedrock format."""
        ingredients = normalized_recipe.get("ingredients", [])

        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Furnace recipe has no ingredients"
            )

        ingredient = ingredients[0]

        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_item = self._map_java_item(item_data)
        if bedrock_item is None:
            return self._create_manual_review_result(
                namespace,
                recipe_name,
                f"Unresolved tag ingredient: {item_data}",
            )

        bedrock_ingredient = {
            "item": bedrock_item,
            "data": item_data_val,
        }

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

        cooking_time = normalized_recipe.get("cooking_time", 200)
        experience = normalized_recipe.get("experience", 0.0)

        bedrock_type_map = {
            "smelting": "minecraft:recipe_furnace",
            "blasting": "minecraft:recipe_furnace_blast",
            "smoking": "minecraft:recipe_furnace_smoke",
            "campfire": "minecraft:recipe_campfire",
        }

        bedrock_recipe_type = bedrock_type_map.get(recipe_type, "minecraft:recipe_furnace")

        bedrock_recipe = {
            "format_version": "1.20.10",
            bedrock_recipe_type: {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": [recipe_type],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
                "cookingtime": cooking_time,
                "experience": experience,
            },
        }

        return bedrock_recipe

    def convert_stonecutter_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a stonecutter recipe to Bedrock format."""
        ingredients = normalized_recipe.get("ingredients", [])

        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Stonecutter recipe has no ingredients"
            )

        ingredient = ingredients[0]

        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_item = self._map_java_item(item_data)
        if bedrock_item is None:
            return self._create_manual_review_result(
                namespace,
                recipe_name,
                f"Unresolved tag ingredient: {item_data}",
            )

        bedrock_ingredient = {
            "item": bedrock_item,
            "data": item_data_val,
        }

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
            "minecraft:recipe_stonecutter": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["stonecutter"],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
            },
        }

        return bedrock_recipe

    def convert_smithing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a smithing recipe to Bedrock format."""
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
            "minecraft:recipe_smithing_transform": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["smithing_table"],
                "template": normalized_recipe.get("template", {"item": "minecraft:air"}),
                "base": normalized_recipe.get("base", {"item": "minecraft:air"}),
                "addition": normalized_recipe.get("addition", {"item": "minecraft:air"}),
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


__all__ = ["FurnaceRecipeConverter"]
