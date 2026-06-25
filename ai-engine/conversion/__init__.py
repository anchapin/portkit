"""
Five-phase legacy translation pipeline for Java → Bedrock conversion.

Issue #1737 — Adopt five-phase legacy translation pipeline.
"""

from .five_phase_pipeline import (
    ConversionResult,
    FivePhaseConverter,
    Phase1StubGenerator,
    Phase2DependencyAnalyzer,
    Phase3APIMapper,
    Phase4CompilationRepair,
    Phase5QualityValidator,
    PhaseReport,
    PhaseStatus,
    RepairAction,
    ValidationReport,
)

__all__ = [
    "FivePhaseConverter",
    "ConversionResult",
    "Phase1StubGenerator",
    "Phase2DependencyAnalyzer",
    "Phase3APIMapper",
    "Phase4CompilationRepair",
    "Phase5QualityValidator",
    "PhaseReport",
    "PhaseStatus",
    "RepairAction",
    "ValidationReport",
]
