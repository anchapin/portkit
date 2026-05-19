"""Bedrock Architect Agent for conversion planning and smart assumption application.

This module provides the BedrockArchitectAgent class which orchestrates conversion
strategies using smart assumptions as specified in PRD Feature 2.

Phase 8 A4a (refs #1201): the legacy ``@tool @staticmethod`` wrappers have
been replaced with typed :class:`langchain_core.tools.BaseTool` subclasses,
each declaring an explicit Pydantic ``args_schema``. The single-string
``<name>_data`` shape is preserved so chat models and existing call sites
continue to invoke ``BedrockArchitectAgent.<tool_name>.invoke({...})``
without changes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar, Dict, List

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from models.smart_assumptions import (
    AssumptionResult,
    FeatureContext,
    SmartAssumptionEngine,
)

logger = logging.getLogger(__name__)


class BedrockArchitectAgent:
    """Bedrock Architect Agent for optimal conversion strategies.

    Responsible for designing conversion strategies using smart assumptions
    as specified in PRD Feature 2. Implements singleton pattern for consistent
    state management across the conversion pipeline.
    """

    _instance: BedrockArchitectAgent | None = None

    def __init__(self) -> None:
        """Initialize the Bedrock Architect Agent."""
        self.smart_assumption_engine = SmartAssumptionEngine()

    @classmethod
    def get_instance(cls) -> BedrockArchitectAgent:
        """Get singleton instance of BedrockArchitectAgent.

        Returns:
            The singleton instance of BedrockArchitectAgent
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self) -> List[Any]:
        """Get tools available to this agent.

        Returns:
            List of available agent tools for conversion planning
        """
        return [
            self.analyze_java_feature_tool,
            self.apply_smart_assumption_tool,
            self.create_conversion_plan_tool,
            self.get_assumption_conflicts_tool,
            self.validate_bedrock_compatibility_tool,
            self.generate_block_definitions_tool,
            self.generate_item_definitions_tool,
            self.generate_recipe_definitions_tool,
            self.generate_entity_definitions_tool,
            self.create_llm_conversion_plan_tool,
        ]

    # ------------------------------------------------------------------
    # Static implementations (used by typed BaseTool subclasses below).
    #
    # These were previously decorated with ``@tool @staticmethod``; the
    # ``@tool`` decorator has been removed and each method renamed with a
    # leading underscore so it does not collide with the class-attribute
    # binding of the typed BaseTool instance below.
    # ------------------------------------------------------------------

    @staticmethod
    def _analyze_java_feature(feature_data: str) -> str:
        """Analyze a Java mod feature to determine applicable smart assumptions."""
        agent = BedrockArchitectAgent.get_instance()

        def _get_conversion_recommendation(analysis_result: AssumptionResult) -> str:
            """Get conversion recommendation based on analysis result"""
            if not analysis_result.applied_assumption:
                return "Feature appears to be directly convertible without assumptions"

            assumption = analysis_result.applied_assumption
            if assumption.impact.value == "high":
                return (
                    f"High-impact conversion required using {assumption.java_feature} "
                    "assumption. Significant functionality changes expected."
                )
            elif assumption.impact.value == "medium":
                return (
                    f"Moderate conversion using {assumption.java_feature} assumption. "
                    "Some functionality changes expected."
                )
            else:
                return (
                    f"Low-impact conversion using {assumption.java_feature} assumption. "
                    "Minimal functionality changes expected."
                )

        try:
            data = json.loads(feature_data)

            # Create FeatureContext from input data
            feature_context = FeatureContext(
                feature_id=data.get("feature_id", "unknown"),
                feature_type=data.get("feature_type", "unknown"),
                name=data.get("name"),
                original_data=data.get("original_data", {}),
            )

            # Analyze using Smart Assumptions Engine
            result = agent.smart_assumption_engine.analyze_feature(feature_context)

            response = {
                "feature_id": feature_context.feature_id,
                "feature_type": feature_context.feature_type,
                "has_applicable_assumption": result.applied_assumption is not None,
                "applicable_assumption": result.applied_assumption.java_feature
                if result.applied_assumption
                else None,
                "has_conflicts": len(result.conflicting_assumptions) > 0,
                "conflicting_assumptions": [a.java_feature for a in result.conflicting_assumptions],
                "conflict_resolution": result.conflict_resolution_reason,
                "recommendation": _get_conversion_recommendation(result),
            }

            logger.info(f"Analyzed feature {feature_context.feature_id}: {response}")
            return json.dumps(response)

        except Exception as e:
            error_response = {"error": f"Failed to analyze feature: {str(e)}"}
            logger.error(f"Feature analysis error: {e}")
            return json.dumps(error_response)

    @staticmethod
    def _apply_smart_assumption(assumption_data: str) -> str:
        """Apply smart assumption to a feature."""
        agent = BedrockArchitectAgent.get_instance()
        try:
            data = json.loads(assumption_data)

            # Reconstruct feature context and assumption result
            feature_context = FeatureContext(
                feature_id=data["feature_context"]["feature_id"],
                feature_type=data["feature_context"]["feature_type"],
                name=data["feature_context"].get("name"),
                original_data=data["feature_context"].get("original_data", {}),
            )

            # Re-analyze to get current assumption
            analysis_result = agent.smart_assumption_engine.analyze_feature(feature_context)

            if not analysis_result.applied_assumption:
                return json.dumps({"error": "No applicable assumption found for feature"})

            # Apply the assumption
            plan_component = agent.smart_assumption_engine.apply_assumption(analysis_result)

            if plan_component:
                response = {
                    "success": True,
                    "conversion_plan_component": {
                        "original_feature_id": plan_component.original_feature_id,
                        "original_feature_type": plan_component.original_feature_type,
                        "assumption_type": plan_component.assumption_type,
                        "bedrock_equivalent": plan_component.bedrock_equivalent,
                        "impact_level": plan_component.impact_level,
                        "user_explanation": plan_component.user_explanation,
                        "technical_notes": plan_component.technical_notes,
                    },
                }
                logger.info(
                    f"Applied assumption for {feature_context.feature_id}: "
                    f"{plan_component.assumption_type}"
                )
            else:
                response = {
                    "success": False,
                    "error": "Failed to generate conversion plan component",
                }

            return json.dumps(response)

        except Exception as e:
            error_response = {"success": False, "error": f"Failed to apply assumption: {str(e)}"}
            logger.error(f"Assumption application error: {e}")
            return json.dumps(error_response)

    @staticmethod
    def _create_conversion_plan(plan_data: Any) -> str:
        """Create a conversion plan for features."""
        agent = BedrockArchitectAgent.get_instance()
        try:
            # Ensure plan_data is a string before loading as JSON
            if not isinstance(plan_data, str):
                plan_data = json.dumps(plan_data)

            features = json.loads(plan_data)
            plan_components = []

            for feature_data in features:
                # Create feature context
                feature_context = FeatureContext(
                    feature_id=feature_data.get("feature_id", "unknown"),
                    feature_type=feature_data.get("feature_type", "unknown"),
                    name=feature_data.get("name"),
                    original_data=feature_data.get("original_data", {}),
                )

                # Analyze and apply assumptions
                analysis_result = agent.smart_assumption_engine.analyze_feature(feature_context)

                if analysis_result.applied_assumption:
                    plan_component = agent.smart_assumption_engine.apply_assumption(analysis_result)
                    if plan_component:
                        plan_components.append(plan_component)
                        logger.info(f"Added conversion plan for {feature_context.feature_id}")
                else:
                    logger.info(
                        f"No assumption applicable for {feature_context.feature_id}, skipping"
                    )

            # Generate assumption report
            assumption_report = agent.smart_assumption_engine.generate_assumption_report(
                plan_components
            )

            response = {
                "success": True,
                "conversion_plan_components": len(plan_components),
                "features_requiring_assumptions": len([c for c in plan_components]),
                "assumption_report": {
                    "assumptions_applied": [
                        {
                            "original_feature": item.original_feature,
                            "assumption_type": item.assumption_type,
                            "bedrock_equivalent": item.bedrock_equivalent,
                            "impact_level": item.impact_level,
                            "user_explanation": item.user_explanation,
                        }
                        for item in assumption_report.assumptions_applied
                    ]
                },
                "detailed_components": [
                    {
                        "original_feature_id": comp.original_feature_id,
                        "original_feature_type": comp.original_feature_type,
                        "assumption_type": comp.assumption_type,
                        "bedrock_equivalent": comp.bedrock_equivalent,
                        "impact_level": comp.impact_level,
                        "user_explanation": comp.user_explanation,
                        "technical_notes": comp.technical_notes,
                    }
                    for comp in plan_components
                ],
            }

            logger.info(f"Created conversion plan with {len(plan_components)} components")
            return json.dumps(response)

        except Exception as e:
            error_response = {
                "success": False,
                "error": f"Failed to create conversion plan: {str(e)}",
            }
            logger.error(f"Conversion plan creation error: {e}")
            return json.dumps(error_response)

    @staticmethod
    def _get_assumption_conflicts(conflict_data: str) -> str:
        """Get assumption conflicts for features."""
        agent = BedrockArchitectAgent.get_instance()
        try:
            data = json.loads(conflict_data)
            feature_type = data.get("feature_type")
            conflict_analysis = agent.smart_assumption_engine.get_conflict_analysis(feature_type)
            logger.info(f"Conflict analysis for {feature_type}: {conflict_analysis}")
            return json.dumps(conflict_analysis)

        except Exception as e:
            error_response = {"error": f"Failed to analyze conflicts: {str(e)}"}
            logger.error(f"Conflict analysis error: {e}")
            return json.dumps(error_response)

    @staticmethod
    def _validate_bedrock_compatibility(compatibility_data: str) -> str:
        """Validate Bedrock compatibility of features."""
        BedrockArchitectAgent.get_instance()

        def _validate_component_compatibility(component: Dict[str, Any]) -> Dict[str, Any]:
            """Validate individual component compatibility with Bedrock"""
            validation = {
                "component_id": component.get("original_feature_id", "unknown"),
                "is_compatible": True,
                "warnings": [],
                "recommendations": [],
            }

            assumption_type = component.get("assumption_type", "")
            impact_level = component.get("impact_level", "")

            # Check for high-impact conversions
            if impact_level == "high":
                validation["warnings"].append(
                    "High-impact conversion may result in significant functionality loss"
                )
                validation["recommendations"].append(
                    "Review user expectations and provide clear documentation about changes"
                )

            # Check for specific assumption types
            if "dimension" in assumption_type:
                validation["warnings"].append(
                    "Custom dimension converted to static structure - dynamic generation lost"
                )
                validation["recommendations"].append(
                    "Consider creating multiple structure variants for variety"
                )

            elif "machinery" in assumption_type:
                validation["warnings"].append(
                    "Complex machinery logic will be simplified or removed"
                )
                validation["recommendations"].append(
                    "Preserve visual aesthetics and consider alternative interaction methods"
                )

            elif "gui" in assumption_type:
                validation["warnings"].append("Interactive GUI elements will become static text")
                validation["recommendations"].append(
                    "Reorganize information for optimal book presentation"
                )

            return validation

        try:
            plan_data = json.loads(compatibility_data)
            components = plan_data.get("components", [])

            validation_results = {
                "is_compatible": True,
                "warnings": [],
                "recommendations": [],
                "component_validations": [],
            }

            for component in components:
                component_validation = _validate_component_compatibility(component)
                validation_results["component_validations"].append(component_validation)

                if not component_validation["is_compatible"]:
                    validation_results["is_compatible"] = False

                validation_results["warnings"].extend(component_validation.get("warnings", []))
                validation_results["recommendations"].extend(
                    component_validation.get("recommendations", [])
                )

            logger.info(f"Validated {len(components)} conversion components")
            return json.dumps(validation_results)

        except Exception as e:
            error_response = {"error": f"Failed to validate compatibility: {str(e)}"}
            logger.error(f"Compatibility validation error: {e}")
            return json.dumps(error_response)

    def _get_conversion_recommendation(self, analysis_result: AssumptionResult) -> str:
        """Get conversion recommendation based on analysis result"""
        if not analysis_result.applied_assumption:
            return "Feature appears to be directly convertible without assumptions"

        assumption = analysis_result.applied_assumption
        if assumption.impact.value == "high":
            return (
                f"High-impact conversion required using {assumption.java_feature} "
                "assumption. Significant functionality changes expected."
            )
        elif assumption.impact.value == "medium":
            return (
                f"Moderate conversion using {assumption.java_feature} assumption. "
                "Some functionality changes expected."
            )
        else:
            return (
                f"Low-impact conversion using {assumption.java_feature} assumption. "
                "Minimal functionality changes expected."
            )

    def _validate_component_compatibility(self, component: Dict[str, Any]) -> Dict[str, Any]:
        """Validate individual component compatibility with Bedrock"""
        validation = {
            "component_id": component.get("original_feature_id", "unknown"),
            "is_compatible": True,
            "warnings": [],
            "recommendations": [],
        }

        assumption_type = component.get("assumption_type", "")
        impact_level = component.get("impact_level", "")

        # Check for high-impact conversions
        if impact_level == "high":
            validation["warnings"].append(
                "High-impact conversion may result in significant functionality loss"
            )
            validation["recommendations"].append(
                "Review user expectations and provide clear documentation about changes"
            )

        # Check for specific assumption types
        if "dimension" in assumption_type:
            validation["warnings"].append(
                "Custom dimension converted to static structure - dynamic generation lost"
            )
            validation["recommendations"].append(
                "Consider creating multiple structure variants for variety"
            )

        elif "machinery" in assumption_type:
            validation["warnings"].append("Complex machinery logic will be simplified or removed")
            validation["recommendations"].append(
                "Preserve visual aesthetics and consider alternative interaction methods"
            )

        elif "gui" in assumption_type:
            validation["warnings"].append("Interactive GUI elements will become static text")
            validation["recommendations"].append(
                "Reorganize information for optimal book presentation"
            )

        return validation

    # --- Placeholder methods for Bedrock Definition Generation ---

    @staticmethod
    def _generate_block_definitions(block_data: str) -> str:
        """Generate Bedrock block definition files (placeholder)."""
        return BedrockArchitectAgent._generate_placeholder_definition(block_data, "block")

    @staticmethod
    def _generate_item_definitions(item_data: str) -> str:
        """Generate Bedrock item definition files (placeholder)."""
        return BedrockArchitectAgent._generate_placeholder_definition(item_data, "item")

    @staticmethod
    def _generate_recipe_definitions(recipe_data: str) -> str:
        """Generate Bedrock recipe JSON files (placeholder)."""
        return BedrockArchitectAgent._generate_placeholder_definition(recipe_data, "recipe")

    @staticmethod
    def _generate_entity_definitions(entity_data: str) -> str:
        """Generate Bedrock entity definition files (placeholder)."""
        return BedrockArchitectAgent._generate_placeholder_definition(entity_data, "entity")

    @staticmethod
    def _generate_placeholder_definition(component_data_str: str, component_type: str) -> str:
        """
        Generic placeholder for generating Bedrock component definitions.
        """
        try:
            component_data = json.loads(component_data_str)
            identifier = component_data.get(
                "identifier", f"custom:{component_data.get('id', f'{component_type}_placeholder')}"
            )
            name = component_data.get("name", f"Custom {component_type.capitalize()}")

            # Basic placeholder structure common to many Bedrock definitions
            placeholder_definition = {
                "format_version": "1.20.0",  # Using a recent common version
                f"minecraft:{component_type}": {
                    "description": {"identifier": identifier},
                    "components": {
                        "minecraft:display_name": {  # Common component for user-visible name
                            "value": name
                        },
                        # Specific components would vary greatly depending on component_type
                        # Example: A block might have "minecraft:material_instances"
                        # An item might have "minecraft:icon"
                        # An entity might have "minecraft:collision_box"
                    },
                    "metadata_generated": {  # Custom section for our tool's info
                        "source_java_id": component_data.get("id", "unknown_java_id"),
                        "conversion_tool": "ModPorterAI_BedrockArchitect",
                        "conversion_notes": (
                            f"This is an AI-generated placeholder {component_type} "
                            "definition. Review and refine."
                        ),
                    },
                },
            }

            # Add type-specific components if needed for a basic valid structure
            if component_type == "block":
                placeholder_definition[f"minecraft:{component_type}"]["components"][
                    "minecraft:loot"
                ] = f"loot_tables/blocks/{component_data.get('id', 'placeholder_block')}.json"
                placeholder_definition[f"minecraft:{component_type}"]["components"][
                    "minecraft:destructible_by_mining"
                ] = {"seconds_to_destroy": 1.0}
            elif component_type == "item":
                placeholder_definition[f"minecraft:{component_type}"]["components"][
                    "minecraft:icon"
                ] = {"texture": component_data.get("id", "placeholder_item_icon")}
                placeholder_definition[f"minecraft:{component_type}"]["components"][
                    "minecraft:max_stack_size"
                ] = 64
            elif component_type == "entity":
                placeholder_definition[f"minecraft:{component_type}"]["components"][
                    "minecraft:type_family"
                ] = {"family": [component_type, "mob"]}
                placeholder_definition[f"minecraft:{component_type}"]["components"][
                    "minecraft:health"
                ] = {"value": 20, "max": 20}

            logger.info(
                f"Generated placeholder {component_type} definition for identifier: {identifier}"
            )
            return json.dumps(
                {
                    "success": True,
                    "component_type": component_type,
                    "identifier": identifier,
                    "definition_json": placeholder_definition,
                    "message": (
                        f"Placeholder {component_type} definition generated successfully "
                        f"for {identifier}."
                    ),
                },
                indent=2,
            )

        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON input for placeholder {component_type} definition: "
                f"{str(e)} - Input: {component_data_str[:500]}...",
                exc_info=True,
            )  # Log part of the input
            return json.dumps(
                {
                    "success": False,
                    "error": f"Invalid JSON input for {component_type} definition: {str(e)}",
                },
                indent=2,
            )
        except Exception as e:
            logger.error(
                f"Error generating placeholder {component_type} definition: {e}", exc_info=True
            )
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        f"Failed to generate placeholder {component_type} definition: {str(e)}"
                    ),
                },
                indent=2,
            )

    @staticmethod
    def _create_llm_conversion_plan(plan_data: str) -> str:
        """
        Use LLM + RAG to generate conversion plans with Bedrock API context.

        This tool augments the smart assumption engine with LLM reasoning
        and retrieves relevant Bedrock documentation for feasibility assessment.

        Args:
            plan_data: JSON string containing:
                - feature_context: Feature data to convert
                - bedrock_docs_query: Query to retrieve relevant Bedrock API docs

        Returns:
            JSON string with LLM-generated conversion plan and feasibility assessment
        """
        try:
            data = json.loads(plan_data)
            feature_context = data.get("feature_context", {})
            bedrock_docs_query = data.get("bedrock_docs_query", "")

            from utils.llm_agent_tools import get_llm_agent_tools

            llm_tools = get_llm_agent_tools()
            llm_tools.initialize()

            result = llm_tools.generate_conversion_plan_with_rag(
                feature_context=feature_context, bedrock_docs_query=bedrock_docs_query
            )

            if result.get("success"):
                response = {
                    "success": True,
                    "llm_conversion_plan": {
                        "components": result.get("conversion_plan", {}).get("components", []),
                        "overall_feasibility": result.get("overall_feasibility", "unknown"),
                        "critical_issues": result.get("critical_issues", []),
                        "recommendations": result.get("recommendations", []),
                    },
                    "rag_context_used": result.get("rag_context_used", False),
                    "model_used": result.get("model_used", "unknown"),
                }
                logger.info(
                    "LLM conversion plan generated with feasibility: "
                    f"{result.get('overall_feasibility', 'unknown')}"
                )
            else:
                response = {
                    "success": False,
                    "error": result.get("error", "LLM conversion planning failed"),
                    "llm_conversion_plan": None,
                }
                logger.warning(f"LLM conversion planning failed: {result.get('error')}")

            return json.dumps(response)

        except Exception as e:
            error_response = {
                "success": False,
                "error": f"LLM conversion planning failed: {str(e)}",
            }
            logger.error(f"LLM conversion planning error: {e}")
            return json.dumps(error_response)


