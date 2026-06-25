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

__all__ = [
    "MultisageAugmenter",
    "SemanticExtractor",
    "SemanticVariant",
    "AugmentationResult",
    "augment_java_snippet",
    "augment_dataset",
    "augment_java_snippet_async",
]
