"""Dimension Porter — Dimension and biome porting helpers for the architect.

Seam: reserved for future dimension/biome porting logic. The current
:class:`BedrockArchitectAgent` does not yet port dimensions; this module
houses the helper that surfaces ``dimension`` assumption warnings, extracted
from the legacy ``_validate_bedrock_compatibility`` inlined helper so future
dimension-aware code has a home.

Issue #1707 — Extracted from bedrock_architect_original.py for subpackage layout.
"""

from __future__ import annotations

from typing import Any, Dict, List


def apply_dimension_warnings(validation: Dict[str, Any], component: Dict[str, Any]) -> None:
    """Append dimension-porting warnings/recommendations to ``validation`` in place.

    The legacy ``_validate_component_compatibility`` helper inlined three
    assumption-type branches (``dimension``, ``machinery``, ``gui``). The
    dimension branch is exposed here; the other two remain in the
    compatibility validator inside the agent class.

    Args:
        validation: Mutable validation dict that will receive ``warnings`` and
            ``recommendations`` entries.
        component: Conversion-plan component dict being validated; only the
            ``assumption_type`` key is consulted.
    """
    if "dimension" not in component.get("assumption_type", ""):
        return
    validation["warnings"].append(
        "Custom dimension converted to static structure - dynamic generation lost"
    )
    validation["recommendations"].append(
        "Consider creating multiple structure variants for variety"
    )


def empty_dimension_summary() -> Dict[str, List[Any]]:
    """Return an empty dimension-porting summary for placeholder callers.

    Returns:
        Dict with empty ``warnings`` and ``recommendations`` lists — used by
        future dimension porting to maintain a consistent response shape.
    """
    return {"warnings": [], "recommendations": []}


__all__ = [
    "apply_dimension_warnings",
    "empty_dimension_summary",
]
