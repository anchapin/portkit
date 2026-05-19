"""bedrock_architect - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.bedrock_architect`` (the old single-file module).

The actual implementation has been split into the ``bedrock_architect/``
subpackage under mmsd/tinker/bedrock_architect/.

Issue #1622 — Stub file for backward compatibility.

For new code, import from submodules directly:
- ``from mmsd.tinker.bedrock_architect.namespace_mapper import ...``
- ``from mmsd.tinker.bedrock_architect.manifest_generator import ...``
- ``from mmsd.tinker.bedrock_architect.layout_planner import ...``
- ``from mmsd.tinker.bedrock_architect.behavior_planner import ...``
- ``from mmsd.tinker.bedrock_architect.dimension_porter import ...``

For backward compatibility, import BedrockArchitectAgent from:
``from agents.bedrock_architect_original import BedrockArchitectAgent``
"""

from __future__ import annotations

# Re-export everything from the original module for backward compatibility
from agents.bedrock_architect_original import (
    BedrockArchitectAgent,
    _AnalyzeJavaFeatureInput,
    _AnalyzeJavaFeatureTool,
    _ApplySmartAssumptionInput,
    _ApplySmartAssumptionTool,
    _CreateConversionPlanInput,
    _CreateConversionPlanTool,
    _GetAssumptionConflictsInput,
    _GetAssumptionConflictsTool,
    _ValidateBedrockCompatibilityInput,
    _ValidateBedrockCompatibilityTool,
    _GenerateBlockDefinitionsInput,
    _GenerateBlockDefinitionsTool,
    _GenerateItemDefinitionsInput,
    _GenerateItemDefinitionsTool,
    _GenerateRecipeDefinitionsInput,
    _GenerateRecipeDefinitionsTool,
    _GenerateEntityDefinitionsInput,
    _GenerateEntityDefinitionsTool,
    _CreateLlmConversionPlanInput,
    _CreateLlmConversionPlanTool,
)

__all__ = [
    "BedrockArchitectAgent",
    "_AnalyzeJavaFeatureInput",
    "_AnalyzeJavaFeatureTool",
    "_ApplySmartAssumptionInput",
    "_ApplySmartAssumptionTool",
    "_CreateConversionPlanInput",
    "_CreateConversionPlanTool",
    "_GetAssumptionConflictsInput",
    "_GetAssumptionConflictsTool",
    "_ValidateBedrockCompatibilityInput",
    "_ValidateBedrockCompatibilityTool",
    "_GenerateBlockDefinitionsInput",
    "_GenerateBlockDefinitionsTool",
    "_GenerateItemDefinitionsInput",
    "_GenerateItemDefinitionsTool",
    "_GenerateRecipeDefinitionsInput",
    "_GenerateRecipeDefinitionsTool",
    "_GenerateEntityDefinitionsInput",
    "_GenerateEntityDefinitionsTool",
    "_CreateLlmConversionPlanInput",
    "_CreateLlmConversionPlanTool",
]