"""Bedrock Builder agent package -- modular Bedrock add-on generator.

Public API (Issue #1742 split of the former single-file ``bedrock_builder.py``)::

    from agents.bedrock_builder import BedrockBuilderAgent

The :class:`BedrockBuilderAgent` implementation lives in
:mod:`agents.bedrock_builder.agent`; the typed LangChain tool wrappers and
their Pydantic args-schema models live in :mod:`agents.bedrock_builder.tools`.

This ``__init__`` re-exports the previous public surface (the agent class plus
every tool input model and tool class) so all existing call sites and tests
continue to work with no import-path changes.
"""

from agents.bedrock_builder.agent import BedrockBuilderAgent
from agents.bedrock_builder.tools import (
    _BaseBedrockBuilderTool,
    _BuildBedrockStructureInput,
    _BuildBedrockStructureTool,
    _ConvertAssetsInput,
    _ConvertAssetsTool,
    _GenerateBlockDefinitionsInput,
    _GenerateBlockDefinitionsTool,
    _PackageAddonInput,
    _PackageAddonTool,
)

__all__ = [
    "BedrockBuilderAgent",
    "_BaseBedrockBuilderTool",
    "_BuildBedrockStructureInput",
    "_BuildBedrockStructureTool",
    "_ConvertAssetsInput",
    "_ConvertAssetsTool",
    "_GenerateBlockDefinitionsInput",
    "_GenerateBlockDefinitionsTool",
    "_PackageAddonInput",
    "_PackageAddonTool",
]
