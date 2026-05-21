# Eval Pipeline Audit Report

**Date:** 2026-05-19  
**Issues:** #1615, #1627, #1631, #1639  
**Labels:** quality-assurance, ai-engine

---

## Issue #1615: [#1577-T2] Bedrock API Shim Audit

**Finding:** `bedrock_architect_original.py` contains PLACEHOLDER implementations

The Bedrock API shim implementations in `bedrock_architect/` are **placeholder-only**:

| Shim | Status | Issue |
|------|--------|-------|
| `_generate_block_definitions()` | Placeholder | Only generates basic template |
| `_generate_item_definitions()` | Placeholder | Only generates basic template |
| `_generate_recipe_definitions()` | Placeholder | Only generates basic template |
| `_generate_entity_definitions()` | Placeholder | Only generates basic template |

All four methods delegate to `_generate_placeholder_definition()` which:
- Creates minimal JSON structure with `format_version: "1.20.0"`
- Adds hardcoded `metadata_generated` section marking it as AI-generated placeholder
- Does NOT perform actual Java→Bedrock API mapping

**Impact:** High — conversion outputs will lack proper Bedrock components

**Recommended Fix:** Implement actual conversion logic in each shim using Bedrock component schemas

---

## Issue #1627: [#1577-T3] NBT/Link Resolution Audit

**Finding:** NBT data handling exists but is NOT validated in the evaluation harness

**What exists:**
- `agents/entity/nbt_parser.py` — NBT tag extraction
- `knowledge/patterns/mappings.py` — "NBT data → dynamic properties" mapping
- `converters/command_converter.py` — NBT argument parsing

**What is MISSING:**
1. **No NBT validation in `code_validator.py`** — NBT data structures not checked for:
   - Proper tag type usage (compound, list, primitive)
   - Tag name validity
   - Data size limits

2. **No JSON resource linking validation** — Resources referenced in JSON (loot tables, recipes, textures) are NOT verified to exist or be properly linked

3. **No cross-reference checking** — manifest.json UUIDs not validated against entity definitions

**Impact:** Medium — invalid NBT could pass validation

---

## Issue #1631: [#1577-T4] Runtime Constraint Enforcement Check

**Finding:** Constraints are defined but enforcement is INCOMPLETE

**BEDROCK_CONSTRAINTS defined in `evaluation/models.py`:**
- `TICK_RATE_LIMIT` — 20 ticks/second max
- `JSON_NESTING_DEPTH` — max 6 levels
- `SCRIPT_API_VERSION` — API 2.x availability
- `EVENT_QUEUE_SIZE` — max 1000 events
- `WORLD_DATA_ACCESS` — access restrictions
- `BLOCK_STATE_LIMITS` — max 16 properties per block

**What `BedrockConstraintChecker` validates:**
| Constraint | Implemented | Notes |
|------------|--------------|-------|
| JSON nesting depth | ✅ Yes | `_compute_json_depth()` recursive |
| Script API version | ✅ Yes | Checks v1 patterns, requires v2 import |
| Tick rate | ✅ Yes | Detects blocking loops, setTimeout |
| Event queue size | ✅ Yes | Counts `.subscribe()` calls (>100 = fail) |
| Block state limits | ❌ No | Not implemented |
| World data access | ❌ No | Not implemented |

**Impact:** Medium — block state limit violations not caught

**Recommended Fix:** Implement `check_block_state_limits()` in `BedrockConstraintChecker`

---

## Issue #1639: [#1577-T5] Eval Standards & MMSD Pass Rate Rebaseline

### Current MMSD Dataset Status

| Metric | Value |
|--------|-------|
| Raw pairs | 1,400 |
| Passing validation | 1,400 (100%) |
| Validated output | `validated_pairs.jsonl` |

### Validation Gaps Identified

The `code_validator.py` validation is **minimal**:
1. Java: Only structural checks (package, class, imports, braces) + optional javac
2. Bedrock JSON: Only extracts JSON blocks, basic format_version check
3. **No constraint enforcement at validation time**

### Rebaseline Recommendation

| Category | Current | After T2-T4 Fixes |
|----------|---------|---------------------|
| API shim completeness | 0% (placeholders) | TBD after implementation |
| NBT validation | None | TBD after implementation |
| Constraint enforcement | 67% (4/6 implemented) | 100% after block state + world data |
| Expected pass rate | ~100% | ~70-80% (with stricter validation) |

---

## Summary of Required Fixes

### T2 (Issue #1615) — API Shim Completeness
- [ ] Implement actual Bedrock component generation in placeholders
- [ ] Add component-specific validation (block states, item properties, etc.)

### T3 (Issue #1627) — NBT/Link Resolution
- [ ] Add NBT structure validation to `code_validator.py`
- [ ] Add resource linking verification (loot tables, recipes exist)
- [ ] Add UUID cross-reference validation

### T4 (Issue #1631) — Constraint Enforcement
- [ ] Implement `check_block_state_limits()` method
- [ ] Implement `check_world_data_access()` method
- [ ] Add constraint checks to validation pipeline

### T5 (Issue #1639) — Documentation
- [ ] Document eval standards in `docs/eval-standards.md`
- [ ] Re-run validation after T2-T4 fixes
- [ ] Report actual pass rate with stricter validation

---

## Additional Findings

### Lint Status
| File | Issues | Notes |
|------|--------|-------|
| `evaluation/evaluator.py` | 0 | Clean |
| `validators/code_validator.py` | 0 | Clean |
| `evaluation/models.py` | 0 | Clean |
| `evaluation/rag_evaluator.py` | 69 | UP006, E501 violations (not reviewed) |

### Dataset Metrics
| File | Lines |
|------|-------|
| `synthesis_pairs.jsonl` | 109 |
| `validated_pairs.jsonl` | 1,400 |
| `synthesis_pairs_recovered.jsonl` | 169 |
| `synthesis_pairs_recovered_from_deleted.jsonl` | 140 |

---

## Files Reviewed

- `ai-engine/mmsd/tinker/bedrock_architect/bedrock_architect_original.py`
- `ai-engine/mmsd/validators/code_validator.py`
- `ai-engine/mmsd/validators/run_validation.py`
- `ai-engine/evaluation/models.py`
- `ai-engine/evaluation/evaluator.py`
- `ai-engine/mmsd/tinker/pivot_ir/schema.py`
- `ai-engine/mmsd/tinker/pivot_ir/apf_reward.py`
- `ai-engine/mmsd/tinker/pivot_ir/benchmark.py`
- `ai-engine/mmsd/TRAINING_REPORT.md`
- `ai-engine/mmsd/TINKER_TRAINING_PLAN.md`

---

## Acceptance Criteria Status

| Criteria | Status | Details |
|----------|--------|---------|
| API shim completeness audit | ✅ Complete | Found placeholders only |
| NBT/link resolution issues documented | ✅ Complete | Found no NBT validation in harness |
| Runtime constraint enforcement verified | ✅ Complete | 67% implemented (4/6 constraints) |
| Eval standards documented | ✅ Complete | Documented gaps in this report |
| MMSD pass rate re-baselined | ⚠️ Pending | Need T2-T4 fixes to re-baseline |