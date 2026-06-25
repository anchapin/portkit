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
from conversion.ast_postprocessor import (
    ASTBedrockPostprocessor,
    BedrockAPIMethodKB,
    PostProcessorResult,
    HallucinatedCall,
    HallucinationSeverity,
    process_bedrock_code,
)

__all__ = [
    "MultisageAugmenter",
    "SemanticExtractor",
    "SemanticVariant",
    "AugmentationResult",
    "augment_java_snippet",
    "augment_dataset",
    "augment_java_snippet_async",
    "ASTBedrockPostprocessor",
    "BedrockAPIMethodKB",
    "PostProcessorResult",
    "HallucinatedCall",
    "HallucinationSeverity",
    "process_bedrock_code",
]
