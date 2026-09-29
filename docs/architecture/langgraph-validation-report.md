# LangGraph Behavioral Assumptions Validation Report

**Issue:** [#1722](https://github.com/anchapin/portkit/issues/1722)
**Validator:** `ai-engine/orchestration/langgraph/langgraph_validator.py`
**Date:** 2026-06-25
**Reference Paper:** arxiv [2605.18332](https://arxiv.org/abs/2605.18332v1) — *Same Signal, Different Semantics: A Cross-Framework Behavioral Analysis of Software Engineering Agents*

---

## Executive Summary

PortKit's LangGraph pipeline was validated against cross-framework SE agent evidence and a battery of structural correctness checks. All 4 automated check categories **PASS**. Two implementation bugs were caught and fixed before they could cause silent data corruption or confidence metric drift. Three behavioral heuristics borrowed from non-LangGraph literature are flagged as **framework-uncertain** and require PortKit-specific ablation validation before their thresholds are treated as ground truth.

---

## 1. Cross-Framework Evidence (arxiv 2605.18332)

The referenced 64,380-run study across 126 configurations / 43 frameworks establishes:

| Finding | Implication for PortKit |
|---|---|
| Framework identity explains **64%** of behavioral variance (vs LLM's 10%) | PortKit-specific pipeline architecture is the primary lever; LLM selection is secondary |
| **Direction-divided error-rate signal**: 47 configs lower-error→better, 48 configs higher-error→better | The "lower error rate → better quality" assumption borrowed from SWE-Agent literature can reverse in LangGraph |
| Confidence thresholds are **framework-specific**; numeric targets require per-framework calibration | PortKit's 0.80 confidence threshold needs ablation, not assumption |
| Only 1 of 7 binary behavioral patterns (P6) cleared the chance baseline across all configs | Prior SE agent behavioral rules cannot be naively applied |
| LangGraph Send-based fan-out is architecture-appropriate for parallel converter nodes | PortKit's fan-out strategy is well-founded |

### Key Takeaway

> **Behavioral findings from any single framework warrant cross-configuration validation before being claimed as general for PortKit.** A rule applied without checking framework fit can mislead.

---

## 2. Automated Validator: `langgraph_validator.py`

Located at: `ai-engine/orchestration/langgraph/langgraph_validator.py`

Runs 4 independent check categories:

### 2.1 State Completeness — **PASS**

Verifies every node reads only declared `ConversionState` fields and every written field is declared.

**Checks:**
- Every field read by a node is declared in `ConversionState`
- Every written field is either declared or is a mergeable accumulator key (`converted_scripts`, `converted_assets`, `errors`, `warnings`, `node_status`)
- No orphan fields in the schema (fields declared but never written)

**Result:** PASS — no missing fields, no orphan fields.

### 2.2 Edge Correctness — **PASS**

Verifies all `add_edge` and `add_conditional_edges` connections reference declared nodes.

**Checks:**
- All edge sources and targets are declared node names or `START`/`END`
- QA validator conditional routing has all three routes: `retry`, `hitl`, `complete`
- `decide_qa_route` has a `retry_count >= max_retries` guard to bound the retry loop
- `decide_qa_route` compares `pass_rate` against a threshold

**Result:** PASS — all edges are correctly wired. Retry loop is bounded.

### 2.3 Checkpoint Integrity — **PASS**

Verifies checkpoint configuration matches the state's reducer requirements.

**Checks:**
- `SqliteSaver` thread-safety rationale documented (`check_same_thread=False`)
- `MemorySaver` fallback present when `SqliteSaver` is unavailable
- `thread_id` uses `self.job_id` for per-job checkpoint isolation
- HITL resume (`resume_from_interruption`) clears `needs_human_review` to avoid re-interruption

**Result:** PASS — `needs_human_review` is correctly reset in `resume_from_interruption` (graph_builder.py:831).

### 2.4 Concurrency Safety — **PASS**

Verifies no race conditions in async parallel node execution.

**Checks:**
- All mergeable fields (`converted_scripts`, `converted_assets`, `errors`, `warnings`, `node_status`) are `Annotated` with reducers
- Parallel-branch nodes do not write singleton fields that would race

**Important architectural note:** The 4 converter nodes (`block_converter`, `entity_converter`, `recipe_converter`, `asset_converter`) are the only nodes in the parallel fan-out. All other nodes (`java_analyzer`, `strategy_planner`, `output_assembler`, `qa_validator`, `logic_translator_retry`, `final_report`) run in a linear chain and have no parallel race risk.

**Result:** PASS — parallel nodes only write to mergeable fields. No race conditions detected.

### 2.5 Cross-Framework Heuristic Audit — **WARNING × 3**

Flags behavioral heuristics borrowed from non-LangGraph SE agent literature.

| Heuristic | Source | Status | Recommendation |
|---|---|---|---|
| `pass_rate >= threshold → complete` | SWE-Agent / OpenHands | ⚠️ FRAMEWORK-UNCERTAIN | RETAIN with monitoring; direction-divided in study |
| `retry_count >= max_retries → stop` | SWE-Agent retry literature | ⚠️ FRAMEWORK-UNCERTAIN | RETAIN; necessary guard; monitor for reversal |
| `confidence < 0.80 → review_flag` | General SE literature | ⚠️ FRAMEWORK-UNCERTAIN | CALIBRATE via ablation; find PortKit-specific value |
| Fan-out 4 parallel converters | PortKit empirical | ✅ PASS | RETAIN — PortKit-derived |
| `interrupt()` for HITL | LangGraph / PortKit | ✅ PASS | RETAIN — LangGraph-native |

---

## 3. Bugs Found and Fixed

### Bug 1: Position-Based Confidence Score (Fixed in graph_builder.py:695–717)

**Severity:** Medium — incorrect quality metrics, framework-uncertain assumption

**Problem:** `_generate_confidence_segments` computed confidence as `0.95 - (i * 0.01)` where `i` is the script's index in the list. This is a **naive index-based heuristic** that has no connection to actual conversion quality. The study (arxiv 2605.18332) shows that framework-agnostic heuristics can be misleading.

**Fix:** Now reads `script.get("confidence")` from the actual converted script data (set by the converter nodes). Falls back to 0.85 if not present. Also reads `script.get("review_flag")` directly from the converter output.

**Code change:** `graph_builder.py` — `_generate_confidence_segments` now uses per-script confidence values rather than index-based assignment.

### Bug 2: HITL Corrections Not Applied (Fixed in retry_fallback.py)

**Severity:** High — human review feedback was read but silently discarded

**Problem:** `execute_logic_translator_retry` read `hitl_feedback.get("corrections", {})` and logged them, but never applied the corrections to the converted scripts. The corrections dict was iterated over with a comment placeholder, then immediately dropped. The retry node returned only `{"retry_count": retry_count + 1, ...}` without updating the scripts.

**Fix:** Corrections are now applied in-place to matching scripts in `converted_scripts` by segment ID or name. The `corrected: True` flag and updated `confidence`/`review_flag`/`data` fields are set on the corrected scripts. The `corrected_segment_keys` field (new in `ConversionState`) tracks which segments were corrected. Duplicate via the `_concat_lists` reducer is avoided by not returning `converted_scripts` from the retry node.

**Code change:** `retry_fallback.py` — `execute_logic_translator_retry` now applies corrections to the converted scripts in-place and records corrected segment keys. `state_schema.py` — `corrected_segment_keys: Annotated[List[str], _concat_lists]` added to `ConversionState`.

---

## 4. Remaining Framework-Uncertain Heuristics (Action Items)

These heuristics are retained but flagged for future empirical validation:

### 4.1 Confidence Threshold Calibration

**Current value:** `0.80` (hard-coded in `_generate_confidence_segments`)
**Recommended action:** Run A/B ablation on MMSD test set: toggle threshold across {0.70, 0.75, 0.80, 0.85, 0.90} and measure conversion pass rate, hallucination rate, and latency. The arxiv study shows numeric targets derived from one framework do not transfer.

### 4.2 Error Rate → Quality Signal

**Current logic:** `pass_rate >= 0.80 → complete`
**Risk:** 48/95 configs in the study showed *higher* error rates correlating with *better* resolution. The signal is direction-divided.
**Recommended action:** Instrument the pipeline to track per-run `pass_rate` vs eventual conversion quality. If PortKit shows the same directional split, invert the threshold logic.

### 4.3 Retry Budget

**Current value:** `max_retries = 3` (hard-coded in `ConversionPipeline.DEFAULT_MAX_RETRIES`)
**Recommended action:** Study shows some frameworks benefit from extended retry while others spiral. Track retry-iteration outcomes in PortKit to find the optimal cap.

---

## 5. Validation Methodology

The validator (`langgraph_validator.py`) is designed to be runnable in CI:

```bash
python3 ai-engine/orchestration/langgraph/langgraph_validator.py
# Exit code 1 if any FAIL verdicts exist
```

Checks are implemented via static analysis (AST parsing of the pipeline files) and can run without a live execution environment. The cross-framework heuristic audit is a schema-driven rules table that can be extended as new heuristics are discovered or borrowed.

---

## 6. Files Changed

| File | Change |
|---|---|
| `ai-engine/orchestration/langgraph/langgraph_validator.py` | New — validator with 4 check categories + cross-framework audit |
| `ai-engine/orchestration/langgraph/graph_builder.py` | Bugfix: confidence from actual script data (was index-based) |
| `ai-engine/orchestration/langgraph/retry_fallback.py` | Bugfix: HITL corrections now applied to converted scripts |
| `ai-engine/orchestration/langgraph/state_schema.py` | Added `corrected_segment_keys` field |
| `docs/architecture/langgraph-validation-report.md` | This report |
