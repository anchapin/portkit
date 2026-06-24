"""
Recipe converter package - handles all recipe conversion logic.

Modularized from recipe_converter.py for better organization.

Submodules:
- shaped: ShapedRecipeConverter
- shapeless: ShapelessRecipeConverter
- furnace: FurnaceRecipeConverter (smelting, blasting, smoking, campfire, stonecutter, smithing)
- custom_types: CustomTypesConverter (Farmer's Delight, Create, Forge custom recipes)
- tag_resolver: FORGE_TAG_MAPPINGS and JAVA_TO_BEDROCK_ITEM_MAP

Public API re-exports RecipeConverterAgent to maintain backwards compatibility.
"""

import json
import logging
from typing import ClassVar, Dict, List

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from agents.recipe.tag_resolver import (
    FORGE_TAG_MAPPINGS,
    JAVA_TO_BEDROCK_ITEM_MAP,
    resolve_tag_to_bedrock,
)

from agents.recipe.shaped import ShapedRecipeConverter
from agents.recipe.shapeless import ShapelessRecipeConverter
from agents.recipe.furnace import FurnaceRecipeConverter
from agents.recipe.custom_types import (
    CUSTOM_RECIPE_TYPES,
    CustomTypesConverter,
    is_custom_recipe_type,
)


logger = logging.getLogger(__name__)


