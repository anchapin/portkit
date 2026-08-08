"""Scan-rule definitions extracted from pre_conversion/analyzer.py (Issue #1871).

This module centralizes static analysis rules, regex patterns, and AST-based
heuristics used to detect compatibility issues, unsupported APIs, and risky
code patterns during the pre-conversion scan phase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class RuleSeverity(Enum):
    """Severity levels for pre-conversion scan rules."""
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass(frozen=True)
class ScanRule:
    """Definition of a single static analysis rule."""
    id: str
    name: str
    severity: RuleSeverity
    pattern: re.Pattern[str] | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Core scan rules
# ---------------------------------------------------------------------------

FORGE_API_USAGE = ScanRule(
    id="PRE-001",
    name="Forge API Usage",
    severity=RuleSeverity.ERROR,
    pattern=re.compile(r"import\s+net\.minecraftforge", re.IGNORECASE),
    description="Direct usage of net.minecraftforge APIs will not translate to Bedrock.",
)

VANILLA_HACK_DETECTED = ScanRule(
    id="PRE-002",
    name="Vanilla Hack Detected",
    severity=RuleSeverity.WARNING,
    pattern=re.compile(r"(?<!\.)(obf|field_(?:public_|private_))"),
    description="Mod relies on internal Minecraft fields/methods subject to obfuscation.",
)

SCAN_RULES: list[ScanRule] = [
    FORGE_API_USAGE,
    VANILLA_HACK_DETECTED,
]
