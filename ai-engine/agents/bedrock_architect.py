"""bedrock_architect - Backward compatibility stub + subpackage coordinator.

This file provides:
1. Backward compatibility for code that imports BedrockArchitectAgent
   from the old single-file module.
2. Re-exports from the new bedrock_architect/ subpackage.

Issue #1622 — Stub file for backward compatibility + package coordinator.

New code should import from submodules directly:
- ``from agents.bedrock_architect.namespace_mapper import NamespaceMapper``
- ``from agents.bedrock_architect.manifest_generator import ManifestGenerator``
- ``from agents.bedrock_architect.layout_planner import LayoutPlanner``
- ``from agents.bedrock_architect.behavior_planner import BehaviorPlanner``
- ``from agents.bedrock_architect.dimension_porter import DimensionPorter``

Or use the package index:
- ``from agents.bedrock_architect import NamespaceMapper, ManifestGenerator``
"""

from __future__ import annotations

# Re-export BedrockArchitectAgent from original for backward compatibility
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

# Re-export subpackage for convenience imports
from agents.bedrock_architect import (
    NamespaceMapper,
    ManifestGenerator,
    LayoutPlanner,
    BehaviorPlanner,
    DimensionPorter,
    PackType,
    FeatureType,
    map_java_package,
    map_java_class,
    create_behavior_manifest,
    create_resource_manifest,
    create_addon,
    plan_block,
    plan_item,
    plan_entity,
    port_biome,
    port_dimension,
)

__all__ = [
    # Backward compatibility
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
    # Subpackage exports
    "NamespaceMapper",
    "ManifestGenerator",
    "LayoutPlanner",
    "BehaviorPlanner",
    "DimensionPorter",
    "PackType",
    "FeatureType",
    "map_java_package",
    "map_java_class",
    "create_behavior_manifest",
    "create_resource_manifest",
    "create_addon",
    "plan_block",
    "plan_item",
    "plan_entity",
    "port_biome",
    "port_dimension",
]