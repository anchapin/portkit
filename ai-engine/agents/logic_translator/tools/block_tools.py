"""Block and recipe tools — bedrock block generation, validation, property mapping, and recipe translation."""

from __future__ import annotations

import json
from typing import Any, ClassVar, Dict

from pydantic import BaseModel, ConfigDict, Field

from ._base import _BaseLogicTranslatorTool


class TranslateCraftingRecipeInput(BaseModel):
    """Args for :class:`TranslateCraftingRecipeTool`.

    The ``recipe`` field carries the raw Java crafting recipe dict
    (with ``type`` and the appropriate shaped/shapeless fields).
    """

    model_config = ConfigDict(extra="forbid")
    recipe: Dict[str, Any] = Field(description="Java crafting recipe dict.")


class GenerateBedrockBlockInput(BaseModel):
    """Args for :class:`GenerateBedrockBlockTool`."""

    model_config = ConfigDict(extra="forbid")
    java_block_analysis: Dict[str, Any] = Field(description="Java block analysis dict.")
    namespace: str = Field(default="modporter", min_length=1, description="Bedrock namespace.")
    use_rag: bool = Field(default=True, description="Augment with RAG context when available.")


class ValidateBlockJsonInput(BaseModel):
    """Args for :class:`ValidateBlockJsonTool`."""

    model_config = ConfigDict(extra="forbid")
    block_json: Dict[str, Any] = Field(description="Bedrock block JSON to validate against schema.")


class MapBlockPropertiesInput(BaseModel):
    """Args for :class:`MapBlockPropertiesTool`."""

    model_config = ConfigDict(extra="forbid")
    java_properties: Dict[str, Any] = Field(description="Java block properties dict.")


def _map_java_block_properties_to_bedrock(java_properties: Dict[str, Any]) -> Dict[str, Any]:
    """Map Java block properties to Bedrock equivalents."""
    from agents.logic_translator.block_state_mapper import (
        JAVA_TO_BEDROCK_BLOCK_PROPERTIES,
    )

    bedrock_properties: Dict[str, Any] = {}

    material = java_properties.get("material", "stone")
    if f"Material.{material.upper()}" in JAVA_TO_BEDROCK_BLOCK_PROPERTIES:
        mapping = JAVA_TO_BEDROCK_BLOCK_PROPERTIES[f"Material.{material.upper()}"]
        bedrock_properties.update(mapping)

    if "hardness" in java_properties:
        bedrock_properties["hardness"] = java_properties["hardness"]

    if "explosion_resistance" in java_properties:
        bedrock_properties["explosion_resistance"] = java_properties["explosion_resistance"]

    if "light_level" in java_properties and java_properties["light_level"] > 0:
        bedrock_properties["light_level"] = min(java_properties["light_level"], 15)

    sound_type = java_properties.get("sound_type", "stone")
    if f"SoundType.{sound_type.upper()}" in JAVA_TO_BEDROCK_BLOCK_PROPERTIES:
        bedrock_properties["sound_category"] = sound_type

    if java_properties.get("requires_tool", False):
        tool_type = java_properties.get("tool_type", "pickaxe")
        if f"ToolType.{tool_type.upper()}" in JAVA_TO_BEDROCK_BLOCK_PROPERTIES:
            bedrock_properties["requires_tool"] = tool_type

    return bedrock_properties


class TranslateCraftingRecipeTool(_BaseLogicTranslatorTool):
    """Translate a Java crafting recipe to Bedrock format."""

    name: str = "translate_crafting_recipe_tool"
    description: str = (
        "Translate a Java crafting recipe to Bedrock format. "
        "Args: recipe (dict containing 'type' and shape/ingredient fields)."
    )
    args_schema: ClassVar[type[BaseModel]] = TranslateCraftingRecipeInput

    async def _arun(  # type: ignore[override]
        self, recipe: Dict[str, Any]
    ) -> str:
        agent = self._get_agent()
        return agent.translate_crafting_recipe_json(json.dumps(recipe))

    def _run(  # type: ignore[override]
        self, recipe: Dict[str, Any]
    ) -> str:
        return self._run_async(self._arun(recipe=recipe))


