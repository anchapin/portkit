"""LangChain tool wrappers for the Logic Translator Agent.

This package exposes typed ``BaseTool`` subclasses backed by the
``LogicTranslatorAgent`` singleton. Each tool declares a Pydantic
``args_schema`` so chat models with native tool-calling can invoke it with
structured arguments instead of a JSON-encoded ``<name>_data: str`` blob.

Backwards compatibility:

* ``LogicTranslatorTools`` is preserved as a facade. Each typed tool is
  exposed as a class attribute on ``LogicTranslatorTools`` (``LogicTranslatorTools.<name>``)
  with the legacy tool name, and the ``@property`` accessors on
  ``LogicTranslatorAgent`` continue to return the same instance.
* The agent's ``__init__`` is heavy (model loading); each tool defers
  resolving the singleton until invocation, never at module import.

Re-exported from tools/ submodules:
- tools._base: _BaseLogicTranslatorTool
- tools.rag_tools: GetRagContextTool, SetRagContextTool
- tools.translation_tools: TranslateJavaMethodTool, ConvertJavaClassTool
- tools.api_mapping_tools: MapJavaApisTool, GenerateEventHandlersTool
- tools.block_tools: TranslateCraftingRecipeTool, GenerateBedrockBlockTool,
                     ValidateBlockJsonTool, MapBlockPropertiesTool
- tools.validation_tools: ValidateJavascriptSyntaxTool

This refactor is Phase 9 of issue #1201, mirroring the pattern proven
in :mod:`tools.search_tool` (PR #1446).
"""

from __future__ import annotations

from agents.logic_translator.tools._base import _BaseLogicTranslatorTool
from agents.logic_translator.tools.api_mapping_tools import (
    GenerateEventHandlersInput,
    GenerateEventHandlersTool,
    MapJavaApisInput,
    MapJavaApisTool,
    _generate_event_handlers_tool_instance,
    _map_java_apis_tool_instance,
)
from agents.logic_translator.tools.block_tools import (
    GenerateBedrockBlockInput,
    GenerateBedrockBlockTool,
    MapBlockPropertiesInput,
    MapBlockPropertiesTool,
    TranslateCraftingRecipeInput,
    TranslateCraftingRecipeTool,
    ValidateBlockJsonInput,
    ValidateBlockJsonTool,
    _generate_bedrock_block_tool_instance,
    _map_block_properties_tool_instance,
    _translate_crafting_recipe_tool_instance,
    _validate_block_json_tool_instance,
    _map_java_block_properties_to_bedrock,
)
from agents.logic_translator.tools.rag_tools import (
    GetRagContextInput,
    GetRagContextTool,
    SetRagContextInput,
    SetRagContextTool,
    _get_rag_context_tool_instance,
    _set_rag_context_tool_instance,
)
from agents.logic_translator.tools.translation_tools import (
    ConvertJavaClassInput,
    ConvertJavaClassTool,
    TranslateJavaMethodInput,
    TranslateJavaMethodTool,
    _convert_java_class_tool_instance,
    _translate_java_method_tool_instance,
)
from agents.logic_translator.tools.validation_tools import (
    ValidateJavascriptSyntaxInput,
    ValidateJavascriptSyntaxTool,
    _validate_javascript_syntax_tool_instance,
)

# ---------------------------------------------------------------------------
# Module-level singleton instances (bound to LogicTranslatorTools class attrs)
# ---------------------------------------------------------------------------

_get_rag_context_tool = _get_rag_context_tool_instance
_set_rag_context_tool = _set_rag_context_tool_instance
_translate_java_method_tool = _translate_java_method_tool_instance
_convert_java_class_tool = _convert_java_class_tool_instance
_map_java_apis_tool = _map_java_apis_tool_instance
_generate_event_handlers_tool = _generate_event_handlers_tool_instance
_validate_javascript_syntax_tool = _validate_javascript_syntax_tool_instance
_translate_crafting_recipe_tool = _translate_crafting_recipe_tool_instance
_generate_bedrock_block_tool = _generate_bedrock_block_tool_instance
_validate_block_json_tool = _validate_block_json_tool_instance
_map_block_properties_tool = _map_block_properties_tool_instance


class LogicTranslatorTools:
    """Collection of LangChain tools for Java to Bedrock logic translation."""

    get_rag_context_tool = _get_rag_context_tool
    set_rag_context_tool = _set_rag_context_tool
    translate_java_method_tool = _translate_java_method_tool
    convert_java_class_tool = _convert_java_class_tool
    map_java_apis_tool = _map_java_apis_tool
    generate_event_handlers_tool = _generate_event_handlers_tool
    validate_javascript_syntax_tool = _validate_javascript_syntax_tool
    translate_crafting_recipe_tool = _translate_crafting_recipe_tool
    generate_bedrock_block_tool = _generate_bedrock_block_tool
    validate_block_json_tool = _validate_block_json_tool
    map_block_properties_tool = _map_block_properties_tool


__all__ = [
    "_BaseLogicTranslatorTool",
    "GetRagContextInput",
    "GetRagContextTool",
    "SetRagContextInput",
    "SetRagContextTool",
    "TranslateJavaMethodInput",
    "TranslateJavaMethodTool",
    "ConvertJavaClassInput",
    "ConvertJavaClassTool",
    "MapJavaApisInput",
    "MapJavaApisTool",
    "GenerateEventHandlersInput",
    "GenerateEventHandlersTool",
    "ValidateJavascriptSyntaxInput",
    "ValidateJavascriptSyntaxTool",
    "TranslateCraftingRecipeInput",
    "TranslateCraftingRecipeTool",
    "GenerateBedrockBlockInput",
    "GenerateBedrockBlockTool",
    "ValidateBlockJsonInput",
    "ValidateBlockJsonTool",
    "MapBlockPropertiesInput",
    "MapBlockPropertiesTool",
    "LogicTranslatorTools",
    "_map_java_block_properties_to_bedrock",
]
