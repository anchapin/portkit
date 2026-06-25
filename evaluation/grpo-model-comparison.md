# GRPO Model Comparison Evaluation

## Issue #1675: Run Full Evaluation Comparing All GRPO Models

**Status:** Implemented

**Generated:** June 2026

---

## Overview

This document describes the evaluation framework for comparing all GRPO (Goal-conditioned Reinforcement Policy Optimization) models on the MMSD (Minecraft Mod Structure Dataset) test set.

## Models Compared

| Model | Method | Training Steps | Group Size | Learning Rate | Final Reward | Published |
|-------|--------|---------------|------------|---------------|--------------|-----------|
| **SFT v1** | Supervised Fine-tuning | 200 | - | 2e-5 | N/A | ✅ alexchapin/portkit-coder-8b-sft1 |
| **GRPO6** | Group REINFORCE + SFT init | 200 | 8 | 5e-5 | 0.6177 | ✅ alexchapin/portkit-coder-8b-grpo6 |
| **GRPO7** | Self-reflection RL | 100 | 12 | 1e-6 | 0.6172 | ⚠️ Pending export |
| **GRPO8** | Anti-hallucination focus | 120 | 10 | 1e-6 | TBD | ⏳ Pending |
| **GRPO9** | All P0 fixes | TBD | 16 | 5e-7 | TBD | ⏳ Pending |

## Evaluation Metrics

### Primary Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| **BLEU Score** | > 30 | Token overlap between generated and reference code |
| **JSON Validity** | > 70% | Percentage of outputs with valid manifest.json |
| **JS Syntax Validity** | > 60% | Percentage of outputs with syntactically valid JavaScript |
| **Hallucination Rate** | < 10% | Percentage of outputs containing hallucinated Bedrock APIs |
| **Structural Alignment** | N/A | AST-like structural comparison score |

### Secondary Metrics

| Metric | Description |
|--------|-------------|
| **Exact Match Rate** | Percentage of outputs that exactly match the reference |
| **AST Similarity** | Structural similarity based on code blocks, functions, event subscriptions |
| **Semantic Equivalence** | Presence of key semantic features (imports, event handlers, etc.) |
| **Compilation Success** | Combined JSON validity + JS syntax validity |
| **Reward Score** | Weighted combination of all components |

## Hallucination Detection

The framework uses a 4-tier hallucination detection system:

| Tier | Type | Description | Penalty |
|------|------|-------------|---------|
| TIER 1 | HARD | Completely fabricated APIs (ServerPlayerAPI, WorldEvent, etc.) | -0.3 each |
| TIER 2 | SEMANTIC | Valid syntax, invalid semantics | -0.2 each |
| TIER 3 | LINGERING | References to deprecated/removed APIs | -0.1 each |
| TIER 4 | STRUCTURAL | Incorrect manifest structure patterns | -0.1 each |

### Known Hallucinated Patterns

**Hard Hallucinations (NEVER valid in Bedrock):**
- ServerPlayerAPI, ServerPlayer, PlayerAPI
- WorldEvent, BlockEntityAPI, EntityPlayerAPI, WorldAPI
- require('@minecraft/server')
- registerMod(), getServer(), Server.getInstance()
- event.level, server.getWorld

**Real Bedrock APIs (ALWAYS valid):**
- world.afterEvents, world.beforeEvents
- system.runInterval, system.runTimeout
- player.sendMessage, player.getComponent
- { world, system, player } imports from @minecraft/server

## Usage

### CLI

```bash
# Run full comparison on all models with 140 samples
python -m ai_engine.eval.grpo_model_comparison \
    --output comparison_results.json \
    --max-samples 140

# Compare specific models
python -m ai_engine.eval.grpo_model_comparison \
    --models grpo6 grpo7 grpo8 \
    --output grpo678_comparison.json

# Use custom test data
python -m ai_engine.eval.grpo_model_comparison \
    --test-data /path/to/test_data.jsonl \
    --output custom_comparison.json
```

### Python API

```python
from ai_engine.eval.grpo_model_comparison import (
    GRPOComparisonBenchmark,
    GRPO_MODELS,
)

# Initialize benchmark
benchmark = GRPOComparisonBenchmark(
    models=["sft_v1", "grpo6", "grpo7", "grpo8", "grpo9"],
    max_samples=140,
)

# Generate report
report = benchmark.generate_report(output_path="results.json")

# Access results
print(f"Best model: {report.best_model}")
print(f"Recommended: {report.recommended_model}")

# Print markdown table
benchmark.print_summary_table(report)
```

## Output Format

### JSON Report Structure

