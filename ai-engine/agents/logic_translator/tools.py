"""LangChain tool wrappers for the Logic Translator Agent.

Backwards compatibility re-export shim.

All classes and ``LogicTranslatorTools`` have been moved to the ``tools`` subpackage:
- tools._base: _BaseLogicTranslatorTool
- tools.rag_tools: GetRagContextTool, SetRagContextTool
- tools.translation_tools: TranslateJavaMethodTool, ConvertJavaClassTool
- tools.api_mapping_tools: MapJavaApisTool, GenerateEventHandlersTool
- tools.block_tools: TranslateCraftingRecipeTool, GenerateBedrockBlockTool,
                     ValidateBlockJsonTool, MapBlockPropertiesTool
- tools.validation_tools: ValidateJavascriptSyntaxTool

Import from ``agents.logic_translator.tools`` (the subpackage ``__init__``)
or from the specific submodule for type annotations.

This shim exists solely to preserve ``from agents.logic_translator.tools import X``
imports without a deprecation cycle.
"""

from agents.logic_translator.tools import (
    ConvertJavaClassInput,
    ConvertJavaClassTool,
    GenerateBedrockBlockInput,
    GenerateBedrockBlockTool,
    GenerateEventHandlersInput,
    GenerateEventHandlersTool,
    GetRagContextInput,
    GetRagContextTool,
    LogicTranslatorTools,
    MapBlockPropertiesInput,
    MapBlockPropertiesTool,
    MapJavaApisInput,
    MapJavaApisTool,
    SetRagContextInput,
    SetRagContextTool,
    TranslateCraftingRecipeInput,
    TranslateCraftingRecipeTool,
    TranslateJavaMethodInput,
    TranslateJavaMethodTool,
    ValidateBlockJsonInput,
    ValidateBlockJsonTool,
    ValidateJavascriptSyntaxInput,
    ValidateJavascriptSyntaxTool,
    _map_java_block_properties_to_bedrock,
)

__all__ = [
    "LogicTranslatorTools",
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
    "_map_java_block_properties_to_bedrock",
]
