"""
Asset converter base — ToolFunction wrapper and utility functions.

Extracted from __init__.py to resolve the monolith pattern (issue #1740).
"""

from typing import Dict


class ToolFunction:
    """Wrapper to make standalone functions compatible with LangChain tool interface (.run())"""

    def __init__(self, func):
        self._func = func

    @property
    def func(self):
        """Access the wrapped function directly (for tests using .func())."""
        return self._func

    def run(self, **kwargs):
        """Call the wrapped function with flattened kwargs."""
        return self._invoke_with_kwargs(kwargs)

    def invoke(self, input, config=None, **kwargs):  # noqa: A002 - LangChain signature
        """LangChain BaseTool-compatible entry point."""
        if isinstance(input, dict):
            return self._invoke_with_kwargs(input)
        return self._func(input)

    async def ainvoke(self, input, config=None, **kwargs):  # noqa: A002
        """Async LangChain entry point — delegates to the sync `invoke`."""
        return self.invoke(input, config=config, **kwargs)

    def _invoke_with_kwargs(self, kwargs):
        if len(kwargs) == 1:
            key = list(kwargs.keys())[0]
            val = kwargs[key]
            if key in (
                "asset_data",
                "texture_data",
                "model_data",
                "audio_data",
                "jar_path",
                "atlas_path",
                "model_data",
                "audio_list",
                "jar_data",
                "path_data",
                "texture_data",
                "validation_data",
                "quality_data",
                "mcaddon_path",
                "test_data",
                "compatibility_data",
                "performance_data",
                "report_data",
                "recipe_json",
                "recipes_json",
                "item_mapping_json",
                "texture_path",
            ):
                return self._func(val)
        return self._func(**kwargs)


def _assess_conversion_complexity(analysis: Dict) -> str:
    """Assess the overall conversion complexity"""
    total_issues = (
        len(analysis.get("textures", {}).get("issues", []))
        + len(analysis.get("models", {}).get("issues", []))
        + len(analysis.get("audio", {}).get("issues", []))
    )
    total_assets = (
        analysis.get("textures", {}).get("count", 0)
        + analysis.get("models", {}).get("count", 0)
        + analysis.get("audio", {}).get("count", 0)
    )

    if total_assets == 0:
        return "none"

    issue_ratio = total_issues / total_assets if total_assets > 0 else 0

    if total_issues == 0 and total_assets >= 3:
        return "moderate"
    if issue_ratio < 0.3:
        return "simple"
    elif issue_ratio <= 0.65:
        return "moderate"
    else:
        return "complex"