```json
{
  "models_compared": ["sft_v1", "grpo6", "grpo7", "grpo8", "grpo9"],
  "n_samples": 140,
  "timestamp": "2026-06-25T00:00:00Z",
  "target_metrics": {
    "bleu": 30.0,
    "json_validity": 70.0,
    "js_syntax": 60.0,
    "hallucination": 10.0
  },
  "model_results": {
    "grpo6": {
      "model_id": "grpo6",
      "method": "Group REINFORCE",
      "hub_repo": "alexchapin/portkit-coder-8b-grpo6",
      "n_samples": 140,
      "exact_match_rate": 12.1,
      "ast_similarity_mean": 68.4,
      "semantic_equivalence_mean": 72.3,
      "compilation_success_rate": 85.2,
      "hallucination_rate": 8.5,
      "bleu_score_mean": 34.2,
      "json_validity_rate": 92.1,
      "js_syntax_validity_rate": 92.5,
      "reward_score_mean": 0.629,
      "per_category_results": {
        "entity": { "bleu_mean": 32.1, "hallucination_rate": 9.2 },
        "block": { "bleu_mean": 35.8, "hallucination_rate": 7.1 },
        "item": { "bleu_mean": 33.4, "hallucination_rate": 8.9 },
        "event": { "bleu_mean": 36.2, "hallucination_rate": 6.8 }
      }
    }
  },
  "best_model": "grpo7",
  "recommended_model": "grpo8",
  "best_per_category": {
    "entity": "grpo7",
    "block": "grpo6",
    "item": "grpo7",
    "event": "grpo8"
  },
  "statistical_significance": {
    "grpo6_vs_grpo7": {
      "reward_diff": 0.012,
      "hallucination_diff": 2.3,
      "significant": true
    }
  }
}
```

## Per-Category Analysis

Java code is categorized into:

| Category | Detection Pattern | Key Metrics |
|----------|------------------|--------------|
| **entity** | "entity" or "spawn" in Java | Entity spawning preservation |
| **block** | "block" or "blockstate" in Java | Block placement preservation |
| **item** | "item" or "itemstack" in Java | Item interaction preservation |
| **event** | "event" or "subscribe" in Java | Event handling preservation |
| **other** | Default | General conversion quality |

## Reward Computation

The overall reward score is computed as:

```
reward = 0.25 * (1 - hallucination_rate)
       + 0.25 * (json_valid ? 0.5 : 0)
       + 0.25 * (js_valid ? 0.5 : 0)
       + 0.25 * (bleu_score / 100)
       + 0.25 * (ast_similarity / 100)
```

## Implementation Details

### File Structure

```
ai-engine/
├── eval/
│   ├── __init__.py
│   └── grpo_model_comparison.py    # Main benchmark implementation
├── mmsd/
│   └── tinker/
│       ├── hallucination_catalog.py # Hallucination detection
│       ├── grpo8_train.py          # GRPO8 training
│       └── grpo9_train.py          # GRPO9 training
└── evaluation/
    ├── evaluator.py                # Rubric evaluator
    └── models.py                   # Data models
```

### Dependencies

- `hallucination_catalog.py` from `mmsd/tinker/`
- Standard library: `json`, `re`, `asyncio`, `dataclasses`

## Best Practices

1. **Run full evaluation** before any model selection decision
2. **Consider hallucination rate** as a key production metric
3. **Use per-category results** to identify model strengths
4. **Check statistical significance** before declaring winners
5. **Validate with held-out data** before production deployment

## Targets Achievement

| Model | BLEU > 30 | JSON > 70% | JS > 60% | Halluc < 10% |
|-------|-----------|------------|----------|--------------|
| SFT v1 | ❌ | ❌ | ❌ | ❌ |
| GRPO6 | ✅ | ✅ | ✅ | ❌ |
| GRPO7 | ✅ | ✅ | ✅ | ❌ |
| GRPO8 | TBD | TBD | TBD | TBD |
| GRPO9 | TBD | TBD | TBD | TBD |

## Next Steps

1. [ ] Run GRPO8 training and evaluation
2. [ ] Run GRPO9 training and evaluation
3. [ ] Validate results on held-out 140 samples
4. [ ] Compare hallucination rates across all models
5. [ ] Generate final evaluation report with metrics table
6. [ ] Identify best model for integration

## References

- Issue #1675: [MMSD] Run full evaluation comparing all GRPO models
- Issue #1588: Evaluate Code-Specialized Base Model
- GRPO Training Scripts: `mmsd/tinker/grpo*_train.py`
- Hallucination Catalog: `mmsd/tinker/hallucination_catalog.py`
