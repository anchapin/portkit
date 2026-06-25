"""modpack_orchestrator - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.modpack_orchestrator`` (the old single-file module).

The actual implementation has been grouped into the ``modpack/`` subpackage
under agents/modpack/orchestrator.py.

Issue #1729 — Stub file for backward compatibility.

For new code, import from the subpackage:
    ``from agents.modpack import ModpackOrchestrator, ModpackConversionCrew``
    ``from agents.modpack.orchestrator import PackFormat, ModpackInfo``
"""

from __future__ import annotations

from agents.modpack.orchestrator import (
    ModpackAnalysisResult,
    ModpackConversionCrew,
    ModpackInfo,
    ModpackOrchestrator,
    PackFormat,
    modpack_orchestrator,
)

__all__ = [
    "ModpackAnalysisResult",
    "ModpackConversionCrew",
    "ModpackInfo",
    "ModpackOrchestrator",
    "PackFormat",
    "modpack_orchestrator",
]
