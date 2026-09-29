"""Bedrock block and recipe translation.

Split out from ``translator.py`` per Issue #1746. Provides generation and
validation of Bedrock block JSON from Java block analysis, plus crafting
recipe conversion and block property mapping.

The :class:`BlockTranslatorMixin` is composed into :class:`LogicTranslatorAgent`
and assumes the host class provides ``self.logger``.
"""

import json
from typing import Any, Dict

from agents.logic_translator.block_state_mapper import (
    JAVA_TO_BEDROCK_BLOCK_PROPERTIES,
)
from agents.logic_translator.block_templates import (
    BEDROCK_BLOCK_TEMPLATES,
)
from utils.logging_config import get_agent_logger

logger = get_agent_logger("logic_translator")


class BlockTranslatorMixin:
    """Bedrock block/recipe translation methods for the LogicTranslatorAgent."""

    def translate_crafting_recipe_json(self, recipe_json_data: str) -> str:
        """Translate crafting recipe JSON to Bedrock format."""
        try:
            data = json.loads(recipe_json_data)
            recipe_type = data.get("type", "unknown")

            if recipe_type == "minecraft:crafting_shaped":
                pattern = data.get("pattern", ["ABC", "DEF", "GHI"])
                key = data.get("key", {"A": {"item": "minecraft:stick"}})
                result = data.get("result", {"item": "minecraft:wooden_sword"})

                bedrock_key = {}
                for k, v in key.items():
                    bedrock_key[k] = {"item": v["item"].replace("minecraft:", "")}

                bedrock_result = {"item": result["item"].replace("minecraft:", "")}
                if "count" in result:
                    bedrock_result["count"] = result["count"]

                bedrock_recipe = {
                    "format_version": "1.17.0",
                    "minecraft:recipe_shaped": {
                        "description": {"identifier": "custom:shaped_recipe"},
                        "pattern": pattern,
                        "key": bedrock_key,
                        "result": bedrock_result,
                    },
                }
            elif recipe_type == "minecraft:crafting_shapeless":
                ingredients = data.get("ingredients", [{"item": "minecraft:stick"}])
                result = data.get("result", {"item": "minecraft:wooden_sword"})

                bedrock_ingredients = []
                for ingredient in ingredients:
                    bedrock_ingredients.append(
                        {"item": ingredient["item"].replace("minecraft:", "")}
                    )

                bedrock_result = {"item": result["item"].replace("minecraft:", "")}
                if "count" in result:
                    bedrock_result["count"] = result["count"]

                bedrock_recipe = {
                    "format_version": "1.17.0",
                    "minecraft:recipe_shapeless": {
                        "description": {"identifier": "custom:shapeless_recipe"},
                        "ingredients": bedrock_ingredients,
                        "result": bedrock_result,
                    },
                }
            else:
                raise ValueError(f"Unsupported recipe type: {recipe_type}")

            return json.dumps({"success": True, "bedrock_recipe": bedrock_recipe, "warnings": []})
        except Exception as e:
            logger.error(f"Error translating recipe: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def generate_bedrock_block_json(
        self,
        java_block_analysis: Dict[str, Any],
        namespace: str = "modporter",
        use_rag: bool = True,
    ) -> Dict[str, Any]:
        """Generate Bedrock block JSON from Java block analysis."""
        try:
            logger.info(
                f"Generating Bedrock block JSON for: {java_block_analysis.get('name', 'unknown')}"
            )

            block_name = java_block_analysis.get("registry_name", "unknown_block")
            if ":" in block_name:
                namespace, block_name = block_name.split(":", 1)

            properties = java_block_analysis.get("properties", {})

            template_type = self._determine_block_template(properties)
            template = BEDROCK_BLOCK_TEMPLATES.get(template_type, BEDROCK_BLOCK_TEMPLATES["basic"])

            block_json = self._build_block_json(
                template=template, namespace=namespace, block_name=block_name, properties=properties
            )

            validation_result = self._validate_block_json(block_json)

            translation_log = {
                "original_java_block": java_block_analysis.get("name", "unknown"),
                "template_used": template_type,
                "properties_mapped": list(properties.keys()),
                "validation_passed": validation_result["is_valid"],
            }
            logger.info(f"Block generation complete: {translation_log}")

            return {
                "success": True,
                "block_json": block_json,
                "block_name": f"{namespace}:{block_name}",
                "validation": validation_result,
                "translation_log": translation_log,
                "warnings": validation_result.get("warnings", []),
            }

        except Exception as e:
            logger.error(f"Error generating Bedrock block JSON: {e}")
            return {
                "success": False,
                "error": str(e),
                "block_json": None,
                "warnings": [f"Block generation failed: {str(e)}"],
            }

    def validate_block_json(self, block_json_data: str) -> str:
        """Validate a Bedrock block JSON against schema requirements."""
        try:
            data = json.loads(block_json_data)
            block_json = data.get("block_json", {})

            is_valid = "format_version" in block_json and "minecraft:block" in block_json

            return json.dumps(
                {
                    "success": True,
                    "is_valid": is_valid,
                    "errors": [] if is_valid else ["Missing required fields"],
                    "warnings": [],
                }
            )
        except Exception as e:
            logger.error(f"Error validating block JSON: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def map_block_properties(self, properties_data: str) -> str:
        """Map Java block properties to Bedrock equivalents."""
        try:
            data = json.loads(properties_data)
            java_properties = data.get("properties", {})

            bedrock_properties = {}
            for key, value in java_properties.items():
                mapped_key = JAVA_TO_BEDROCK_BLOCK_PROPERTIES.get(key, key)
                bedrock_properties[mapped_key] = value

            return json.dumps(
                {
                    "success": True,
                    "bedrock_properties": bedrock_properties,
                    "warnings": [],
                }
            )
        except Exception as e:
            logger.error(f"Error mapping block properties: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def _determine_block_template(self, properties: Dict[str, Any]) -> str:
        """Determine the best block template based on properties."""
        material = properties.get("material", "stone").lower()

        if properties.get("light_level", 0) > 0:
            return "light_emitting"

        material_template_map = {
            "wood": "wooden",
            "stone": "stone",
            "dirt": "dirt",
            "sand": "sand",
            "glass": "glass",
            "metal": "metal",
            "water": "liquid",
            "lava": "liquid",
        }

        for mat, template in material_template_map.items():
            if mat in material:
                return template

        return "basic"

    def _build_block_json(
        self, template: Dict[str, Any], namespace: str, block_name: str, properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build block JSON from template."""
        block_json = {
            "format_version": "1.17.0",
            f"minecraft:{template.get('type', 'block')}": {
                "description": {
                    "identifier": f"{namespace}:{block_name}",
                },
                "components": {},
            },
        }

        for key, value in properties.items():
            mapped_key = JAVA_TO_BEDROCK_BLOCK_PROPERTIES.get(key, key)
            block_json[f"minecraft:{template.get('type', 'block')}"]["components"][mapped_key] = (
                value
            )

        return block_json

    def _validate_block_json(self, block_json: Dict[str, Any]) -> Dict[str, Any]:
        """Validate block JSON structure."""
        errors = []
        warnings = []

        if "format_version" not in block_json:
            errors.append("Missing format_version")

        has_block_component = any(k.startswith("minecraft:") for k in block_json.keys())
        if not has_block_component:
            errors.append("Missing block component")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