# ─────────────────────────────────────────────────────────────────────────────
# Typed args_schema models — one per LangChain tool wrapper
#
# Each schema preserves the legacy single-string ``<name>_data`` shape so chat
# models and existing call sites continue to invoke ``BedrockArchitectAgent.
# <tool_name>.invoke({"<name>_data": "..."})`` without changes. Pydantic
# ``extra="forbid"`` makes hallucinated extra fields fail loud at validation,
# and ``min_length=1`` rejects empty strings before they reach the underlying
# JSON-decoding logic.
# ─────────────────────────────────────────────────────────────────────────────


class _AnalyzeJavaFeatureInput(BaseModel):
    """Args for :class:`_AnalyzeJavaFeatureTool`."""

    model_config = ConfigDict(extra="forbid")
    feature_data: str = Field(
        min_length=1,
        description=(
            "JSON string with feature_id, feature_type, name, and original_data "
            "describing the Java mod feature to analyze."
        ),
    )


class _ApplySmartAssumptionInput(BaseModel):
    """Args for :class:`_ApplySmartAssumptionTool`."""

    model_config = ConfigDict(extra="forbid")
    assumption_data: str = Field(
        min_length=1,
        description=(
            "JSON string containing a feature_context object describing the "
            "Java mod feature to which a smart assumption should be applied."
        ),
    )


