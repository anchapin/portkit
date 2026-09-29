"""Layout Planner — Bedrock addon directory tree skeleton planning for the architect.

Seam: placeholder for layout/directory planning. The current
:class:`BedrockArchitectAgent` does not yet plan full addon directory trees;
this module is reserved for that work and re-exports the conversion-plan
construction helper used by the agent so future layout logic has a home.

Issue #1707 — Extracted from bedrock_architect_original.py for subpackage layout.
"""

from __future__ import annotations

from typing import Any, List

from models.smart_assumptions import ConversionPlanComponent


def collect_plan_components(components: List[Any]) -> List[Dict[str, Any]]:
    """Serialise a list of :class:`ConversionPlanComponent` into response dicts.

    The legacy ``_create_conversion_plan`` tool inlined a list comprehension that
    converted plan components to a JSON-friendly shape. That logic now lives
    here so any future layout planner can reuse the same serialiser.

    Args:
        components: Iterable of :class:`ConversionPlanComponent` instances (or
            any object with the same attribute names).

    Returns:
        List of dicts shaped for direct JSON encoding into the tool response.
    """
    return [
        {
            "original_feature_id": comp.original_feature_id,
            "original_feature_type": comp.original_feature_type,
            "assumption_type": comp.assumption_type,
            "bedrock_equivalent": comp.bedrock_equivalent,
            "impact_level": comp.impact_level,
            "user_explanation": comp.user_explanation,
            "technical_notes": comp.technical_notes,
        }
        for comp in components
        if isinstance(comp, ConversionPlanComponent)
    ]


__all__ = [
    "collect_plan_components",
]
