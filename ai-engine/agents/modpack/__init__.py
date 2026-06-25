"""
Modpack conversion cluster subpackage.

Groups the closely related modpack conversion agents (orchestrator, conflict
detector, gameplay comparator) that previously lived as flat top-level files in
``agents/``. Split into a subpackage per issue #1729.

Public API:
    - Orchestrator:        ``ModpackOrchestrator``, ``ModpackConversionCrew``,
                            ``ModpackInfo``, ``ModpackAnalysisResult``, ``PackFormat``,
                            ``modpack_orchestrator``
    - Conflict detector:   ``ModpackConflictDetector``, ``ConflictDetectionResult``,
                            ``Conflict``, ``ConflictType``, ``LoadOrderEntry``,
                            ``ModLoader``, ``ModMetadata``, ``NamespaceInfo``, ``Severity``,
                            ``modpack_conflict_detector``
    - Gameplay comparator:  ``GameplayComparisonAgent``, ``GameplayComparisonResult``,
                            ``GameTestScript``, ``GameplayTestRunner``, ``MinecraftLauncher``,
                            ``Screenshot``, ``ScreenshotComparator``

Backward compatibility: the original flat modules
(``agents.modpack_orchestrator``, ``agents.modpack_conflict_detector``,
``agents.gameplay_comparison_agent``) are kept as re-export stubs so existing
``from agents.<module> import X`` imports continue to work.
"""

from __future__ import annotations

from .conflict_detector import (
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
from .gameplay_comparator import (
    GameTestScript,
    GameplayComparisonAgent,
    GameplayComparisonResult,
    GameplayTestRunner,
    MinecraftLauncher,
    Screenshot,
    ScreenshotComparator,
)
from .orchestrator import (
    ModpackAnalysisResult,
    ModpackConversionCrew,
    ModpackInfo,
    ModpackOrchestrator,
    PackFormat,
    modpack_orchestrator,
)

__all__ = [
    # conflict_detector
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
    # gameplay_comparator
    "GameTestScript",
    "GameplayComparisonAgent",
    "GameplayComparisonResult",
    "GameplayTestRunner",
    "MinecraftLauncher",
    "Screenshot",
    "ScreenshotComparator",
    # orchestrator
    "ModpackAnalysisResult",
    "ModpackConversionCrew",
    "ModpackInfo",
    "ModpackOrchestrator",
    "PackFormat",
    "modpack_orchestrator",
]
