"""gameplay_comparison_agent - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.gameplay_comparison_agent`` (the old single-file module).

The actual implementation has been grouped into the ``modpack/`` subpackage
under agents/modpack/gameplay_comparator.py.

Issue #1729 — Stub file for backward compatibility.

For new code, import from the subpackage:
    ``from agents.modpack import GameplayComparisonAgent``
    ``from agents.modpack.gameplay_comparator import Screenshot, GameTestScript``
"""

from __future__ import annotations

from agents.modpack.gameplay_comparator import (
    GameTestScript,
    GameplayComparisonAgent,
    GameplayComparisonResult,
    GameplayTestRunner,
    MinecraftLauncher,
    Screenshot,
    ScreenshotComparator,
)

__all__ = [
    "GameTestScript",
    "GameplayComparisonAgent",
    "GameplayComparisonResult",
    "GameplayTestRunner",
    "MinecraftLauncher",
    "Screenshot",
    "ScreenshotComparator",
]