class _CreateConversionPlanInput(BaseModel):
    """Args for :class:`_CreateConversionPlanTool`.

    Accepts either a JSON string or a list of feature dicts to preserve the
    legacy ``plan_data: Any`` calling shape; non-string values are JSON-encoded
    by the underlying impl before being parsed.
    """

    model_config = ConfigDict(extra="forbid")
    plan_data: Any = Field(
        description=(
            "JSON string or list of feature dicts describing the Java mod "
            "features to assemble into a conversion plan."
        ),
    )


class _GetAssumptionConflictsInput(BaseModel):
    """Args for :class:`_GetAssumptionConflictsTool`."""

    model_config = ConfigDict(extra="forbid")
    conflict_data: str = Field(
        min_length=1,
        description=(
            "JSON string with a feature_type field identifying which feature "
            "type to inspect for assumption conflicts."
        ),
    )


class _ValidateBedrockCompatibilityInput(BaseModel):
    """Args for :class:`_ValidateBedrockCompatibilityTool`."""

    model_config = ConfigDict(extra="forbid")
    compatibility_data: str = Field(
        min_length=1,
        description=(
            "JSON string with a components list describing conversion plan "
            "components to validate against Bedrock compatibility rules."
        ),
    )


class _GenerateBlockDefinitionsInput(BaseModel):
    """Args for :class:`_GenerateBlockDefinitionsTool`."""

    model_config = ConfigDict(extra="forbid")
    block_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock block to generate.",
    )


