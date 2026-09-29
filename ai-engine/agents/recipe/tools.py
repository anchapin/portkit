"""
Recipe Converter tool wrappers — Input models and typed BaseTool subclasses.

Extracted from __init__.py to resolve the monolith pattern (issue #1740).
"""

from typing import ClassVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field


class _BaseRecipeTool(BaseTool):
    """Common scaffolding for Recipe Converter typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


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


class _ConvertRecipeTool(_BaseRecipeTool):
    name: str = "convert_recipe_tool"
    description: str = (
        "Convert a single Java recipe to Bedrock JSON. "
        "Args: recipe_json (str, required) — JSON describing the Java recipe, "
        "optionally wrapped in {recipe_data, namespace, recipe_name}."
    )
    args_schema: ClassVar[type[BaseModel]] = _ConvertRecipeInput

    def _run(self, recipe_json: str) -> str:
        from agents.recipe import RecipeConverterAgent

        return RecipeConverterAgent._convert_recipe(recipe_json)


class _ConvertRecipesBatchTool(_BaseRecipeTool):
    name: str = "convert_recipes_batch_tool"
    description: str = (
        "Convert a batch of Java recipes to Bedrock JSON. "
        "Args: recipes_json (str, required) — JSON list of Java recipes."
    )
    args_schema: ClassVar[type[BaseModel]] = _ConvertRecipesBatchInput

    def _run(self, recipes_json: str) -> str:
        from agents.recipe import RecipeConverterAgent

        return RecipeConverterAgent._convert_recipes_batch(recipes_json)


class _MapItemIdTool(_BaseRecipeTool):
    name: str = "map_item_id_tool"
    description: str = (
        "Register custom Java→Bedrock item-ID mappings on the converter. "
        "Args: item_mapping_json (str, required) — JSON list or dict of mappings."
    )
    args_schema: ClassVar[type[BaseModel]] = _MapItemIdInput

    def _run(self, item_mapping_json: str) -> str:
        from agents.recipe import RecipeConverterAgent

        return RecipeConverterAgent._map_item_id(item_mapping_json)


class _ValidateRecipeTool(_BaseRecipeTool):
    name: str = "validate_recipe_tool"
    description: str = (
        "Validate a Bedrock recipe against expected structure. "
        "Args: recipe_json (str, required) — JSON of the Bedrock recipe."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateRecipeInput

    def _run(self, recipe_json: str) -> str:
        from agents.recipe import RecipeConverterAgent

        return RecipeConverterAgent._validate_recipe(recipe_json)


def _attach_tool_instances(agent_cls: type) -> None:
    """Attach module-level tool instances as class attributes on RecipeConverterAgent."""
    agent_cls.convert_recipe_tool = _ConvertRecipeTool()
    agent_cls.convert_recipes_batch_tool = _ConvertRecipesBatchTool()
    agent_cls.map_item_id_tool = _MapItemIdTool()
    agent_cls.validate_recipe_tool = _ValidateRecipeTool()