class RecipeConverterAgent:
    """
    Agent responsible for converting Java mod recipes to Bedrock format.

    Supports:
    - Shaped recipes (crafting table)
    - Shapeless recipes
    - Furnace/smelting recipes
    - Blast furnace recipes
    - Smithing recipes
    - Campfire and smoking recipes
    - Stonecutter recipes
    - Custom Forge recipe types (Farmer's Delight, Create, etc.)
    - Create recipe types (mechanical_crafting, pressing, milling, crushing,
      deploying, splashing, compacting, mixing, sequenced_assembly, filling,
      emptying, cutting, haunting, sandpaper_polishing, item_application)
    """

    _instance = None

    def __init__(self):
        self.item_mapping = JAVA_TO_BEDROCK_ITEM_MAP.copy()
        self.custom_mappings = {}
        self.manual_review_reasons = []

        self._shaped_converter = ShapedRecipeConverter(self._map_java_item_to_bedrock)
        self._shapeless_converter = ShapelessRecipeConverter(self._map_java_item_to_bedrock)
        self._furnace_converter = FurnaceRecipeConverter(self._map_java_item_to_bedrock)
        self._custom_converter = CustomTypesConverter(self._map_java_item_to_bedrock)

    @classmethod
    def get_instance(cls):
        """Get singleton instance of RecipeConverterAgent"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self) -> List:
        """Get tools available to this agent"""
        return [
            RecipeConverterAgent.convert_recipe_tool,
            RecipeConverterAgent.convert_recipes_batch_tool,
            RecipeConverterAgent.map_item_id_tool,
            RecipeConverterAgent.validate_recipe_tool,
        ]

    def _map_java_item_to_bedrock(self, java_item_id: str) -> str:
        """Map a Java item ID to its Bedrock equivalent.

        For tag ingredients (starting with #), this method attempts to resolve them
        using FORGE_TAG_MAPPINGS first, then falls back to pattern-based resolution
        via resolve_tag_to_bedrock(). If resolution fails, returns None to signal
        that the recipe should be routed to manual review.

        Args:
            java_item_id: A Java item ID or tag like "minecraft:iron_ingot" or
                "#forge:ingots/iron"

        Returns:
            A Bedrock item ID string, or None if a tag could not be resolved.
        """
        if java_item_id in self.custom_mappings:
            return self.custom_mappings[java_item_id]
        if java_item_id in FORGE_TAG_MAPPINGS:
            return FORGE_TAG_MAPPINGS[java_item_id]
        if java_item_id in self.item_mapping:
            return self.item_mapping[java_item_id]
        java_lower = java_item_id.lower()
        for key, value in self.item_mapping.items():
            if key.lower() == java_lower:
                return value
        if java_item_id.startswith("#"):
            resolved = resolve_tag_to_bedrock(java_item_id)
            if resolved is not None:
                logger.debug(f"Resolved tag {java_item_id} to {resolved}")
                return resolved
            logger.warning(f"Unresolved Forge tag: {java_item_id}")
            return None
        logger.warning(f"No mapping found for item: {java_item_id}")
        return java_item_id

    def _parse_java_recipe(self, recipe_data: Dict) -> Dict:
        """Parse a Java recipe JSON into a normalized format."""
        recipe_type = recipe_data.get("type", "")

        normalized = {
            "original_type": recipe_type,
            "result_item": None,
            "result_count": 1,
            "result_data": 0,
            "ingredients": [],
            "pattern": [],
            "key": {},
            "cooking_time": None,
            "experience": 0.0,
            "requires_manual_review": False,
            "manual_review_reason": None,
            "container": None,
            "tool": None,
        }

        if "forge:conditional" in recipe_type:
            recipe_data = self._unwrap_conditional_recipe(recipe_data)
            recipe_type = recipe_data.get("type", "")

        result = recipe_data.get("result", {})
        if isinstance(result, dict):
            normalized["result_item"] = result.get("item", result.get("id", ""))
            normalized["result_count"] = result.get("count", 1)
            normalized["result_data"] = result.get("data", 0)
        elif isinstance(result, str):
            normalized["result_item"] = result
        elif isinstance(result, list) and len(result) > 0:
            first_result = result[0] if isinstance(result[0], dict) else {"item": result[0]}
            normalized["result_item"] = first_result.get("item", first_result.get("id", ""))
            normalized["result_count"] = first_result.get("count", 1)
            normalized["result_data"] = first_result.get("data", 0)
            if len(result) > 1:
                secondary_outputs = []
                for r in result[1:]:
                    if isinstance(r, dict):
                        secondary_outputs.append(
                            {
                                "item": r.get("item", r.get("id", "")),
                                "count": r.get("count", 1),
                                "data": r.get("data", 0),
                            }
                        )
                    elif isinstance(r, str):
                        secondary_outputs.append({"item": r, "count": 1, "data": 0})
                if secondary_outputs:
                    normalized["secondary_outputs"] = secondary_outputs

        if "crafting_shaped" in recipe_type:
            normalized["recipe_category"] = "shaped"
            normalized["pattern"] = recipe_data.get("pattern", [])
            normalized["key"] = recipe_data.get("key", {})
        elif "crafting_shapeless" in recipe_type:
            normalized["recipe_category"] = "shapeless"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
        elif "smelting" in recipe_type:
            normalized["recipe_category"] = "smelting"
            normalized["cooking_time"] = recipe_data.get("cookingtime", 200)
            normalized["experience"] = recipe_data.get("experience", 0.0)
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "blasting" in recipe_type:
            normalized["recipe_category"] = "blasting"
            normalized["cooking_time"] = recipe_data.get("cookingtime", 100)
            normalized["experience"] = recipe_data.get("experience", 0.0)
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "smoking" in recipe_type:
            normalized["recipe_category"] = "smoking"
            normalized["cooking_time"] = recipe_data.get("cookingtime", 100)
            normalized["experience"] = recipe_data.get("experience", 0.0)
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "campfire_cooking" in recipe_type:
            normalized["recipe_category"] = "campfire"
            normalized["cooking_time"] = recipe_data.get("cookingtime", 600)
            normalized["experience"] = recipe_data.get("experience", 0.0)
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "stonecutting" in recipe_type:
            normalized["recipe_category"] = "stonecutter"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "smithing_transform" in recipe_type:
            normalized["recipe_category"] = "smithing"
            normalized["base"] = recipe_data.get("base")
            normalized["addition"] = recipe_data.get("addition")
            normalized["template"] = recipe_data.get("template")
        elif "farmersdelight:cooking" in recipe_type:
            normalized["recipe_category"] = "cooking_pot"
            normalized["cooking_time"] = recipe_data.get("cookingtime", 200)
            normalized["experience"] = recipe_data.get("experience", 0.0)
            normalized["container"] = recipe_data.get("container")
            ingredients = recipe_data.get("ingredients") or []
            if not ingredients:
                ingredient = recipe_data.get("ingredient")
                if ingredient:
                    ingredients = [ingredient]
            normalized["ingredients"] = ingredients
        elif "farmersdelight:cutting" in recipe_type:
            normalized["recipe_category"] = "cutting_board"
            normalized["tool"] = recipe_data.get("tool")
            ingredients = recipe_data.get("ingredients", [])
            normalized["ingredients"] = ingredients
        elif "create:mechanical_crafting" in recipe_type:
            normalized["recipe_category"] = "mechanical_crafting"
            normalized["pattern"] = recipe_data.get("pattern", [])
            normalized["key"] = recipe_data.get("key", {})
        elif "create:pressing" in recipe_type:
            normalized["recipe_category"] = "pressing"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "create:sequenced_assembly" in recipe_type:
            normalized["recipe_category"] = "sequenced_assembly"
            normalized["transitions"] = recipe_data.get("sequence", [])
            normalized["ingredient"] = recipe_data.get("ingredient")
            normalized["intermediate"] = recipe_data.get("intermediate", "")
        elif "create:deploying" in recipe_type:
            normalized["recipe_category"] = "deploying"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
            normalized["tool"] = recipe_data.get("tool")
        elif "create:milling" in recipe_type:
            normalized["recipe_category"] = "milling"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
            normalized["heat_requirement"] = recipe_data.get("heatRequirement")
            normalized["min_rpm"] = recipe_data.get("minRPM")
            normalized["max_rpm"] = recipe_data.get("maxRPM")
        elif "create:crushing" in recipe_type:
            normalized["recipe_category"] = "crushing"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
            normalized["heat_requirement"] = recipe_data.get("heatRequirement")
            normalized["min_rpm"] = recipe_data.get("minRPM")
            normalized["max_rpm"] = recipe_data.get("maxRPM")
        elif "create:splashing" in recipe_type:
            normalized["recipe_category"] = "splashing"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
            normalized["min_rpm"] = recipe_data.get("minRPM")
            normalized["max_rpm"] = recipe_data.get("maxRPM")
        elif "create:compacting" in recipe_type:
            normalized["recipe_category"] = "compacting"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
            normalized["heat_requirement"] = recipe_data.get("heatRequirement")
            normalized["min_rpm"] = recipe_data.get("minRPM")
            normalized["max_rpm"] = recipe_data.get("maxRPM")
        elif "create:mixing" in recipe_type:
            normalized["recipe_category"] = "mixing"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
            normalized["heat_requirement"] = recipe_data.get("heatRequirement")
            normalized["min_rpm"] = recipe_data.get("minRPM")
            normalized["max_rpm"] = recipe_data.get("maxRPM")
        elif "create:filling" in recipe_type:
            normalized["recipe_category"] = "filling"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
        elif "create:emptying" in recipe_type:
            normalized["recipe_category"] = "emptying"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
        elif "create:cutting" in recipe_type:
            normalized["recipe_category"] = "cutting"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
            normalized["heat_requirement"] = recipe_data.get("heatRequirement")
        elif "create:haunting" in recipe_type:
            normalized["recipe_category"] = "haunting"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "create:sandpaper_polishing" in recipe_type:
            normalized["recipe_category"] = "sandpaper_polishing"
            ingredient = recipe_data.get("ingredient")
            if ingredient:
                normalized["ingredients"] = [ingredient]
        elif "create:item_application" in recipe_type:
            normalized["recipe_category"] = "item_application"
            normalized["ingredients"] = recipe_data.get("ingredients", [])
        elif "immersiveengineering:crusher" in recipe_type:
            normalized["recipe_category"] = "ie_crusher"
            normalized["ingredients"] = self._normalize_ie_input(recipe_data)
            normalized["secondary_outputs"] = self._normalize_ie_secondaries(recipe_data)
            normalized["energy"] = recipe_data.get("energy")
        elif "immersiveengineering:metalpress" in recipe_type:
            normalized["recipe_category"] = "ie_metalpress"
            normalized["ingredients"] = self._normalize_ie_input(recipe_data)
            normalized["mold"] = recipe_data.get("mold")
            normalized["energy"] = recipe_data.get("energy")
        elif "immersiveengineering:arc_furnace" in recipe_type:
            normalized["recipe_category"] = "ie_arc_furnace"
            normalized["ingredients"] = self._normalize_ie_input(recipe_data)
            normalized["secondary_outputs"] = self._normalize_ie_secondaries(recipe_data)
            normalized["energy"] = recipe_data.get("energy")
        elif "immersiveengineering:refinery" in recipe_type:
            normalized["recipe_category"] = "ie_refinery"
            normalized["ingredients"] = self._normalize_ie_input(recipe_data)
            normalized["energy"] = recipe_data.get("energy")
        elif is_custom_recipe_type(recipe_type):
            normalized["recipe_category"] = "custom"
            normalized["requires_manual_review"] = True
            normalized["manual_review_reason"] = (
                f"Custom Forge recipe type '{recipe_type}' requires manual review"
            )
        else:
            normalized["recipe_category"] = "unknown"
            normalized["requires_manual_review"] = True
            normalized["manual_review_reason"] = f"Unknown recipe type: {recipe_type}"
            logger.warning(f"Unknown recipe type: {recipe_type}")

        return normalized

    def _unwrap_conditional_recipe(self, recipe_data: Dict) -> Dict:
        """Unwrap a forge:conditional recipe to get the inner recipe."""
        if "recipe" in recipe_data:
            inner = recipe_data["recipe"]
            if isinstance(inner, dict):
                return inner
        return recipe_data

    @staticmethod
    def _normalize_ie_input(recipe_data: Dict) -> list:
        """Normalize an ImmersiveEngineering ``input`` field into a list of ingredients.

        IE recipes use a single ``input`` key (an ingredient dict, a tag string,
        or a list of alternative ingredients) rather than the vanilla
        ``ingredient``/``ingredients`` keys. This helper wraps it into the list
        shape the rest of the converter pipeline expects.
        """
        raw = recipe_data.get("input")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return [raw]

    @staticmethod
    def _normalize_ie_secondaries(recipe_data: Dict) -> list:
        """Normalize an ImmersiveEngineering ``secondaries`` array.

        IE ``secondaries`` entries look like ``{"chance": 0.1, "output": {...}}``;
        downstream converters only care about the ``output`` item/count, so each
        entry is flattened to ``{"item", "count", "chance"}``. Returns an empty
        list when there are no secondaries.
        """
        secondaries = recipe_data.get("secondaries") or []
        normalized = []
        for entry in secondaries:
            if not isinstance(entry, dict):
                continue
            output = entry.get("output", entry)
            if isinstance(output, dict):
                item = output.get("item", output.get("id", ""))
                count = output.get("count", 1)
            else:
                item = output
                count = 1
            secondary = {"item": item, "count": count}
            if "chance" in entry:
                secondary["chance"] = entry["chance"]
            normalized.append(secondary)
        return normalized

    def _convert_shaped_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a shaped recipe to Bedrock format."""
        return self._shaped_converter.convert_to_bedrock(normalized_recipe, namespace, recipe_name)

    def _convert_shapeless_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a shapeless recipe to Bedrock format."""
        return self._shapeless_converter.convert_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_smelting_to_bedrock(
        self,
        normalized_recipe: Dict,
        namespace: str,
        recipe_name: str,
        recipe_type: str = "smelting",
    ) -> Dict:
        """Convert a furnace-type recipe to Bedrock format."""
        return self._furnace_converter.convert_smelting_to_bedrock(
            normalized_recipe, namespace, recipe_name, recipe_type
        )

    def _convert_stonecutter_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a stonecutter recipe to Bedrock format."""
        return self._furnace_converter.convert_stonecutter_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_smithing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a smithing recipe to Bedrock format."""
        return self._furnace_converter.convert_smithing_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_cooking_pot_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Farmer's Delight cooking pot recipe to Bedrock format."""
        return self._custom_converter.convert_cooking_pot_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_cutting_board_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Farmer's Delight cutting board recipe to Bedrock format."""
        return self._custom_converter.convert_cutting_board_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_mechanical_crafting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create mechanical crafting recipe to Bedrock format."""
        return self._custom_converter.convert_mechanical_crafting_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_pressing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create pressing recipe to Bedrock format."""
        return self._custom_converter.convert_pressing_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_milling_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create milling recipe to Bedrock format."""
        return self._custom_converter.convert_milling_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_crushing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create crushing recipe to Bedrock format."""
        return self._custom_converter.convert_crushing_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_deploying_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create deploying recipe to Bedrock format."""
        return self._custom_converter.convert_deploying_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_splashing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create splashing recipe to Bedrock format."""
        return self._custom_converter.convert_splashing_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_compacting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create compacting recipe to Bedrock format."""
        return self._custom_converter.convert_compacting_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_mixing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create mixing recipe to Bedrock format."""
        return self._custom_converter.convert_mixing_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_sequenced_assembly_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create sequenced assembly recipe to Bedrock format."""
        return self._custom_converter.convert_sequenced_assembly_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_filling_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create filling recipe to Bedrock format."""
        return self._custom_converter.convert_filling_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_emptying_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create emptying recipe to Bedrock format."""
        return self._custom_converter.convert_emptying_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_cutting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create cutting recipe to Bedrock format."""
        return self._custom_converter.convert_cutting_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_haunting_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create haunting recipe to Bedrock format."""
        return self._custom_converter.convert_haunting_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_sandpaper_polishing_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create sandpaper polishing recipe to Bedrock format."""
        return self._custom_converter.convert_sandpaper_polishing_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_item_application_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert a Create item application recipe to Bedrock format."""
        return self._custom_converter.convert_item_application_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_ie_crusher_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering crusher recipe to Bedrock format."""
        return self._custom_converter.convert_ie_crusher_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_ie_metalpress_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering metal press recipe to Bedrock format."""
        return self._custom_converter.convert_ie_metalpress_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_ie_arc_furnace_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering arc furnace recipe to Bedrock format."""
        return self._custom_converter.convert_ie_arc_furnace_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _convert_ie_refinery_to_bedrock(
        self, normalized_recipe: Dict, namespace: str, recipe_name: str
    ) -> Dict:
        """Convert an ImmersiveEngineering refinery recipe to Bedrock format."""
        return self._custom_converter.convert_ie_refinery_to_bedrock(
            normalized_recipe, namespace, recipe_name
        )

    def _create_manual_review_result(self, namespace: str, recipe_name: str, reason: str) -> Dict:
        """Create a result indicating the recipe requires manual review."""
        return {
            "format_version": "1.20.10",
            "manual_review_required": True,
            "reason": reason,
            "original_recipe": f"{namespace}:{recipe_name}",
            "description": {"identifier": f"{namespace}:{recipe_name}"},
        }

    def convert_recipe(
        self, recipe_data: Dict, namespace: str = "mod", recipe_name: str = None
    ) -> Dict:
        """Convert a Java recipe to Bedrock format."""
        normalized = self._parse_java_recipe(recipe_data)

        if not recipe_name:
            result_item = normalized.get("result_item", "unknown")
            if ":" in result_item:
                _, item_name = result_item.split(":", 1)
                recipe_name = item_name
            else:
                recipe_name = result_item

        category = normalized.get("recipe_category", "unknown")

        if category == "shaped":
            return self._convert_shaped_to_bedrock(normalized, namespace, recipe_name)
        elif category == "shapeless":
            return self._convert_shapeless_to_bedrock(normalized, namespace, recipe_name)
        elif category == "smelting":
            return self._convert_smelting_to_bedrock(normalized, namespace, recipe_name, "smelting")
        elif category == "blasting":
            return self._convert_smelting_to_bedrock(normalized, namespace, recipe_name, "blasting")
        elif category == "smoking":
            return self._convert_smelting_to_bedrock(normalized, namespace, recipe_name, "smoking")
        elif category == "campfire":
            return self._convert_smelting_to_bedrock(normalized, namespace, recipe_name, "campfire")
        elif category == "stonecutter":
            return self._convert_stonecutter_to_bedrock(normalized, namespace, recipe_name)
        elif category == "smithing":
            return self._convert_smithing_to_bedrock(normalized, namespace, recipe_name)
        elif category == "cooking_pot":
            return self._convert_cooking_pot_to_bedrock(normalized, namespace, recipe_name)
        elif category == "cutting_board":
            return self._convert_cutting_board_to_bedrock(normalized, namespace, recipe_name)
        elif category == "mechanical_crafting":
            return self._convert_mechanical_crafting_to_bedrock(normalized, namespace, recipe_name)
        elif category == "pressing":
            return self._convert_pressing_to_bedrock(normalized, namespace, recipe_name)
        elif category == "milling":
            return self._convert_milling_to_bedrock(normalized, namespace, recipe_name)
        elif category == "crushing":
            return self._convert_crushing_to_bedrock(normalized, namespace, recipe_name)
        elif category == "deploying":
            return self._convert_deploying_to_bedrock(normalized, namespace, recipe_name)
        elif category == "splashing":
            return self._convert_splashing_to_bedrock(normalized, namespace, recipe_name)
        elif category == "compacting":
            return self._convert_compacting_to_bedrock(normalized, namespace, recipe_name)
        elif category == "mixing":
            return self._convert_mixing_to_bedrock(normalized, namespace, recipe_name)
        elif category == "sequenced_assembly":
            return self._convert_sequenced_assembly_to_bedrock(normalized, namespace, recipe_name)
        elif category == "filling":
            return self._convert_filling_to_bedrock(normalized, namespace, recipe_name)
        elif category == "emptying":
            return self._convert_emptying_to_bedrock(normalized, namespace, recipe_name)
        elif category == "cutting":
            return self._convert_cutting_to_bedrock(normalized, namespace, recipe_name)
        elif category == "haunting":
            return self._convert_haunting_to_bedrock(normalized, namespace, recipe_name)
        elif category == "sandpaper_polishing":
            return self._convert_sandpaper_polishing_to_bedrock(normalized, namespace, recipe_name)
        elif category == "item_application":
            return self._convert_item_application_to_bedrock(normalized, namespace, recipe_name)
        elif category == "ie_crusher":
            return self._convert_ie_crusher_to_bedrock(normalized, namespace, recipe_name)
        elif category == "ie_metalpress":
            return self._convert_ie_metalpress_to_bedrock(normalized, namespace, recipe_name)
        elif category == "ie_arc_furnace":
            return self._convert_ie_arc_furnace_to_bedrock(normalized, namespace, recipe_name)
        elif category == "ie_refinery":
            return self._convert_ie_refinery_to_bedrock(normalized, namespace, recipe_name)
        elif category == "custom":
            reason = normalized.get("manual_review_reason", "Unknown custom Forge recipe type")
            return self._create_manual_review_result(namespace, recipe_name, reason)
        else:
            logger.warning(f"Cannot convert unknown recipe category: {category}")
            return {"success": False, "error": f"Unknown recipe category: {category}"}

    def add_custom_item_mapping(self, java_item_id: str, bedrock_item_id: str):
        """Add a custom Java to Bedrock item mapping."""
        self.custom_mappings[java_item_id] = bedrock_item_id

    @staticmethod
    def _convert_recipe(recipe_json: str) -> str:
        """Convert a Java recipe to Bedrock format."""
        try:
            input_data = json.loads(recipe_json)
            agent = RecipeConverterAgent.get_instance()

            if "recipe_data" in input_data and isinstance(input_data["recipe_data"], dict):
                recipe_data = input_data["recipe_data"]
                namespace = input_data.get("namespace") or recipe_data.pop("namespace", "mod")
                recipe_name = input_data.get("recipe_name") or recipe_data.pop("recipe_name", None)
            else:
                recipe_data = input_data
                namespace = recipe_data.pop("namespace", "mod")
                recipe_name = recipe_data.pop("recipe_name", None)

            result = agent.convert_recipe(recipe_data, namespace, recipe_name)

            return json.dumps({"success": True, "converted_recipe": result}, indent=2)

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @staticmethod
    def _convert_recipes_batch(recipes_json: str) -> str:
        """Convert multiple Java recipes to Bedrock format in batch."""
        try:
            recipes = json.loads(recipes_json)
            agent = RecipeConverterAgent.get_instance()

            results = []
            for item in recipes:
                if "recipe_data" in item and isinstance(item["recipe_data"], dict):
                    recipe_data = item["recipe_data"]
                    namespace = item.get("namespace") or recipe_data.pop("namespace", "mod")
                    recipe_name = item.get("recipe_name") or recipe_data.pop("recipe_name", None)
                else:
                    recipe_data = item
                    namespace = recipe_data.pop("namespace", "mod")
                    recipe_name = recipe_data.pop("recipe_name", None)

                converted = agent.convert_recipe(recipe_data, namespace, recipe_name)
                results.append(converted)

            return json.dumps(
                {"success": True, "converted_recipes": results, "total_count": len(results)},
                indent=2,
            )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @staticmethod
    def _map_item_id(item_mapping_json: str) -> str:
        """Add custom Java to Bedrock item ID mappings."""
        try:
            mappings = json.loads(item_mapping_json)
            agent = RecipeConverterAgent.get_instance()

            if isinstance(mappings, list):
                for mapping in mappings:
                    if isinstance(mapping, dict) and "java" in mapping and "bedrock" in mapping:
                        agent.add_custom_item_mapping(mapping["java"], mapping["bedrock"])
            elif isinstance(mappings, dict):
                for java_id, bedrock_id in mappings.items():
                    agent.add_custom_item_mapping(java_id, bedrock_id)

            return json.dumps({"success": True, "message": "Custom item mappings added"}, indent=2)

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @staticmethod
    def _validate_recipe(recipe_json: str) -> str:
        """Validate a Bedrock recipe for correctness."""
        try:
            recipe = json.loads(recipe_json)
            issues = []

            if "format_version" not in recipe:
                issues.append("Missing format_version")

            recipe_types = [
                "minecraft:recipe_shaped",
                "minecraft:recipe_shapeless",
                "minecraft:recipe_furnace",
                "minecraft:recipe_furnace_blast",
                "minecraft:recipe_furnace_smoke",
                "minecraft:recipe_campfire",
                "minecraft:recipe_stonecutter",
                "minecraft:recipe_smithing_transform",
            ]

            found_type = None
            for rt in recipe_types:
                if rt in recipe:
                    found_type = rt
                    break

            if not found_type:
                issues.append("Unknown recipe type")
                return json.dumps({"valid": False, "issues": issues}, indent=2)

            recipe_content = recipe.get(found_type, {})

            if "description" not in recipe_content:
                issues.append("Missing description")
            elif "identifier" not in recipe_content.get("description", {}):
                issues.append("Missing description.identifier")

            if found_type == "minecraft:recipe_shaped":
                if "pattern" not in recipe_content:
                    issues.append("Missing pattern")
                if "key" not in recipe_content:
                    issues.append("Missing key")
                if "result" not in recipe_content:
                    issues.append("Missing result")
            elif found_type == "minecraft:recipe_shapeless":
                if "ingredients" not in recipe_content:
                    issues.append("Missing ingredients")
                if "result" not in recipe_content:
                    issues.append("Missing result")
            elif "recipe_furnace" in found_type or found_type == "minecraft:recipe_campfire":
                if "ingredients" not in recipe_content:
                    issues.append("Missing ingredients")
                if "result" not in recipe_content:
                    issues.append("Missing result")
            elif found_type == "minecraft:recipe_stonecutter":
                if "ingredients" not in recipe_content:
                    issues.append("Missing ingredients")
                if "result" not in recipe_content:
                    issues.append("Missing result")

            is_valid = len(issues) == 0

            return json.dumps(
                {"valid": is_valid, "recipe_type": found_type, "issues": issues}, indent=2
            )

        except Exception as e:
            return json.dumps({"valid": False, "issues": [str(e)]}, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Typed args_schema models — one per LangChain tool wrapper
#
# Phase 8 A5 (refs #1201). Each schema preserves the legacy single-string
# JSON shape so chat models and existing call sites continue to invoke
# ``RecipeConverterAgent.<tool_name>.invoke({...})`` (or the legacy
# ``.run(<json_string>)``) without changes. ``extra="forbid"`` makes
# hallucinated extra fields fail loud at validation, and ``min_length=1``
# rejects empty strings.
# ─────────────────────────────────────────────────────────────────────────────


class _ConvertRecipeInput(BaseModel):
    """Args for :class:`_ConvertRecipeTool`."""

    model_config = ConfigDict(extra="forbid")
    recipe_json: str = Field(
        min_length=1,
        description=(
            "JSON string describing a single Java recipe to convert. May contain "
            "an optional ``recipe_data``, ``namespace``, and ``recipe_name``."
        ),
    )


class _ConvertRecipesBatchInput(BaseModel):
    """Args for :class:`_ConvertRecipesBatchTool`."""

    model_config = ConfigDict(extra="forbid")
    recipes_json: str = Field(
        min_length=1,
        description="JSON-encoded list of Java recipes to convert in a batch.",
    )


class _MapItemIdInput(BaseModel):
    """Args for :class:`_MapItemIdTool`."""

    model_config = ConfigDict(extra="forbid")
    item_mapping_json: str = Field(
        min_length=1,
        description=(
            "JSON-encoded list of {java, bedrock} mappings, or dict of "
            "{java_id: bedrock_id} mappings, to register on the converter."
        ),
    )


class _ValidateRecipeInput(BaseModel):
    """Args for :class:`_ValidateRecipeTool`."""

    model_config = ConfigDict(extra="forbid")
    recipe_json: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock recipe to validate.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Typed BaseTool subclasses — replace the previous @tool @staticmethod wrappers
# ─────────────────────────────────────────────────────────────────────────────


class _BaseRecipeTool(BaseTool):
    """Common scaffolding for Recipe Converter typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class _ConvertRecipeTool(_BaseRecipeTool):
    name: str = "convert_recipe_tool"
    description: str = (
        "Convert a single Java recipe to Bedrock JSON. "
        "Args: recipe_json (str, required) — JSON describing the Java recipe, "
        "optionally wrapped in {recipe_data, namespace, recipe_name}."
    )
    args_schema: ClassVar[type[BaseModel]] = _ConvertRecipeInput

    def _run(self, recipe_json: str) -> str:  # type: ignore[override]
        return RecipeConverterAgent._convert_recipe(recipe_json)


class _ConvertRecipesBatchTool(_BaseRecipeTool):
    name: str = "convert_recipes_batch_tool"
    description: str = (
        "Convert a batch of Java recipes to Bedrock JSON. "
        "Args: recipes_json (str, required) — JSON list of Java recipes."
    )
    args_schema: ClassVar[type[BaseModel]] = _ConvertRecipesBatchInput

    def _run(self, recipes_json: str) -> str:  # type: ignore[override]
        return RecipeConverterAgent._convert_recipes_batch(recipes_json)


class _MapItemIdTool(_BaseRecipeTool):
    name: str = "map_item_id_tool"
    description: str = (
        "Register custom Java→Bedrock item-ID mappings on the converter. "
        "Args: item_mapping_json (str, required) — JSON list or dict of mappings."
    )
    args_schema: ClassVar[type[BaseModel]] = _MapItemIdInput

    def _run(self, item_mapping_json: str) -> str:  # type: ignore[override]
        return RecipeConverterAgent._map_item_id(item_mapping_json)


class _ValidateRecipeTool(_BaseRecipeTool):
    name: str = "validate_recipe_tool"
    description: str = (
        "Validate a Bedrock recipe against expected structure. "
        "Args: recipe_json (str, required) — JSON of the Bedrock recipe."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateRecipeInput

    def _run(self, recipe_json: str) -> str:  # type: ignore[override]
        return RecipeConverterAgent._validate_recipe(recipe_json)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level tool instances — preserved as class attributes on
# RecipeConverterAgent so the existing access patterns
# (``RecipeConverterAgent.<tool_name>`` and ``agent.<tool_name>``) both
# continue to work unchanged for call sites and tests, including the
# legacy ``tool_func.run(<json_string>)`` shape exercised by
# ``tests/test_recipe_converter.py``.
# ─────────────────────────────────────────────────────────────────────────────


RecipeConverterAgent.convert_recipe_tool = _ConvertRecipeTool()
RecipeConverterAgent.convert_recipes_batch_tool = _ConvertRecipesBatchTool()
RecipeConverterAgent.map_item_id_tool = _MapItemIdTool()
RecipeConverterAgent.validate_recipe_tool = _ValidateRecipeTool()


__all__ = [
    "RecipeConverterAgent",
    "FORGE_TAG_MAPPINGS",
    "JAVA_TO_BEDROCK_ITEM_MAP",
    "CUSTOM_RECIPE_TYPES",
]
