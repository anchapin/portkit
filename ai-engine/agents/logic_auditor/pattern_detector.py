"""pattern_detector - Java logic pattern classification.

Seam: Severity/SemanticType enums and the _classify_semantic_type logic that
decides which adversarial checks to run on a piece of Java code.
Lifted from lines 24-39 and 498-517 of the original logic_auditor_agent.py.
"""

from __future__ import annotations

import re
from enum import Enum


class Severity(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SemanticType(Enum):
    NUMERIC_FORMULA = "numeric_formula"
    PROBABILITY_RNG = "probability_rng"
    EVENT_HOOK = "event_hook"
    CONDITIONAL = "conditional"
    RESOURCE_ID = "resource_id"
    UNKNOWN = "unknown"


def classify_semantic_type(code: str) -> list[SemanticType]:
    """Classify which semantic types are present in the code."""
    types: list[SemanticType] = []

    if re.search(r"\*\s*\d+\.?\d*|random.*[<>]", code):
        if "random" in code.lower() or "probability" in code.lower():
            types.append(SemanticType.PROBABILITY_RNG)
        else:
            types.append(SemanticType.NUMERIC_FORMULA)

    if re.search(r"onBlock|onEntity|onPlayer|onInteract|onTick", code, re.IGNORECASE):
        types.append(SemanticType.EVENT_HOOK)

    if re.search(r"if\s*\([^)]*&&", code) or re.search(r"if\s*\([^)]*\|\|", code):
        types.append(SemanticType.CONDITIONAL)

    if re.search(r"[a-z_]+:[a-z_]+", code):
        types.append(SemanticType.RESOURCE_ID)

    return types if types else [SemanticType.UNKNOWN]
