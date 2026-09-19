"""Typed tool for LLM-augmented *complexity* analysis."""

from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ._base_tool import _BaseJavaAnalyzerTool

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer.tools")


def _analyze_complexity_with_llm_impl(analysis_data: str) -> str:
    """
    Use LLM to analyze Java mod complexity and identify Bedrock-incompatible patterns.

    This tool augments the regex-based feature detection with LLM-powered analysis
    to provide deeper insights into mod complexity and conversion feasibility.

    Args:
        analysis_data: JSON string containing:
            - source_code: Java source code to analyze
            - class_name: Name of the class being analyzed
            - feature_data: Existing feature data from regex analysis

    Returns:
        JSON string with LLM-powered complexity analysis
    """
    try:
        data = json.loads(analysis_data)
        source_code = data.get("source_code", "")
        class_name = data.get("class_name", "UnknownClass")
        feature_data = data.get("feature_data", {})

        from utils.llm_agent_tools import get_llm_agent_tools

        llm_tools = get_llm_agent_tools()
        llm_tools.initialize()

        result = llm_tools.analyze_java_mod_complexity(
            source_code=source_code, class_name=class_name, feature_data=feature_data
        )

        if result.get("success"):
            response = {
                "success": True,
                "llm_analysis": {
                    "complexity_level": result.get("complexity_level", "unknown"),
                    "bedrock_incompatible_patterns": result.get(
                        "bedrock_incompatible_patterns", []
                    ),
                    "conversion_strategies": result.get("conversion_strategies", []),
                    "summary": result.get("summary", ""),
                },
                "model_used": result.get("model_used", "unknown"),
            }
            logger.info(
                f"LLM complexity analysis completed for {class_name}: {result.get('complexity_level', 'unknown')}"
            )
        else:
            response = {
                "success": False,
                "error": result.get("error", "LLM analysis failed"),
                "llm_analysis": None,
            }
            logger.warning(
                f"LLM complexity analysis failed for {class_name}: {result.get('error')}"
            )

        return json.dumps(response)

    except Exception as e:
        error_response = {"success": False, "error": f"LLM analysis failed: {str(e)}"}
        logger.error(f"LLM complexity analysis error: {e}")
        return json.dumps(error_response)


# ─────────────────────────────────────────────────────────────────────────────
# Typed args_schema models — one per LangChain tool wrapper
#
# Phase 8 A6 (refs #1201). Each schema preserves the legacy single-arg
# ``mod_data: Union[str, Dict]`` (or ``analysis_data: str``) shape so chat
# models and existing call sites continue to invoke
# ``JavaAnalyzerAgent.<tool_name>.invoke({...})`` without changes. Five of
# the six tools accept either a JSON string or a dict, mirroring the
# legacy ``Union[str, Dict]`` typing on the static methods. The sixth
# (``analyze_complexity_with_llm_tool``) requires a JSON string only.
# ─────────────────────────────────────────────────────────────────────────────


class _AnalyzeComplexityWithLlmInput(BaseModel):
    """Args for :class:`_AnalyzeComplexityWithLlmTool`."""

    model_config = ConfigDict(extra="forbid")
    analysis_data: str = Field(
        min_length=1,
        description=(
            "JSON string with the prior analysis output to be reasoned about "
            "by the LLM-augmented complexity analyzer."
        ),
    )


class _AnalyzeComplexityWithLlmTool(_BaseJavaAnalyzerTool):
    name: str = "analyze_complexity_with_llm_tool"
    description: str = (
        "Use the LLM to reason about an analysis's complexity. "
        "Args: analysis_data (str, required) — JSON of prior analysis."
    )
    args_schema: ClassVar[type[BaseModel]] = _AnalyzeComplexityWithLlmInput

    def _run(self, analysis_data: str) -> str:  # type: ignore[override]
        return _analyze_complexity_with_llm_impl(analysis_data)
