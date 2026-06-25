#!/usr/bin/env python3
"""
PortKit Pivot IR — Intermediate Representation for Java→Bedrock Transpilation
============================================================================

Pivot IR is a structured intermediate representation that captures essential
translation logic between Java mods and Bedrock add-ons. It provides:

1. **Abstraction**: Separates parsing from code generation
2. **Composability**: Enables independent adapter development
3. **Debuggability**: Human-readable IR for inspection
4. **Partial Evaluation**: Supports partial functionality (APF reward)

Architecture:
  Java Source → [JavaParser] → PivotIR → [BedrockEmitter] → Bedrock Add-on

Pivot IR Design Principles:
  - Capture semantics, not syntax (Java events → Bedrock event subscriptions)
  - Keep mapping rules explicit (not implicit in model)
  - Support incremental coverage (core patterns first)
  - Enable reward shaping (APF rewards partial correctness)

IR Structure:
  - entities: Block, Item, Entity, Container definitions
  - events: Event handlers with Java→Bedrock mapping
  - apis: API call patterns (world.*, player.*, dimension.*)
  - manifests: Add-on manifest metadata

Author: PortKit AI Engine
Issues: #1578, #1594, #1599, #1600, #1605, #1624, #1626
"""

# Import schema first (base types)
from pivot_ir.schema import (
    PivotIR,
    EventHandler,
    APICall,
    Manifest,
    BlockDef,
    ItemDef,
    EntityDef,
    EntityType,
    EventType,
    create_pivot_ir,
    pivot_ir_to_dict,
    dict_to_pivot_ir,
    compute_coverage,
    ir_to_text_summary,
)

# Adapters
from pivot_ir.java_parser import (
    JavaToPivotIRAdapter,
    parse_java_to_pivot_ir,
    JAVA_TO_BEDROCK_EVENTS,
    JAVA_TO_BEDROCK_API,
    SAMPLE_JAVA_BLOCK,
    SAMPLE_JAVA_ITEM,
    SAMPLE_JAVA_ENTITY,
)

from pivot_ir.bedrock_emitter import (
    PivotIRToBedrockAdapter,
    emit_pivot_ir_to_bedrock,
    emit_manifest,
    emit_script,
    emit_entity_definition,
    BEDROCK_EVENT_PATTERNS,
)

# APF Reward
from pivot_ir.apf_reward import (
    compute_apf_reward,
    score_entity_coverage,
    score_event_coverage,
    score_api_coverage,
    score_structure,
    APFRewardConfig,
    DEFAULT_APF_CONFIG,
    compute_apf_with_legacy,
    count_hallucinated_apis_in_completion,
)

# Benchmark
from pivot_ir.benchmark import (
    BenchmarkResult,
    run_benchmark,
    run_single_benchmark,
    print_benchmark_report,
    compare_direct_vs_pivot,
    SAMPLE_TEST_CASES,
    compute_bleu,
)

__all__ = [
    # Schema
    "PivotIR",
    "Entity",
    "EventHandler",
    "APICall",
    "Manifest",
    "BlockDef",
    "ItemDef",
    "EntityDef",
    "EventMapping",
    "EntityType",
    "EventType",
    "create_pivot_ir",
    "pivot_ir_to_dict",
    "dict_to_pivot_ir",
    "compute_coverage",
    "ir_to_text_summary",
    # Adapters
    "JavaToPivotIRAdapter",
    "parse_java_to_pivot_ir",
    "JAVA_TO_BEDROCK_EVENTS",
    "JAVA_TO_BEDROCK_API",
    "SAMPLE_JAVA_BLOCK",
    "SAMPLE_JAVA_ITEM",
    "SAMPLE_JAVA_ENTITY",
    "PivotIRToBedrockAdapter",
    "emit_pivot_ir_to_bedrock",
    "emit_manifest",
    "emit_script",
    "emit_entity_definition",
    "BEDROCK_EVENT_PATTERNS",
    # APF Reward
    "compute_apf_reward",
    "score_entity_coverage",
    "score_event_coverage",
    "score_api_coverage",
    "score_structure",
    "APFRewardConfig",
    "DEFAULT_APF_CONFIG",
    "compute_apf_with_legacy",
    "count_hallucinated_apis_in_completion",
    # Benchmark
    "BenchmarkResult",
    "run_benchmark",
    "run_single_benchmark",
    "print_benchmark_report",
    "compare_direct_vs_pivot",
    "SAMPLE_TEST_CASES",
    "compute_bleu",
]

__version__ = "0.1.0"
