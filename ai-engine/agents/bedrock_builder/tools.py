"""
Typed BaseTool wrappers and args-schema models for the Bedrock Builder agent.

Phase 8 A4a (refs #1201). Each schema preserves the legacy single-string
``<name>_data`` shape so chat models and existing call sites continue to
invoke ``BedrockBuilderAgent.<tool_name>.invoke({"<name>_data": "..."})``
without changes. ``extra="forbid"`` makes hallucinated extra fields fail
loud at validation, and ``min_length=1`` rejects empty strings.

Extracted from the former single-file ``agents/bedrock_builder.py`` module as
part of the ``bedrock_builder/`` subpackage split (Issue #1742). The tool
instances are bound onto :class:`BedrockBuilderAgent` as class attributes at
import time so the existing access patterns
(``BedrockBuilderAgent.<tool_name>`` and ``agent.<tool_name>``) continue to
work unchanged for call sites and tests.
"""

from typing import ClassVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from agents.bedrock_builder.agent import BedrockBuilderAgent


# ---------------------------------------------------------------------------
# Typed args_schema models -- one per LangChain tool wrapper
# ---------------------------------------------------------------------------


class _BuildBedrockStructureInput(BaseModel):
    """Args for :class:`_BuildBedrockStructureTool`."""

    model_config = ConfigDict(extra="forbid")
    structure_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock addon directory structure to build.",
    )


class _GenerateBlockDefinitionsInput(BaseModel):
    """Args for :class:`_GenerateBlockDefinitionsTool`."""

    model_config = ConfigDict(extra="forbid")
    block_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock block definitions to generate.",
    )


class _ConvertAssetsInput(BaseModel):
    """Args for :class:`_ConvertAssetsTool`."""

    model_config = ConfigDict(extra="forbid")
    asset_data: str = Field(
        min_length=1,
        description="JSON string describing the assets (textures, models, sounds) to convert.",
    )


class _PackageAddonInput(BaseModel):
    """Args for :class:`_PackageAddonTool`."""

    model_config = ConfigDict(extra="forbid")
    package_data: str = Field(
        min_length=1,
        description="JSON string describing the addon to package into a .mcaddon archive.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Typed BaseTool subclasses — replace the previous @tool @staticmethod wrappers
# ─────────────────────────────────────────────────────────────────────────────


class _BaseBedrockBuilderTool(BaseTool):
    """Common scaffolding for Bedrock Builder typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class _BuildBedrockStructureTool(_BaseBedrockBuilderTool):
    name: str = "build_bedrock_structure_tool"
    description: str = (
        "Build basic Bedrock addon directory structure. "
        "Args: structure_data (str, required) — JSON describing the structure."
    )
    args_schema: ClassVar[type[BaseModel]] = _BuildBedrockStructureInput

    def _run(self, structure_data: str) -> str:  # type: ignore[override]
        return BedrockBuilderAgent._build_bedrock_structure(structure_data)


class _GenerateBlockDefinitionsTool(_BaseBedrockBuilderTool):
    name: str = "generate_block_definitions_tool"
    description: str = (
        "Generate Bedrock block definition files. "
        "Args: block_data (str, required) — JSON describing the blocks."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateBlockDefinitionsInput

    def _run(self, block_data: str) -> str:  # type: ignore[override]
        return BedrockBuilderAgent._generate_block_definitions(block_data)


class _ConvertAssetsTool(_BaseBedrockBuilderTool):
    name: str = "convert_assets_tool"
    description: str = (
        "Convert mod assets to Bedrock format. "
        "Args: asset_data (str, required) — JSON describing the assets."
    )
    args_schema: ClassVar[type[BaseModel]] = _ConvertAssetsInput

    def _run(self, asset_data: str) -> str:  # type: ignore[override]
        return BedrockBuilderAgent._convert_assets(asset_data)


class _PackageAddonTool(_BaseBedrockBuilderTool):
    name: str = "package_addon_tool"
    description: str = (
        "Package an addon into a .mcaddon archive. "
        "Args: package_data (str, required) — JSON describing the package."
    )
    args_schema: ClassVar[type[BaseModel]] = _PackageAddonInput

    def _run(self, package_data: str) -> str:  # type: ignore[override]
        return BedrockBuilderAgent._package_addon(package_data)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level tool instances — preserved as class attributes on
# BedrockBuilderAgent so the existing access patterns
# (BedrockBuilderAgent.<tool_name> and agent.<tool_name>) both
# continue to work unchanged for call sites and tests.
# ─────────────────────────────────────────────────────────────────────────────


BedrockBuilderAgent.build_bedrock_structure_tool = _BuildBedrockStructureTool()
BedrockBuilderAgent.generate_block_definitions_tool = _GenerateBlockDefinitionsTool()
BedrockBuilderAgent.convert_assets_tool = _ConvertAssetsTool()
BedrockBuilderAgent.package_addon_tool = _PackageAddonTool()
