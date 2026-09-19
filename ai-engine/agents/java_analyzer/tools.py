"""
Java Analyzer tools — backwards-compatibility shim.

The tool implementations now live in focused submodules:
  * structure_tools.py   — mod structure & metadata tools
  * feature_tools.py     — feature & asset identification tools
  * dependency_tools.py  — dependency analysis tool
  * complexity_tools.py  — LLM complexity analysis tool

This module re-exports every public name (``JavaAnalyzerTools`` facade,
the typed ``_BaseJavaAnalyzerTool`` subclasses and their Pydantic input
schemas) so existing imports such as
``from agents.java_analyzer.tools import JavaAnalyzerTools`` keep working.
"""

from __future__ import annotations

from typing import Dict, Union

from ._base_tool import _BaseJavaAnalyzerTool  # noqa: F401
from .structure_tools import _AnalyzeModStructureInput  # noqa: F401
from .structure_tools import _ExtractModMetadataInput  # noqa: F401
from .feature_tools import _IdentifyFeaturesInput  # noqa: F401
from .feature_tools import _ExtractAssetsInput  # noqa: F401
from .dependency_tools import _AnalyzeDependenciesInput  # noqa: F401
from .complexity_tools import _AnalyzeComplexityWithLlmInput  # noqa: F401
from .structure_tools import _AnalyzeModStructureTool  # noqa: F401
from .structure_tools import _ExtractModMetadataTool  # noqa: F401
from .feature_tools import _IdentifyFeaturesTool  # noqa: F401
from .feature_tools import _ExtractAssetsTool  # noqa: F401
from .dependency_tools import _AnalyzeDependenciesTool  # noqa: F401
from .complexity_tools import _AnalyzeComplexityWithLlmTool  # noqa: F401
from .structure_tools import _analyze_mod_structure_impl  # noqa: F401
from .structure_tools import _extract_mod_metadata_impl  # noqa: F401
from .feature_tools import _identify_features_impl  # noqa: F401
from .feature_tools import _extract_assets_impl  # noqa: F401
from .dependency_tools import _analyze_dependencies_impl  # noqa: F401
from .complexity_tools import _analyze_complexity_with_llm_impl  # noqa: F401


class JavaAnalyzerTools:
    """Facade re-exposing the legacy static tool entry points.

    Each method delegates to its focused implementation in the
    corresponding ``*_tools`` submodule; the typed ``BaseTool``
    instances are re-bound below as class attributes.
    """

    def __init__(self, agent_instance=None):
        self.agent_instance = agent_instance

    @staticmethod
    def _analyze_mod_structure(mod_data: Union[str, Dict]) -> str:
        """Delegate to the focused ``_analyze_mod_structure_impl``."""
        return _analyze_mod_structure_impl(mod_data)

    @staticmethod
    def _extract_mod_metadata(mod_data: Union[str, Dict]) -> str:
        """Delegate to the focused ``_extract_mod_metadata_impl``."""
        return _extract_mod_metadata_impl(mod_data)

    @staticmethod
    def _identify_features(mod_data: Union[str, Dict]) -> str:
        """Delegate to the focused ``_identify_features_impl``."""
        return _identify_features_impl(mod_data)

    @staticmethod
    def _analyze_dependencies(mod_data: Union[str, Dict]) -> str:
        """Delegate to the focused ``_analyze_dependencies_impl``."""
        return _analyze_dependencies_impl(mod_data)

    @staticmethod
    def _extract_assets(mod_data: Union[str, Dict]) -> str:
        """Delegate to the focused ``_extract_assets_impl``."""
        return _extract_assets_impl(mod_data)

    @staticmethod
    def _analyze_complexity_with_llm(analysis_data: str) -> str:
        """Delegate to the focused ``_analyze_complexity_with_llm_impl``."""
        return _analyze_complexity_with_llm_impl(analysis_data)


# Typed BaseTool instances bound as class attributes so that
# ``JavaAnalyzerAgent``'s class-body aliases resolve to the same
# singleton objects (identity preserved for tests & tool-calling).
JavaAnalyzerTools.analyze_mod_structure_tool = _AnalyzeModStructureTool()
JavaAnalyzerTools.extract_mod_metadata_tool = _ExtractModMetadataTool()
JavaAnalyzerTools.identify_features_tool = _IdentifyFeaturesTool()
JavaAnalyzerTools.analyze_dependencies_tool = _AnalyzeDependenciesTool()
JavaAnalyzerTools.extract_assets_tool = _ExtractAssetsTool()
JavaAnalyzerTools.analyze_complexity_with_llm_tool = _AnalyzeComplexityWithLlmTool()
