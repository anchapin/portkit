"""Namespace Mapper — Java feature and namespace handling for Bedrock architect.

Seam: extracted ``_analyze_java_feature`` FeatureContext construction and the
Java-to-Bedrock namespace resolution used by the analysis path.

Issue #1707 — Extracted from bedrock_architect_original.py for subpackage layout.
"""

from __future__ import annotations

from typing import Any, Dict

from models.smart_assumptions import FeatureContext


def build_feature_context(data: Dict[str, Any]) -> FeatureContext:
    """Construct a :class:`FeatureContext` from raw Java-feature JSON.

    The legacy ``_analyze_java_feature`` tool deserialised its ``feature_data``
    argument and then built a ``FeatureContext`` inline. That construction is
    reused by the smart-assumption application path, so it lives here for both
    call sites to share.

    Args:
        data: Dictionary with ``feature_id``, ``feature_type``, ``name`` (optional)
            and ``original_data`` (optional) keys.

    Returns:
        A :class:`FeatureContext` populated from ``data`` with safe defaults.
    """
    return FeatureContext(
        feature_id=data.get("feature_id", "unknown"),
        feature_type=data.get("feature_type", "unknown"),
        name=data.get("name"),
        original_data=data.get("original_data", {}),
    )


def extract_namespace(feature_type: str | None) -> str | None:
    """Extract a Bedrock namespace hint from a feature_type string.

    The smart-assumption engine reasons about feature types like ``block``,
    ``item`` or ``machinery``; this helper keeps the raw string handling in one
    place. The current implementation is a no-op pass-through — the seam is
    preserved for future namespace resolution (e.g., mod-id prefixing).

    Args:
        feature_type: Feature type string from a feature payload.

    Returns:
        The unchanged ``feature_type`` (reserved for future expansion).
    """
    return feature_type


__all__ = [
    "build_feature_context",
    "extract_namespace",
]