class _GenerateItemDefinitionsInput(BaseModel):
    """Args for :class:`_GenerateItemDefinitionsTool`."""

    model_config = ConfigDict(extra="forbid")
    item_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock item to generate.",
    )


class _GenerateRecipeDefinitionsInput(BaseModel):
    """Args for :class:`_GenerateRecipeDefinitionsTool`."""

    model_config = ConfigDict(extra="forbid")
    recipe_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock recipe to generate.",
    )


class _GenerateEntityDefinitionsInput(BaseModel):
    """Args for :class:`_GenerateEntityDefinitionsTool`."""

    model_config = ConfigDict(extra="forbid")
    entity_data: str = Field(
        min_length=1,
        description="JSON string describing the Bedrock entity to generate.",
    )


class _CreateLlmConversionPlanInput(BaseModel):
    """Args for :class:`_CreateLlmConversionPlanTool`."""

    model_config = ConfigDict(extra="forbid")
    plan_data: str = Field(
        min_length=1,
        description=(
            "JSON string with feature_context and bedrock_docs_query fields used "
            "to drive the LLM-augmented conversion-plan generation."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Typed BaseTool subclasses — replace the previous @tool @staticmethod wrappers
# ─────────────────────────────────────────────────────────────────────────────


class _BaseBedrockArchitectTool(BaseTool):
    """Common scaffolding for Bedrock Architect typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class _AnalyzeJavaFeatureTool(_BaseBedrockArchitectTool):
    name: str = "analyze_java_feature_tool"
    description: str = (
        "Analyze a Java mod feature to determine applicable smart assumptions. "
        "Args: feature_data (str, required) — JSON with feature_id, feature_type, "
        "name, and original_data."
    )
    args_schema: ClassVar[type[BaseModel]] = _AnalyzeJavaFeatureInput

    def _run(self, feature_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._analyze_java_feature(feature_data)


class _ApplySmartAssumptionTool(_BaseBedrockArchitectTool):
    name: str = "apply_smart_assumption_tool"
    description: str = (
        "Apply a smart assumption to a Java mod feature, returning the resulting "
        "conversion-plan component. "
        "Args: assumption_data (str, required) — JSON containing a feature_context."
    )
    args_schema: ClassVar[type[BaseModel]] = _ApplySmartAssumptionInput

    def _run(self, assumption_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._apply_smart_assumption(assumption_data)


class _CreateConversionPlanTool(_BaseBedrockArchitectTool):
    name: str = "create_conversion_plan_tool"
    description: str = (
        "Create a conversion plan for a list of Java mod features. "
        "Args: plan_data (str or list, required) — JSON string or list of feature dicts."
    )
    args_schema: ClassVar[type[BaseModel]] = _CreateConversionPlanInput

    def _run(self, plan_data: Any) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._create_conversion_plan(plan_data)


class _GetAssumptionConflictsTool(_BaseBedrockArchitectTool):
    name: str = "get_assumption_conflicts_tool"
    description: str = (
        "Get the assumption-conflict analysis for a given feature type. "
        "Args: conflict_data (str, required) — JSON with a feature_type field."
    )
    args_schema: ClassVar[type[BaseModel]] = _GetAssumptionConflictsInput

    def _run(self, conflict_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._get_assumption_conflicts(conflict_data)


class _ValidateBedrockCompatibilityTool(_BaseBedrockArchitectTool):
    name: str = "validate_bedrock_compatibility_tool"
    description: str = (
        "Validate the Bedrock compatibility of a conversion plan, surfacing "
        "warnings and recommendations per component. "
        "Args: compatibility_data (str, required) — JSON with a components list."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateBedrockCompatibilityInput

    def _run(self, compatibility_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._validate_bedrock_compatibility(compatibility_data)


class _GenerateBlockDefinitionsTool(_BaseBedrockArchitectTool):
    name: str = "generate_block_definitions_tool"
    description: str = (
        "Generate a placeholder Bedrock block definition. "
        "Args: block_data (str, required) — JSON describing the block."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateBlockDefinitionsInput

    def _run(self, block_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._generate_block_definitions(block_data)


class _GenerateItemDefinitionsTool(_BaseBedrockArchitectTool):
    name: str = "generate_item_definitions_tool"
    description: str = (
        "Generate a placeholder Bedrock item definition. "
        "Args: item_data (str, required) — JSON describing the item."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateItemDefinitionsInput

    def _run(self, item_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._generate_item_definitions(item_data)


class _GenerateRecipeDefinitionsTool(_BaseBedrockArchitectTool):
    name: str = "generate_recipe_definitions_tool"
    description: str = (
        "Generate a placeholder Bedrock recipe definition. "
        "Args: recipe_data (str, required) — JSON describing the recipe."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateRecipeDefinitionsInput

    def _run(self, recipe_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._generate_recipe_definitions(recipe_data)


class _GenerateEntityDefinitionsTool(_BaseBedrockArchitectTool):
    name: str = "generate_entity_definitions_tool"
    description: str = (
        "Generate a placeholder Bedrock entity definition. "
        "Args: entity_data (str, required) — JSON describing the entity."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateEntityDefinitionsInput

    def _run(self, entity_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._generate_entity_definitions(entity_data)


class _CreateLlmConversionPlanTool(_BaseBedrockArchitectTool):
    name: str = "create_llm_conversion_plan_tool"
    description: str = (
        "Use the LLM + RAG pipeline to generate a Bedrock conversion plan with "
        "feasibility assessment. "
        "Args: plan_data (str, required) — JSON with feature_context and "
        "bedrock_docs_query."
    )
    args_schema: ClassVar[type[BaseModel]] = _CreateLlmConversionPlanInput

    def _run(self, plan_data: str) -> str:  # type: ignore[override]
        return BedrockArchitectAgent._create_llm_conversion_plan(plan_data)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level tool instances — preserved as class attributes on
# BedrockArchitectAgent so the existing access patterns
# (``BedrockArchitectAgent.<tool_name>`` and ``agent.<tool_name>``)
# both continue to work unchanged for call sites and tests.
# ─────────────────────────────────────────────────────────────────────────────


BedrockArchitectAgent.analyze_java_feature_tool = _AnalyzeJavaFeatureTool()
BedrockArchitectAgent.apply_smart_assumption_tool = _ApplySmartAssumptionTool()
BedrockArchitectAgent.create_conversion_plan_tool = _CreateConversionPlanTool()
BedrockArchitectAgent.get_assumption_conflicts_tool = _GetAssumptionConflictsTool()
BedrockArchitectAgent.validate_bedrock_compatibility_tool = _ValidateBedrockCompatibilityTool()
BedrockArchitectAgent.generate_block_definitions_tool = _GenerateBlockDefinitionsTool()
BedrockArchitectAgent.generate_item_definitions_tool = _GenerateItemDefinitionsTool()
BedrockArchitectAgent.generate_recipe_definitions_tool = _GenerateRecipeDefinitionsTool()
BedrockArchitectAgent.generate_entity_definitions_tool = _GenerateEntityDefinitionsTool()
BedrockArchitectAgent.create_llm_conversion_plan_tool = _CreateLlmConversionPlanTool()
