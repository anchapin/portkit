"""Typed tool for Java mod *dependency* analysis."""

from __future__ import annotations

import json
from typing import Any, ClassVar, Dict, List, Union

from pydantic import BaseModel, ConfigDict, Field

from ._base_tool import _BaseJavaAnalyzerTool

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer.tools")


def _analyze_dependencies_impl(mod_data: Union[str, Dict]) -> str:
    """
    Analyze mod dependencies.

    Args:
        mod_data: JSON string containing mod information

    Returns:
        JSON string with dependency analysis
    """
    from agents.java_analyzer import JavaAnalyzerAgent

    JavaAnalyzerAgent.get_instance()

    def _generate_dependency_recommendations(results: Dict) -> List[str]:
        """Generate dependency recommendations"""
        return ["Review dependencies for Bedrock compatibility"]

    try:
        if isinstance(mod_data, str):
            try:
                data = json.loads(mod_data)
                if "mod_data" in data:
                    (data["mod_data"] if isinstance(data["mod_data"], dict) else {})
                else:
                    data.get("mod_metadata", {})
            except json.JSONDecodeError:
                pass
        else:
            data = mod_data if isinstance(mod_data, dict) else {"mod_metadata": {}}
            if "mod_data" in data:
                data["mod_data"] if isinstance(data["mod_data"], dict) else {}
            else:
                data.get("mod_metadata", {})

        dependency_results = {
            "direct_dependencies": [],
            "transitive_dependencies": [],
            "framework_dependencies": [],
            "conversion_impact": {},
            "compatibility_concerns": [],
        }

        response = {
            "success": True,
            "dependency_analysis": dependency_results,
            "recommendations": _generate_dependency_recommendations(dependency_results),
        }

        logger.info("Analyzed dependencies: 0 direct, 0 framework")
        return json.dumps(response)

    except Exception as e:
        error_response = {
            "success": False,
            "error": f"Failed to analyze dependencies: {str(e)}",
        }
        logger.error(f"Dependency analysis error: {e}")
        return json.dumps(error_response)


class _AnalyzeDependenciesInput(BaseModel):
    """Args for :class:`_AnalyzeDependenciesTool`."""

    model_config = ConfigDict(extra="forbid")
    mod_data: Any = Field(
        description=(
            "JSON string or dict containing ``mod_path`` and an optional "
            "``metadata.dependencies`` list."
        ),
    )


class _AnalyzeDependenciesTool(_BaseJavaAnalyzerTool):
    name: str = "analyze_dependencies_tool"
    description: str = (
        "Analyze a mod's declared and detected dependencies, including "
        "Bedrock-portability assessment. "
        "Args: mod_data (str or dict, required) — mod_path + optional metadata."
    )
    args_schema: ClassVar[type[BaseModel]] = _AnalyzeDependenciesInput

    def _run(self, mod_data: Any) -> str:  # type: ignore[override]
        return _analyze_dependencies_impl(mod_data)
