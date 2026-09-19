"""bedrock_architect subpackage — Bedrock conversion-planning architect.

This subpackage replaces the monolithic ``ai-engine/agents/bedrock_architect.py``
+ ``bedrock_architect_original.py`` pair. The architect agent is split into
five single-responsibility modules:

- ``namespace_mapper`` — Java feature / namespace helpers
- ``manifest_generator`` — Bedrock definition (block/item/recipe/entity) generation
- ``layout_planner`` — conversion-plan component serialisation
- ``behavior_planner`` — :class:`BedrockArchitectAgent` and its 10 typed LangChain tools
- ``dimension_porter`` — dimension/biome porting warning helpers

All public symbols remain importable from ``agents.bedrock_architect`` for
backward compatibility; new code is encouraged to import from the specific
submodule.

Issue #1707 — Coordinator ``__init__.py`` for the bedrock_architect subpackage.
"""

from __future__ import annotations

# Re-export the agent class and the typed tool wrappers / schemas
from .behavior_planner import (
    BedrockArchitectAgent,
    _AnalyzeJavaFeatureInput,
    _AnalyzeJavaFeatureTool,
    _ApplySmartAssumptionInput,
    _ApplySmartAssumptionTool,
    _BaseBedrockArchitectTool,
    _CreateConversionPlanInput,
    _CreateConversionPlanTool,
    _CreateLlmConversionPlanInput,
    _CreateLlmConversionPlanTool,
    _GenerateBlockDefinitionsInput,
    _GenerateBlockDefinitionsTool,
    _GenerateEntityDefinitionsInput,
    _GenerateEntityDefinitionsTool,
    _GenerateItemDefinitionsInput,
    _GenerateItemDefinitionsTool,
    _GenerateRecipeDefinitionsInput,
    _GenerateRecipeDefinitionsTool,
    _GetAssumptionConflictsInput,
    _GetAssumptionConflictsTool,
    _ValidateBedrockCompatibilityInput,
    _ValidateBedrockCompatibilityTool,
)

# Import submodules so ``from agents.bedrock_architect import namespace_mapper``
# (and the other four) continue to resolve.
from . import (
    behavior_planner,
    dimension_porter,
    layout_planner,
    manifest_generator,
    namespace_mapper,
)

# Re-export the helper-layer functions/classes for convenience.
from .dimension_porter import apply_dimension_warnings, empty_dimension_summary
from .layout_planner import collect_plan_components
from .manifest_generator import generate_placeholder_definition
from .namespace_mapper import build_feature_context, extract_namespace


__all__ = [
    # Backward-compat re-exports (preserved from the original stub)
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
    "_BaseBedrockArchitectTool",
    # Submodules
    "namespace_mapper",
    "manifest_generator",
    "layout_planner",
    "behavior_planner",
    "dimension_porter",
    # Helper-layer symbols
    "build_feature_context",
    "extract_namespace",
    "generate_placeholder_definition",
    "collect_plan_components",
    "apply_dimension_warnings",
    "empty_dimension_summary",
]
