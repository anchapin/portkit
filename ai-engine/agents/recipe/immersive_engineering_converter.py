"""
ImmersiveEngineering recipe converters.

Extracted from the original ``custom_types.py`` monolith (issue #1745).
Composed into ``CustomTypesConverter`` via mixin inheritance — see
``custom_types.py``.

Bedrock has no ImmersiveEngineering, so crusher / metalpress / arc_furnace /
refinery recipes are approximated as vanilla shapeless recipes. Machine-specific
metadata (energy cost, secondaries, mold) is preserved via the
``portkit:approximated_from`` annotation channel so the packager/validator
still see only valid Bedrock schema fields.
"""

from typing import Dict

from agents.recipe.converter_base import CustomConverterBase


class ImmersiveEngineeringConverterMixin(CustomConverterBase):
    """Converter mixin for ImmersiveEngineering recipe types (issue #1771)."""

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


__all__ = ["ImmersiveEngineeringConverterMixin"]
