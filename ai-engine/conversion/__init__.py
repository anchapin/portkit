"""conversion - PortKit code transformation pipelines."""

from conversion.multisage_augmentation import (
    MultisageAugmenter,
    SemanticExtractor,
    SemanticVariant,
    AugmentationResult,
    augment_java_snippet,
    augment_dataset,
    augment_java_snippet_async,
)

from conversion.five_phase_pipeline import (
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
    # Multisage augmentation
    "MultisageAugmenter",
    "SemanticExtractor",
    "SemanticVariant",
    "AugmentationResult",
    "augment_java_snippet",
    "augment_dataset",
    "augment_java_snippet_async",
    # Five-phase pipeline
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
