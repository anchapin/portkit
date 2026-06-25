"""
Block and Item Generator for creating Bedrock block and item definitions.
Part of the entity/ subpackage for Issue #1276 refactoring.
Provides the same public API as the original block_item_generator module.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.entity.block_generator import generate_blocks, write_blocks_to_disk
from agents.entity.block_state_parser import CREATIVE_CATEGORIES
from agents.entity.item_generator import (
    generate_items,
    generate_tool_item,
    generate_armor_item,
    generate_consumable_item,
    generate_ranged_weapon_item,
    generate_rare_item,
    write_items_to_disk,
)
from agents.entity.nbt_parser import (
    ArmorProperties,
    ArmorType,
    BlockProperties,
    ConsumableProperties,
    ItemProperties,
    MaterialType,
    RangedWeaponProperties,
    RareItemProperties,
    ToolProperties,
    ToolType,
)

logger = logging.getLogger(__name__)


class BlockItemGenerator:
    """
    Generator for Bedrock block and item definition files.
    Converts Java mod blocks and items to Bedrock format.
    """

    def __init__(self):
        self.block_template = {
            "format_version": "1.19.0",
            "minecraft:block": {
                "description": {"identifier": "", "register_to_creative_menu": True},
                "components": {},
                "events": {},
            },
        }

        self.item_template = {
            "format_version": "1.19.0",
            "minecraft:item": {
                "description": {"identifier": "", "register_to_creative_menu": True},
                "components": {},
            },
        }

        self.creative_categories = CREATIVE_CATEGORIES.copy()

    def generate_blocks(self, java_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate Bedrock block definitions from Java blocks.

        Args:
            java_blocks: List of Java block definitions

        Returns:
            Dictionary of Bedrock block definitions
        """
        return generate_blocks(java_blocks)

    def generate_items(self, java_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate Bedrock item definitions from Java items.

        Args:
            java_items: List of Java item definitions

        Returns:
            Dictionary of Bedrock item definitions
        """
        return generate_items(java_items)

    def generate_recipes(
        self, java_recipes: List[Dict[str, Any]], namespace: str = "mod"
    ) -> Dict[str, Any]:
        """
        Convert Java recipes to Bedrock format using RecipeConverterAgent.

        Args:
            java_recipes: List of Java recipe definitions
            namespace: Namespace for the recipes (default: "mod")

        Returns:
            Dictionary of Bedrock recipes
        """
        from agents.recipe_converter import RecipeConverterAgent

        logger.info(f"Converting {len(java_recipes)} Java recipes to Bedrock format")
        bedrock_recipes = {}
        manual_review_count = 0

        recipe_converter = RecipeConverterAgent.get_instance()

        for java_recipe in java_recipes:
            try:
                result_item = java_recipe.get("result", {})
                if isinstance(result_item, dict):
                    result_item_id = result_item.get("item", result_item.get("id", "unknown"))
                elif isinstance(result_item, str):
                    result_item_id = result_item
                elif isinstance(result_item, list) and len(result_item) > 0:
                    first = result_item[0]
                    result_item_id = (
                        first.get("item", first.get("id", "unknown"))
                        if isinstance(first, dict)
                        else str(first)
                    )
                else:
                    result_item_id = "unknown"

                if ":" in result_item_id:
                    _, recipe_name = result_item_id.split(":", 1)
                else:
                    recipe_name = result_item_id

                bedrock_recipe = recipe_converter.convert_recipe(
                    java_recipe, namespace, recipe_name
                )

                if (
                    bedrock_recipe
                    and not isinstance(bedrock_recipe, dict)
                    or (
                        isinstance(bedrock_recipe, dict) and not bedrock_recipe.get("success", True)
                    )
                ):
                    if isinstance(bedrock_recipe, dict) and bedrock_recipe.get("success") is False:
                        logger.warning(
                            f"Recipe conversion failed: {bedrock_recipe.get('error', 'Unknown error')}"
                        )
                        continue

                if isinstance(bedrock_recipe, dict):
                    recipe_id = None
                    for recipe_key, recipe_content in bedrock_recipe.items():
                        if recipe_key.startswith("minecraft:recipe_"):
                            recipe_id = recipe_content.get("description", {}).get(
                                "identifier", f"recipe_{len(bedrock_recipes)}"
                            )
                            break
                    else:
                        if "identifier" in bedrock_recipe:
                            recipe_id = bedrock_recipe["identifier"]
                        elif bedrock_recipe.get("manual_review_required"):
                            logger.info(
                                f"Recipe {java_recipe.get('id', 'unknown')} flagged for manual review: "
                                f"{bedrock_recipe.get('reason', 'Unknown reason')}"
                            )
                            manual_review_count += 1

                    if recipe_id:
                        if recipe_id in bedrock_recipes:
                            raw_ingredients = java_recipe.get("ingredients") or [
                                java_recipe.get("ingredient", {})
                            ]
                            input_suffix = ""
                            if isinstance(raw_ingredients, list) and len(raw_ingredients) > 0:
                                first_ing = raw_ingredients[0]
                                if isinstance(first_ing, dict):
                                    item_id = first_ing.get("item", first_ing.get("tag", ""))
                                    if item_id:
                                        slug = (
                                            item_id.split(":")[-1]
                                            .replace("/", "_")
                                            .replace("\\", "_")
                                        )
                                        input_suffix = "_from_" + slug
                            if input_suffix:
                                recipe_id = f"{recipe_id}{input_suffix}"
                            else:
                                recipe_id = f"{recipe_id}_alt_{len(bedrock_recipes)}"
                        bedrock_recipes[recipe_id] = bedrock_recipe
            except Exception as e:
                logger.error(f"Failed to convert recipe {java_recipe.get('id', 'unknown')}: {e}")
                continue

        logger.info(
            f"Successfully converted {len(bedrock_recipes)} recipes ({manual_review_count} flagged for manual review)"
        )
        return bedrock_recipes

    def generate_tool_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a Bedrock tool item definition.

        Args:
            data: Dictionary containing tool data

        Returns:
            Bedrock item definition JSON
        """
        return generate_tool_item(data)

    def generate_armor_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a Bedrock armor item definition.

        Args:
            data: Dictionary containing armor data

        Returns:
            Bedrock item definition JSON
        """
        return generate_armor_item(data)

    def generate_consumable_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a Bedrock consumable item definition (food, potions).

        Args:
            data: Dictionary containing consumable data

        Returns:
            Bedrock item definition JSON
        """
        return generate_consumable_item(data)

    def generate_ranged_weapon_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a Bedrock ranged weapon item definition (bow, crossbow).

        Args:
            data: Dictionary containing ranged weapon data

        Returns:
            Bedrock item definition JSON
        """
        return generate_ranged_weapon_item(data)

    def generate_rare_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a Bedrock rare/special item definition with enchantments.

        Args:
            data: Dictionary containing rare item data

        Returns:
            Bedrock item definition JSON
        """
        return generate_rare_item(data)

    def _convert_java_block(self, java_block: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single Java block to Bedrock format."""
        from agents.entity.block_generator import convert_java_block as convert

        return convert(java_block)

    def _convert_java_item(self, java_item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single Java item to Bedrock format."""
        from agents.entity.item_generator import convert_java_item as convert

        return convert(java_item)

    def _parse_java_block_properties(self, java_block: Dict[str, Any]) -> BlockProperties:
        """Parse Java block properties."""
        from agents.entity.nbt_parser import parse_java_block_properties as parse

        return parse(java_block)

    def _parse_java_item_properties(self, java_item: Dict[str, Any]) -> ItemProperties:
        """Parse Java item properties."""
        from agents.entity.nbt_parser import parse_java_item_properties as parse

        return parse(java_item)

    def _determine_block_category(self, java_block: Dict[str, Any]) -> Optional[str]:
        """Determine appropriate creative menu category for block."""
        from agents.entity.block_state_parser import determine_block_category

        return determine_block_category(java_block)

    def _determine_item_category(self, java_item: Dict[str, Any]) -> Optional[str]:
        """Determine appropriate creative menu category for item."""
        from agents.entity.block_state_parser import determine_item_category

        return determine_item_category(java_item)

    def _write_json_files(
        self, definitions: Dict[str, Any], directory: Path, written_files: List[Path]
    ) -> None:
        """Helper method to write JSON definitions to a directory."""
        directory.mkdir(parents=True, exist_ok=True)
        for item_id, definition in definitions.items():
            file_path = directory / f"{item_id.split(':')[-1]}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(definition, f, indent=2, ensure_ascii=False)
            written_files.append(file_path)

    def write_definitions_to_disk(
        self,
        blocks: Dict[str, Any],
        items: Dict[str, Any],
        recipes: Dict[str, Any],
        bp_path: Path,
        rp_path: Path,
    ) -> Dict[str, List[Path]]:
        """Write block, item, and recipe definitions to disk."""
        written_files = {"blocks": [], "items": [], "recipes": []}

        if blocks:
            written_files["blocks"] = write_blocks_to_disk(blocks, bp_path, rp_path)

        if items:
            written_files["items"] = write_items_to_disk(items, bp_path)

        if recipes:
            self._write_json_files(recipes, bp_path / "recipes", written_files["recipes"])

        logger.info(
            f"Written {len(written_files['blocks'])} blocks, "
            f"{len(written_files['items'])} items, "
            f"{len(written_files['recipes'])} recipes to disk"
        )

        return written_files


class MaterialType:
    """Material type enum for backward compatibility."""

    STONE = "stone"
    WOOD = "wood"
    METAL = "metal"
    GLASS = "glass"
    CLOTH = "cloth"
    DIRT = "dirt"
    SAND = "sand"
    SNOW = "snow"
    ICE = "ice"
    WATER = "water"
    LAVA = "lava"


class ToolType:
    """Tool type enum for backward compatibility."""

    PICKAXE = "pickaxe"
    AXE = "axe"
    SHOVEL = "shovel"
    HOE = "hoe"
    SWORD = "sword"
    SHEARS = "shears"
    BOW = "bow"
    CROSSBOW = "crossbow"
    TRIDENT = "trident"


class ArmorType:
    """Armor type enum for backward compatibility."""

    HELMET = "helmet"
    CHESTPLATE = "chestplate"
    LEGGINGS = "leggings"
    BOOTS = "boots"
