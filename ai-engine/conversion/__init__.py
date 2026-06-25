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

from conversion.failure_taxonomy import (
    FailureClassifier,
    FailureType,
    Severity,
    FailureClassification,
    FailureEvidence,
    classify_conversion_failure,
    classify_all_failures,
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
    # Multisage augmentation
    "MultisageAugmenter",
    "SemanticExtractor",
    "SemanticVariant",
    "AugmentationResult",
    "augment_java_snippet",
    "augment_dataset",
    "augment_java_snippet_async",
    # Failure taxonomy
    "FailureClassifier",
    "FailureType",
    "Severity",
    "FailureClassification",
    "FailureEvidence",
    "classify_conversion_failure",
    "classify_all_failures",
    # AST postprocessor
    "ASTBedrockPostprocessor",
    "BedrockAPIMethodKB",
    "PostProcessorResult",
    "HallucinatedCall",
    "HallucinationSeverity",
    "process_bedrock_code",
]