class GenerateBedrockBlockTool(_BaseLogicTranslatorTool):
    """Generate Bedrock block JSON from a Java block analysis."""

    name: str = "generate_bedrock_block_tool"
    description: str = (
        "Generate Bedrock block JSON. Args: java_block_analysis (dict, required), "
        "namespace (str, default 'modporter'), use_rag (bool, default True)."
    )
    args_schema: ClassVar[type[BaseModel]] = GenerateBedrockBlockInput

    async def _arun(  # type: ignore[override]
        self,
        java_block_analysis: Dict[str, Any],
        namespace: str = "modporter",
        use_rag: bool = True,
    ) -> str:
        agent = self._get_agent()
        try:
            result = agent.generate_bedrock_block_json(
                java_block_analysis=java_block_analysis,
                namespace=namespace,
                use_rag=use_rag,
            )
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e), "block_json": None})

    def _run(  # type: ignore[override]
        self,
        java_block_analysis: Dict[str, Any],
        namespace: str = "modporter",
        use_rag: bool = True,
    ) -> str:
        return self._run_async(
            self._arun(
                java_block_analysis=java_block_analysis,
                namespace=namespace,
                use_rag=use_rag,
            )
        )


class ValidateBlockJsonTool(_BaseLogicTranslatorTool):
    """Validate a Bedrock block JSON document."""

    name: str = "validate_block_json_tool"
    description: str = "Validate a Bedrock block JSON document. Args: block_json (dict, required)."
    args_schema: ClassVar[type[BaseModel]] = ValidateBlockJsonInput

    async def _arun(  # type: ignore[override]
        self, block_json: Dict[str, Any]
    ) -> str:
        agent = self._get_agent()
        try:
            result = agent._validate_block_json(block_json)
            return json.dumps({"success": True, "validation": result})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def _run(  # type: ignore[override]
        self, block_json: Dict[str, Any]
    ) -> str:
        return self._run_async(self._arun(block_json=block_json))


class MapBlockPropertiesTool(_BaseLogicTranslatorTool):
    """Map Java block properties to Bedrock equivalents.

    Routes through the module-level :func:`_map_java_block_properties_to_bedrock`
    helper. The legacy wrapper called a non-existent agent method; this tool
    fixes that by calling the actually-implemented mapping logic.
    """

    name: str = "map_block_properties_tool"
    description: str = (
        "Map Java block properties to Bedrock. Args: java_properties (dict, required)."
    )
    args_schema: ClassVar[type[BaseModel]] = MapBlockPropertiesInput

    async def _arun(  # type: ignore[override]
        self, java_properties: Dict[str, Any]
    ) -> str:
        # Resolve the helper through the package namespace
        # (``agents.logic_translator.tools``) so callers can substitute it via
        # ``patch("agents.logic_translator.tools._map_java_block_properties_to_bedrock")``.
        # A direct module-global call would bypass that patch target. Lazy import
        # avoids the circular dependency with the package ``__init__``.
        from agents.logic_translator import tools as _tools_pkg

        try:
            result = _tools_pkg._map_java_block_properties_to_bedrock(java_properties)
            return json.dumps({"success": True, "bedrock_properties": result})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def _run(  # type: ignore[override]
        self, java_properties: Dict[str, Any]
    ) -> str:
        return self._run_async(self._arun(java_properties=java_properties))


# Module-level singleton instances
_translate_crafting_recipe_tool_instance = TranslateCraftingRecipeTool()
_generate_bedrock_block_tool_instance = GenerateBedrockBlockTool()
_validate_block_json_tool_instance = ValidateBlockJsonTool()
_map_block_properties_tool_instance = MapBlockPropertiesTool()
