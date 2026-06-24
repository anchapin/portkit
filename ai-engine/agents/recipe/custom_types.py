"""
Custom recipe types converter for NeoForge, Farmer's Delight, Create, and other mods.

Handles:
- Farmer's Delight (cooking pot, cutting board)
- Create (mechanical crafting, pressing, milling, crushing, deploying, splashing, compacting)
- Generic Forge patterns
"""

import copy
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


class CustomTypesConverter:
    """Converter for custom Forge recipe types (Farmer's Delight, Create, etc.)."""

    def __init__(self, map_java_item_to_bedrock_fn):
        self._map_java_item = map_java_item_to_bedrock_fn

    def convert_cooking_pot_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Farmer's Delight cooking pot recipe to Bedrock format.

        Cooking pot recipes are converted to furnace recipes with additional
        container and cooking time info preserved in comments/tags.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Cooking pot recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {
            "item": self._map_java_item(item_data),
            "data": item_data_val,
        }

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        container = normalized_recipe.get("container")
        cooking_time = normalized_recipe.get("cooking_time", 200)
        experience = normalized_recipe.get("experience", 0.0)

        bedrock_recipe = {
            "format_version": "1.20.10",
            "minecraft:recipe_furnace": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["crafting_table", "cooking_pot"],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
                "cookingtime": cooking_time,
                "experience": experience,
                "备注": f"Original container: {container}"
                if container
                else "Farmer's Delight cooking pot recipe",
            },
        }

        return bedrock_recipe

    def convert_cutting_board_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Farmer's Delight cutting board recipe to Bedrock format.

        Cutting board recipes use a tool + ingredients -> result pattern.
        We convert to a shaped recipe with the tool as part of the key.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        tool = normalized_recipe.get("tool")

        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Cutting board recipe has no ingredients"
            )

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue

            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        tool_info = ""
        if tool:
            tool_item = tool.get("item", tool) if isinstance(tool, dict) else tool
            tool_info = f" - Requires tool: {tool_item}"

        bedrock_recipe = {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["crafting_table", "cutting_board"],
                "pattern": ["A", "B"],
                "key": {
                    "A": bedrock_ingredients[0]
                    if len(bedrock_ingredients) > 0
                    else {"item": "minecraft:air"},
                    "B": {"item": "minecraft:air"}
                    if len(bedrock_ingredients) <= 1
                    else bedrock_ingredients[1],
                },
                "result": bedrock_result,
                "备注": f"Cutting board recipe{tool_info}",
            },
        }

        return bedrock_recipe

    def convert_mechanical_crafting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create mechanical crafting recipe to Bedrock format.

        Mechanical crafting supports up to 9x9 grids. We convert to a standard
        shaped recipe (Bedrock supports 3x3 max).
        """
        pattern = normalized_recipe.get("pattern", [])
        key = normalized_recipe.get("key", {})

        if not pattern or not key:
            return self._create_manual_review_result(
                namespace, recipe_name, "Mechanical crafting recipe has no pattern or key"
            )

        max_row_len = max(len(row) for row in pattern) if pattern else 0
        if max_row_len > 3 or len(pattern) > 3:
            return self._create_manual_review_result(
                namespace,
                recipe_name,
                f"Mechanical crafting uses {max_row_len}x{len(pattern)} grid, Bedrock supports max 3x3",
            )

        bedrock_key = {}
        for key_char, ingredient in key.items():
            if isinstance(ingredient, list):
                item_data = ingredient[0].get("item", "") if ingredient else "minecraft:air"
                item_count = 1
                item_data_val = 0
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            elif isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            else:
                continue

            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_key[key_char] = entry

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        bedrock_recipe = {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["crafting_table", "mechanical_crafting"],
                "pattern": pattern,
                "key": bedrock_key,
                "result": bedrock_result,
            },
        }

        return bedrock_recipe

    def convert_pressing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create pressing recipe to Bedrock format.

        Pressing recipes are converted to a shaped recipe with the ingredient
        as the main input.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Pressing recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {
            "item": self._map_java_item(item_data),
            "data": item_data_val,
        }

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        bedrock_recipe = {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}"},
                "tags": ["crafting_table", "pressing"],
                "pattern": ["A"],
                "key": {"A": bedrock_ingredient},
                "result": bedrock_result,
                "备注": "Create pressing recipe",
            },
        }

        return bedrock_recipe

    def convert_milling_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create milling recipe to Bedrock format.

        Milling recipes use Millstone to crush ores into materials.
        Converted to a shaped recipe approximating the crushing operation.
        Secondary outputs are fanned out via ``portkit:additional_recipes``
        (issue #1770) instead of being dropped into a human-readable note.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Milling recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {
            "item": self._map_java_item(item_data),
            "data": item_data_val,
        }

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        block = {
            "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
            "tags": ["crafting_table", "milling"],
            "pattern": ["A"],
            "key": {"A": bedrock_ingredient},
            "result": bedrock_result,
        }

        return self._assemble_create_recipe(
            "minecraft:recipe_shaped",
            block,
            normalized_recipe,
            machine="create:milling",
        )

    def convert_crushing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create crushing recipe to Bedrock format.

        Crushing recipes use Crushing Wheels for ore doubling.
        Converted to a shaped recipe approximating the crushing operation.
        Secondary outputs are fanned out via ``portkit:additional_recipes``
        (issue #1770) instead of being dropped into a human-readable note.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Crushing recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {
            "item": self._map_java_item(item_data),
            "data": item_data_val,
        }

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        block = {
            "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
            "tags": ["crafting_table", "crushing"],
            "pattern": ["A"],
            "key": {"A": bedrock_ingredient},
            "result": bedrock_result,
        }

        return self._assemble_create_recipe(
            "minecraft:recipe_shaped",
            block,
            normalized_recipe,
            machine="create:crushing",
        )

    def convert_deploying_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create deploying recipe to Bedrock format.

        Deploying recipes combine an item with a catalyst (block) to produce output.
        Converted to a shaped recipe using ingredient + catalyst pattern.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        tool = normalized_recipe.get("tool")

        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Deploying recipe has no ingredients"
            )

        bedrock_ingredients = []
        for i, ingredient in enumerate(ingredients):
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue

            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        catalyst_info = ""
        if tool:
            tool_item = tool.get("item", tool) if isinstance(tool, dict) else tool
            bedrock_tool = self._map_java_item(tool_item)
            catalyst_info = f" - Catalyst: {bedrock_tool}"

        pattern = ["AB"] if len(bedrock_ingredients) >= 2 else ["A"]
        key = {
            "A": bedrock_ingredients[0]
            if len(bedrock_ingredients) > 0
            else {"item": "minecraft:air"},
            "B": bedrock_ingredients[1]
            if len(bedrock_ingredients) > 1
            else {"item": "minecraft:air"},
        }

        bedrock_recipe = {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "deploying"],
                "pattern": pattern,
                "key": key,
                "result": bedrock_result,
                "备注": f"Create deploying recipe{catalyst_info} - approximated",
            },
        }

        return bedrock_recipe

    def convert_splashing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create splashing recipe to Bedrock format.

        Splashing recipes use water to wash items (ore washing, etc.).
        Converted to a shapeless recipe with water bucket as an implicit ingredient.
        """
        ingredients = normalized_recipe.get("ingredients", [])

        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Splashing recipe has no ingredients"
            )

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue

            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        block = {
            "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
            "tags": ["crafting_table", "splashing"],
            "ingredients": bedrock_ingredients,
            "result": bedrock_result,
        }

        return self._assemble_create_recipe(
            "minecraft:recipe_shapeless",
            block,
            normalized_recipe,
            machine="create:splashing",
        )

    def convert_compacting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create compacting recipe to Bedrock format.

        Compacting recipes compress items into blocks.
        Converted to a shaped recipe.
        """
        ingredients = normalized_recipe.get("ingredients", [])

        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Compacting recipe has no ingredients"
            )

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue

            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        pattern = ["A"] * min(len(bedrock_ingredients), 3)
        key = {}
        for i, char in enumerate(["A", "B", "C"][: len(bedrock_ingredients)]):
            key[char] = bedrock_ingredients[i]

        block = {
            "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
            "tags": ["crafting_table", "compacting"],
            "pattern": pattern,
            "key": key,
            "result": bedrock_result,
        }

        return self._assemble_create_recipe(
            "minecraft:recipe_shaped",
            block,
            normalized_recipe,
            machine="create:compacting",
        )

    def convert_mixing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create mixing recipe to Bedrock format.

        Mixing recipes use the Basin + Mechanical Mixer.
        Non-fluid recipes convert to shapeless; fluid recipes get manual review.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Mixing recipe has no ingredients"
            )

        fluid_ingredients = []
        for ing in ingredients:
            if isinstance(ing, dict) and ing.get("tag") and ing["tag"].startswith("forge:fluids"):
                fluid_ingredients.append(ing)
            elif isinstance(ing, str) and ing.startswith("forge:fluids"):
                fluid_ingredients.append(ing)

        if fluid_ingredients:
            return self._create_manual_review_result(
                namespace,
                recipe_name,
                "Mixing recipe with fluid ingredients requires Create's mixer block not available in Bedrock",
            )

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue
            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        secondary_note = ""
        secondary_outputs = normalized_recipe.get("secondary_outputs", [])
        if secondary_outputs:
            secondary_items = [o.get("item", "") for o in secondary_outputs]
            secondary_note = f" | Secondary outputs: {secondary_items}"

        heat_note = ""
        if normalized_recipe.get("heat_requirement"):
            heat_note = f" | Heat: {normalized_recipe['heat_requirement']}"

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shapeless": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "mixing"],
                "ingredients": bedrock_ingredients,
                "result": bedrock_result,
                "备注": f"Create mixing recipe (Basin) - approximated{secondary_note}{heat_note}",
            },
        }

    def convert_sequenced_assembly_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create sequenced assembly recipe to Bedrock format.

        Sequenced assembly is multi-step; we convert the first step and
        note the remaining steps for manual review.
        """
        transitions = normalized_recipe.get("transitions", [])
        ingredient = normalized_recipe.get("ingredient")

        bedrock_ingredient = {"item": "minecraft:air"}
        if ingredient:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_data_val = ingredient.get("data", 0)
            else:
                item_data = ingredient
                item_data_val = 0
            bedrock_ingredient = {"item": self._map_java_item(item_data), "data": item_data_val}

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        steps_note = f" | Steps: {len(transitions)}" if transitions else ""

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "sequenced_assembly"],
                "pattern": ["A"],
                "key": {"A": bedrock_ingredient},
                "result": bedrock_result,
                "备注": f"Create sequenced assembly - first step only, full sequence needs manual assembly{steps_note}",
            },
        }

    def convert_filling_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create filling recipe to Bedrock format.

        Filling recipes combine an item with a fluid.
        Converted to a shaped recipe noting the fluid requirement.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Filling recipe has no ingredients"
            )

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue
            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "filling"],
                "pattern": ["AB"] if len(bedrock_ingredients) >= 2 else ["A"],
                "key": {
                    "A": bedrock_ingredients[0]
                    if bedrock_ingredients
                    else {"item": "minecraft:air"},
                    "B": bedrock_ingredients[1]
                    if len(bedrock_ingredients) > 1
                    else {"item": "minecraft:air"},
                },
                "result": bedrock_result,
                "备注": "Create filling recipe (item + fluid) - fluid portion needs manual setup",
            },
        }

    def convert_emptying_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create emptying recipe to Bedrock format.

        Emptying recipes extract fluid from items.
        Converted to a shaped recipe noting the fluid output.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Emptying recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {"item": self._map_java_item(item_data), "data": item_data_val}

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "emptying"],
                "pattern": ["A"],
                "key": {"A": bedrock_ingredient},
                "result": bedrock_result,
                "备注": "Create emptying recipe - fluid output needs manual handling",
            },
        }

    def convert_cutting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create cutting recipe to Bedrock format.

        Cutting recipes use the Mechanical Saw to cut blocks/items.
        Converted to a shaped recipe.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Cutting recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {"item": self._map_java_item(item_data), "data": item_data_val}

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        secondary_note = ""
        secondary_outputs = normalized_recipe.get("secondary_outputs", [])
        if secondary_outputs:
            secondary_items = [o.get("item", "") for o in secondary_outputs]
            secondary_note = f" | Secondary outputs: {secondary_items}"

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "cutting"],
                "pattern": ["A"],
                "key": {"A": bedrock_ingredient},
                "result": bedrock_result,
                "备注": f"Create cutting recipe (Mechanical Saw) - approximated{secondary_note}",
            },
        }

    def convert_haunting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create haunting recipe to Bedrock format.

        Haunting recipes convert items via Encased Fan with soul fire.
        Converted to a shaped recipe.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Haunting recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {"item": self._map_java_item(item_data), "data": item_data_val}

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "haunting"],
                "pattern": ["A"],
                "key": {"A": bedrock_ingredient},
                "result": bedrock_result,
                "备注": "Create haunting recipe (Encased Fan + Soul Fire) - approximated",
            },
        }

    def convert_sandpaper_polishing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create sandpaper polishing recipe to Bedrock format.

        Sandpaper polishing recipes polish items using Sand Paper.
        Converted to a shaped recipe.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Sandpaper polishing recipe has no ingredients"
            )

        ingredient = ingredients[0]
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", "")
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0

        bedrock_ingredient = {"item": self._map_java_item(item_data), "data": item_data_val}

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "sandpaper_polishing"],
                "pattern": ["A"],
                "key": {"A": bedrock_ingredient},
                "result": bedrock_result,
                "备注": "Create sandpaper polishing recipe - approximated",
            },
        }

    def convert_item_application_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create item application recipe to Bedrock format.

        Item application recipes apply one item to another (block).
        Converted to a shaped recipe with ingredient + applied item.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "Item application recipe has no ingredients"
            )

        bedrock_ingredients = []
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item_data = ingredient.get("item", "")
                item_count = ingredient.get("count", 1)
                item_data_val = ingredient.get("data", 0)
            elif isinstance(ingredient, str):
                item_data = ingredient
                item_count = 1
                item_data_val = 0
            else:
                continue
            bedrock_item = self._map_java_item(item_data)
            entry = {"item": bedrock_item, "data": item_data_val}
            if item_count > 1:
                entry["count"] = item_count
            bedrock_ingredients.append(entry)

        bedrock_result = {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

        pattern = ["AB"] if len(bedrock_ingredients) >= 2 else ["A"]
        key = {
            "A": bedrock_ingredients[0] if bedrock_ingredients else {"item": "minecraft:air"},
            "B": bedrock_ingredients[1]
            if len(bedrock_ingredients) > 1
            else {"item": "minecraft:air"},
        }

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{recipe_name}_converted_from_create"},
                "tags": ["crafting_table", "item_application"],
                "pattern": pattern,
                "key": key,
                "result": bedrock_result,
                "备注": "Create item application recipe - approximated",
            },
        }

    def _build_create_conversion_note(self, normalized_recipe: Dict) -> str:
        """Compose the namespaced conversion note for a Create approximation.

        Only carries heat/RPM context; secondary outputs are no longer baked
        into the note since they are fanned out via ``portkit:additional_recipes``
        (issue #1770). Returns an empty string when there is no such context.
        """
        parts = []
        heat = normalized_recipe.get("heat_requirement")
        if heat:
            parts.append(f"Heat: {heat}")
        min_rpm = normalized_recipe.get("min_rpm")
        max_rpm = normalized_recipe.get("max_rpm")
        if min_rpm or max_rpm:
            parts.append(f"RPM: {min_rpm or '?'}-{max_rpm or '?'}")
        return " | ".join(parts)

    def _assemble_create_recipe(
        self,
        block_key: str,
        block: Dict,
        normalized_recipe: Dict,
        machine: str,
    ) -> Dict:
        """Assemble a Create Bedrock recipe with namespaced annotations.

        Replaces the legacy schema-invalid ``备注`` key with the namespaced
        annotation channel so emitted JSON only carries ``minecraft:``/
        ``portkit:`` keys (issue #1770):

        - ``portkit:approximated_from`` — the Create machine type
          (e.g. ``create:crushing``).
        - ``portkit:conversion_note`` — heat/RPM context (omitted when empty).
        - ``portkit:additional_recipes`` — one fully-formed Bedrock recipe
          per secondary output, each with a ``_outN`` identifier suffix and
          a ``portkit:output_chance`` annotation when the source recorded a
          probability weight. Omitted for single-output recipes.

        The per-recipe converter return type stays a single ``Dict``; a
        downstream packager can read ``portkit:additional_recipes`` to write
        one extra ``.json`` file per secondary under ``recipes/``.
        """
        block["portkit:approximated_from"] = machine
        note = self._build_create_conversion_note(normalized_recipe)
        if note:
            block["portkit:conversion_note"] = note

        recipe = {"format_version": "1.20.10", block_key: block}

        secondaries = normalized_recipe.get("secondary_outputs", []) or []
        if not secondaries:
            return recipe

        additional = []
        for idx, sec in enumerate(secondaries, start=2):
            sec_block = copy.deepcopy(block)
            sec_block["result"] = {
                "item": self._map_java_item(sec.get("item", "")),
                "data": sec.get("data", 0),
                "count": sec.get("count", 1),
            }
            base_id = sec_block["description"]["identifier"]
            sec_block["description"]["identifier"] = f"{base_id}_out{idx}"
            if "chance" in sec:
                sec_block["portkit:output_chance"] = sec["chance"]
            additional.append({"format_version": "1.20.10", block_key: sec_block})
        recipe["portkit:additional_recipes"] = additional
        return recipe

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

    # ─────────────────────────────────────────────────────────────────────
    # ImmersiveEngineering (issue #1771)
    #
    # Bedrock has no ImmersiveEngineering, so crusher / metalpress /
    # arc_furnace / refinery recipes are approximated as vanilla shapeless
    # recipes. Machine-specific metadata (energy cost, secondaries, mold) is
    # preserved via the `portkit:approximated_from` annotation channel so the
    # packager/validator still see only valid Bedrock schema fields.
    # ─────────────────────────────────────────────────────────────────────

    _IE_MACHINE_TAG = "immersiveengineering"

    def _build_ie_ingredient(self, ingredient) -> Dict:
        """Normalize a single IE input ingredient into a Bedrock ingredient dict."""
        if isinstance(ingredient, dict):
            item_data = ingredient.get("item", ingredient.get("id", ""))
            if not item_data and ingredient.get("tag"):
                item_data = ingredient["tag"]
            item_data_val = ingredient.get("data", 0)
        else:
            item_data = ingredient
            item_data_val = 0
        return {"item": self._map_java_item(item_data), "data": item_data_val}

    def _build_ie_result(self, normalized_recipe: Dict) -> Dict:
        """Build the Bedrock result block for an IE recipe."""
        return {
            "item": self._map_java_item(normalized_recipe.get("result_item", "")),
            "data": normalized_recipe.get("result_data", 0),
            "count": normalized_recipe.get("result_count", 1),
        }

    def _build_ie_approximation_note(
        self, machine: str, normalized_recipe: Dict, extras: str = ""
    ) -> str:
        """Compose the annotation note for an IE approximation.

        ``energy`` (IE ticks) and secondary outputs are surfaced here so the
        information is preserved without polluting the Bedrock schema.
        """
        parts = [f"ImmersiveEngineering {machine} recipe - approximated (Bedrock has no IE)"]

        energy = normalized_recipe.get("energy")
        if energy is not None:
            parts.append(f"Energy: {energy}")

        secondary_outputs = normalized_recipe.get("secondary_outputs", []) or []
        if secondary_outputs:
            secondary_items = [o.get("item", "") for o in secondary_outputs]
            parts.append(f"Secondary outputs: {secondary_items}")

        if extras:
            parts.append(extras)

        return " | ".join(parts)

    def convert_ie_crusher_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering crusher recipe to Bedrock format.

        Crusher recipes grind a single input (ore/ingot/gem) into a primary
        result plus optional ``secondaries`` byproducts. Approximated as a
        shapeless recipe since Bedrock has no IE Crusher; byproducts are
        preserved in the annotation note.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "IE crusher recipe has no input"
            )

        bedrock_ingredient = self._build_ie_ingredient(ingredients[0])
        bedrock_result = self._build_ie_result(normalized_recipe)
        note = self._build_ie_approximation_note("crusher", normalized_recipe)

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shapeless": {
                "description": {
                    "identifier": f"{namespace}:{recipe_name}_converted_from_immersiveengineering"
                },
                "tags": ["crafting_table", f"{self._IE_MACHINE_TAG}_crusher"],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
                "备注": note,
                "portkit:approximated_from": "immersiveengineering:crusher",
            },
        }

    def convert_ie_metalpress_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering metal press recipe to Bedrock format.

        Metal press recipes form a workpiece against a reusable ``mold`` item
        (plate/gear/rod/wire molds). Approximated as a shapeless recipe that
        consumes both the input and the mold identifier (mold is annotated as
        reusable so the packager can drop it from the actual consume list).
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "IE metal press recipe has no input"
            )

        bedrock_ingredient = self._build_ie_ingredient(ingredients[0])
        bedrock_result = self._build_ie_result(normalized_recipe)

        mold = normalized_recipe.get("mold")
        mold_extra = ""
        if mold:
            mold_item = mold.get("item", mold.get("id", "")) if isinstance(mold, dict) else mold
            mold_extra = f"Mold: {mold_item} (reusable)"

        note = self._build_ie_approximation_note(
            "metal press", normalized_recipe, extras=mold_extra
        )

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shapeless": {
                "description": {
                    "identifier": f"{namespace}:{recipe_name}_converted_from_immersiveengineering"
                },
                "tags": ["crafting_table", f"{self._IE_MACHINE_TAG}_metalpress"],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
                "备注": note,
                "portkit:approximated_from": "immersiveengineering:metalpress",
            },
        }

    def convert_ie_arc_furnace_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering arc furnace recipe to Bedrock format.

        Arc furnace recipes electrically smelt or alloy inputs. Approximated as
        a shapeless recipe; ``secondaries`` and the energy cost are preserved
        in the annotation note.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "IE arc furnace recipe has no input"
            )

        bedrock_ingredient = self._build_ie_ingredient(ingredients[0])
        bedrock_result = self._build_ie_result(normalized_recipe)
        note = self._build_ie_approximation_note("arc furnace", normalized_recipe)

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shapeless": {
                "description": {
                    "identifier": f"{namespace}:{recipe_name}_converted_from_immersiveengineering"
                },
                "tags": ["crafting_table", f"{self._IE_MACHINE_TAG}_arc_furnace"],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
                "备注": note,
                "portkit:approximated_from": "immersiveengineering:arc_furnace",
            },
        }

    def convert_ie_refinery_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering refinery recipe to Bedrock format.

        Refinery recipes mix fluid inputs into a fluid output — there is no
        faithful Bedrock approximation, so we emit a best-effort shapeless
        approximation carrying the energy cost in the annotation note. Fluid
        I/O is intentionally lossy here; a future fluid-aware pass can upgrade
        this branch.
        """
        ingredients = normalized_recipe.get("ingredients", [])
        if not ingredients:
            return self._create_manual_review_result(
                namespace, recipe_name, "IE refinery recipe has no input"
            )

        bedrock_ingredient = self._build_ie_ingredient(ingredients[0])
        bedrock_result = self._build_ie_result(normalized_recipe)
        note = self._build_ie_approximation_note("refinery", normalized_recipe)

        return {
            "format_version": "1.20.10",
            "minecraft:recipe_shapeless": {
                "description": {
                    "identifier": f"{namespace}:{recipe_name}_converted_from_immersiveengineering"
                },
                "tags": ["crafting_table", f"{self._IE_MACHINE_TAG}_refinery"],
                "ingredients": [bedrock_ingredient],
                "result": bedrock_result,
                "备注": note,
                "portkit:approximated_from": "immersiveengineering:refinery",
            },
        }


def is_custom_recipe_type(recipe_type: str) -> bool:
    """Check if a recipe type is a known custom Forge recipe type."""
    for custom_type in CUSTOM_RECIPE_TYPES.keys():
        if custom_type in recipe_type:
            return True
    return False


__all__ = [
    "CUSTOM_RECIPE_TYPES",
    "CustomTypesConverter",
    "is_custom_recipe_type",
    "_load_custom_recipe_types",
]
