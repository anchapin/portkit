"""modpack_conflict_detector - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.modpack_conflict_detector`` (the old single-file module).

The actual implementation has been grouped into the ``modpack/`` subpackage
under agents/modpack/conflict_detector.py.

Issue #1729 — Stub file for backward compatibility.

For new code, import from the subpackage:
    ``from agents.modpack import ModpackConflictDetector, ConflictDetectionResult``
    ``from agents.modpack.conflict_detector import ModLoader, Severity``
"""

from __future__ import annotations

from agents.modpack.conflict_detector import (
    Conflict,
    ConflictDetectionResult,
    ConflictType,
    LoadOrderEntry,
    ModLoader,
    ModMetadata,
    ModpackConflictDetector,
    NamespaceInfo,
    Severity,
    modpack_conflict_detector,
)

__all__ = [
    "Conflict",
    "ConflictDetectionResult",
    "ConflictType",
    "LoadOrderEntry",
    "ModLoader",
    "ModMetadata",
    "ModpackConflictDetector",
    "NamespaceInfo",
    "Severity",
    "modpack_conflict_detector",
]
