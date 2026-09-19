# SwiftTrans Dual-Stage Strategy for Bedrock Code Generation

Resolves [#1765](https://github.com/anchapin/portkit/issues/1765).

Reference paper: **SwiftTrans: Bridging Functional Correctness and Runtime
Efficiency Gaps in LLM-Based Code Translation**
([arXiv:2606.17683](https://arxiv.org/abs/2606.17683), Wang & Zhang, 2026).

## TL;DR

PortKit's current conversion pipeline uses the first-pass LLM translation
as-is. SwiftTrans's empirical finding is that this is exactly the regime
where LLM-translated code runs *consistently slower* than human-written
equivalents, and that prompt engineering alone cannot close the gap. The
fix is a two-stage strategy: fan out multiple diverse candidates, then rank
them on a *combined* correctness + runtime-efficiency signal.

This module implements that strategy behind an opt-in flag
(`SwiftTransConfig.enabled`). When the flag is off, the existing single-pass
behaviour is preserved byte-for-byte.

## Implementation map

| Paper concept            | PortKit module                          | Status        |
| ------------------------ | --------------------------------------- | ------------- |
| Stage 1 — MpTranslator   | `swifttrans/candidate_generator.py`     | Implemented   |
| Stage 2 — DiffSelector   | `swifttrans/diff_selector.py`           | Implemented   |
| Phase 3 — Static scorer  | `swifttrans/efficiency_scorer.py`       | Implemented   |
| Phase 4 — MMSD enrichment| (training-data pipeline)                | **Deferred**  |
| Pipeline wiring          | `orchestration/langgraph_pipeline.py`   | Opt-in hook   |

The strategy lives in the top-level `swifttrans/` package, following the
established pattern for paper-grounded modules in this codebase
(`reasoning_patterns/`, `rl/`, `evaluation/`).

## Why each stage is the way it is

### Stage 1 — MpTranslator (multi-perspective exploration)

`MpTranslator` generates one candidate per `CandidateVariant`. Each variant
applies *Hierarchical Guidance*: a shared structural prefix ("must be valid
Bedrock JS, must preserve behaviour") plus a different *secondary*
constraint (efficiency, idiomaticity, minimal allocation, structural
fidelity, baseline). Keeping the structural prefix identical is what makes
the candidates genuinely comparable in Stage 2.

The translator callable is injected via the `Translator` Protocol so this
stage is unit-testable without an LLM, and so PortKit's existing
`LogicTranslatorAgent` (or a LangGraph `Send` fan-out) can be wired in
later without coupling. See `StubTranslator` for the deterministic test
default.

### Stage 2 — DiffSelector (difference-aware selection)

`DiffSelector` ranks the Stage 1 candidates in two passes:

1. **Deterministic pre-filter** (`BedrockEfficiencyScorer`): every
   candidate is scored on the Bedrock tick-budget anti-patterns catalogued
   in `EfficiencyAntiPattern`. Candidates scoring below the low-tier
   threshold are rejected *before* any LLM ranking cost is incurred — this
   is the paper's recommended cheap-elimination step.
2. **Ordinal ranking** (`RankingJudge`): the survivors are handed to a
   pluggable judge. The default `HeuristicRankingJudge` blends the
   efficiency score with a correctness proxy (the rubric-grounded
   evaluator from #1367, when wired in). An LLM judge implementing
   Ordinal Guidance can be slotted in via the same Protocol without
   touching the orchestrator.

A safety fallback preserves the least-bad candidate if the pre-filter
would reject everything, so the pipeline never silently emits empty
output.

### Phase 3 — Bedrock static efficiency scorer

The scorer is intentionally non-LLM and deterministic. The detected
anti-patterns are the ones the SwiftTrans preliminary study identifies as
the dominant causes of LLM-translated Bedrock code running slow:

- per-tick object allocation (`new` inside `system.runInterval`)
- unbounded / redundant entity queries (`world.getEntities()`)
- blocking sleeps (`setTimeout`, busy-wait loops)
- deep nested loops inside tick callbacks
- `+=` string concatenation in hot paths

Each violation carries a remediation hint so the DiffSelector's reasoning
is auditable — a hard requirement for B2B mod conversions where efficiency
regressions must be explainable.

## Opt-in wiring

`SwiftTransConfig.enabled` defaults to `False`. When disabled,
`SwiftTransStrategy.run` returns the caller-supplied baseline candidate
unchanged. This lets the module land behind a flag while we gather
efficiency-regression telemetry on real conversions.

The intended integration point is the LangGraph conversion pipeline's
logic-translator node (`orchestration/langgraph_pipeline.py`). A minimal
wiring would:

1. After `_strategy_planner_node` resolves the conversion plan, construct a
   `SwiftTransStrategy` from the job config.
2. In the logic-translator node (or its retry node), call
   `strategy.run(java_source, baseline=single_pass_candidate)` and emit
   `result.selected.code` as the translated script.
3. Persist `result.ranking.to_dict()` alongside the script for audit.

That wiring is deliberately left as a follow-up task: it touches the live
conversion path and warrants its own staged rollout with telemetry, whereas
the strategy module itself is independently testable and reviewable.

## Deferred work

### Phase 4 — MMSD fine-tuning data enrichment

The issue's Phase 4 proposes labelling MMSD training pairs with an
efficiency tier and biasing fine-tuning toward high-efficiency Bedrock
examples. This is a data-labelling + training-pipeline task, not a
code-gen strategy, and lives in a different part of the codebase
(`ai-engine/mmsd/`, `ai-engine/training_manager.py`). It is tracked as
follow-up work and intentionally excluded from this PR to keep the
strategy module reviewable in isolation.

### LLM Ordinal Guidance judge

The `RankingJudge` Protocol supports an LLM-based ordinal ranker (rank-all-
at-once with explicit difference reasoning, per the paper). The default
`HeuristicRankingJudge` is sufficient to land the strategy and capture
most of the win per the SwiftTrans evaluation; a production LLM judge is a
follow-up that depends on the prompt-audit work in `prompt_audit_lib/`.

## Testing

Unit tests cover each stage independently plus a full Stage 1 → Stage 2
integration run:

```
pytest ai-engine/tests/test_swifttrans_strategy.py -v
```

The tests use `StubTranslator` (deterministic, variant-distinguishable
output) so they run without an LLM and are stable under the coverage gate.
