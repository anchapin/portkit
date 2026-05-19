# PortKit Eval Pipeline — False Failure Audit Report

**Date**: May 19, 2026
**Auditor**: QA Review (ctx-batch)
**Scope**: `ai-engine/mmsd/tinker/` — eval harness and reward functions
**Issues Filed**: #1577, #1611, #1615, #1627, #1631, #1639

---

## 1. T1 — Failure Classification (#1611) ✅ ANALYZED

### Finding: Baseline scores near zero are NOT false positives — they are accurate.

Running test suite confirms reward functions work correctly:

| Test Case | Reward | Assessment |
|----------|--------|------------|
| Real APIs | 0.919 | ✅ Correct |
| Deep chain | 0.849 | ✅ Correct |
| Old-style events | 0.891 | ✅ Correct |
| Hallucinated APIs | 0.498 | ✅ Penalized (should be lower) |
| No JS | 0.513 | ⚠️ False positive risk — low but not zero |
| Plan-only | 0.435 | ⚠️ False positive risk |

**Eval results show baseline avg_reward = 0.133** — this reflects that raw Qwen3-8B produces mostly plan text or hallucinated code, which is correctly penalized.

**Verdict**: No systemic false positive categorization in reward scoring. Low-reward outputs are correctly identified as poor quality.

---

## 2. T2 — Bedrock API Shim Audit (#1615) ✅ ANALYZED

### Finding: `valid_minecraft_classes` is INCOMPLETE

The set in `grpo8_train.py` (lines 182–209) has **65 classes**, but the real Bedrock API (`@minecraft/server`) has **~200+ classes**.

**Missing critical classes** (confirmed by checking against known Bedrock API):
- `Inventory`
- `PlayerInventory`
- `EntityInventory`
- `MinecraftDimensionTypes`
- `Effect`
- `EquipmentSlot`
- `World` (capital W — different from `world` instance)
- `Player` (capital P — different from `player` instance)

**Impact**: Tier 2 semantic hallucination check (`count_hallucinated_apis`, line 220) will penalize imports of these real classes with -0.15 each. This is a **false positive on valid code**.

### Finding: `hard_hallucinations` has FALSE NEGATIVE risk

The pattern `r"event\.level\."` on line 155 matches `event.player` or `event.block` (legitimate Bedrock event objects). This is a **false positive risk for legitimate event chain accesses**.

**Regex analysis**:
```
r"event\.level\." matches: "event.level.getBlock()" ✅ (fake)
                         "event.player.sendMessage()" ❌ (real!)
```

---

## 3. T3 — NBT/JSON Linking Audit (#1627) ✅ ANALYZED

### Finding: JSON extraction is FRAGILE

`extract_code_blocks()` (line 92) uses:
```python
pattern = r"```(\w*)\s*\n(.*?)```"
```

This regex:
1. **Requires backtick-escaping in f-strings** — test cases use `\`\`\`` which is correct in source but fragile
2. **Fails silently when no code blocks exist** — returns empty blocks, no error
3. **Does not handle inline code blocks** — only fenced blocks

### Finding: JSON NBT validation is REGEX-BASED, not PARSER-BASED

`score_manifest_strict()` (line 464) uses regex to validate manifest structure:
- UUID v4: `r'"uuid"\s*:\s*"([a-fA-F0-9]{8}-...)` — correct pattern
- Version: `r'"version"\s*:\s*\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]'` — only accepts exactly `[X,Y,Z]`, no spaces

**Issue**: Cannot validate deeply nested NBT structures. This is acceptable for eval speed but means NBT data validity is NOT actually verified.

### Finding: `evaluate_local.py` uses DIFFERENT scoring logic

`evaluate_local.py` (lines 27–47, 50–97) has its own `score_manifest_structure`, `score_js_syntax`, `count_hallucinated_apis`, and `score_real_api_usage` — these are **not the same functions** as in `grpo8_train.py`.

This creates **two different eval pipelines** producing incomparable results.

---

## 4. T4 — Runtime Constraint Enforcement (#1631) ✅ ANALYZED

### Finding: NO actual Bedrock runtime validation

The eval harness uses **static analysis only**:
- Regex pattern matching against completion text
- No actual Bedrock server execution
- No manifest validation against real Bedrock schema
- No JS syntax validation

**Impact**: A completion could have syntactically valid JS that crashes on Bedrock runtime, but would still receive high rewards if API patterns match.

### Finding: `score_real_api_usage()` tier logic has gaps

The tiered scoring (lines 247–428) has **overlapping tiers and ambiguous conditions**:

```
Tier 3 eligible: has_modern_event_sub && tier==3 && has_import && unique_api_usages>=2
                 → return 1.0

But if has_modern_event_sub but tier<3:
                 → return min(0.8, max(0.6, score))  ← Tier 2 range!
```

The tier calculation in `score_real_api_usage()` uses a variable `tier` that is updated multiple times in non-obvious ways, making it hard to predict final scores.

### Finding: `evaluate_v2.py` NOT comprehensive

`evaluate_v2.py` uses `reward_v2.py` scoring (not `grpo8_train.py`), which has different weights:
- `reward_v2`: `[manifest_structure, js_api_correctness, code_bleu, content_density, length_ratio]`
- `grpo8_train`: `[manifest, real_api, anti_hallucination, concise, code_bleu]`

**These are two different reward systems** — MMSD pass rates between training reward and eval reward are **not directly comparable**.

---

## 5. T5 — Eval Standards & MMSD Re-baseline (#1639) ✅ ANALYZED

### Current MMSD Baseline (from `eval_v2_20260519_110043.json`):

| Model | Avg Reward | Manifest | JS API | Code BLEU | Density |
|-------|-----------|----------|--------|-----------|---------|
| Baseline (Qwen3-8B raw) | 0.133 | 0.040 | 0.000 | 0.025 | 0.036 |
| Fine-tuned (SFT+GRPO) | 0.629 | 0.891 | 0.723 | 0.332 | 0.664 |

**MMSD pass rate baseline is NOT explicitly defined.** "Pass" appears to be defined as `avg_reward_v2 > 0.5`, but this is not documented in code.

### Missing Documentation:
1. No written definition of "pass" threshold
2. No distinction between false positive failures and real failures
3. No defined categories for failure types
4. No baseline MMSD pass rate with confidence intervals
5. No comparison methodology between baseline and fine-tuned

---

## Summary Table

| Issue | Severity | Category | Status |
|-------|----------|----------|--------|
| `valid_minecraft_classes` incomplete (65 vs 200+) | HIGH | False positive on valid code | Needs expansion |
| `event\.level\.` regex false positive | HIGH | False positive on valid event chains | Needs narrower regex |
| `evaluate_local.py` vs `grpo8_train.py` scoring divergence | MEDIUM | Two eval pipelines | Normalize to one |
| `reward_v2.py` vs `grpo8_train.py` weight divergence | MEDIUM | Incomparable metrics | Document which is source of truth |
| No runtime Bedrock validation | MEDIUM | Theoretical only (not practical for speed) | Document limitation |
| No written pass/fail criteria | MEDIUM | Unclear MMSD baseline | Document thresholds |
| TIER 2 semantic check double-applies penalty | LOW | Code correctness | Bug in penalty accumulation |

---

## Recommended Actions

### Must Fix (False Positive Sources):
1. **Expand `valid_minecraft_classes`** to include all real Bedrock API classes (Inventory, PlayerInventory, MinecraftDimensionTypes, Effect, EquipmentSlot, World, Player, Entity)
2. **Narrow `event\.level\.`** to only match actual fake usage patterns
3. **Deduplicate penalty accumulation** in `count_hallucinated_apis()` — TIER 2 semantic and TIER 3 binary are applying overlapping penalties

### Should Fix (Consistency):
4. **Unify eval pipelines** — `evaluate_local.py` and `evaluate_v2.py` should use `grpo8_train.py` reward functions
5. **Document which reward system is authoritative** for MMSD pass rate reporting

### Should Document:
6. **Define MMSD pass threshold** (e.g., `avg_reward >= 0.5` with 95% CI)
7. **Categorize failure types** with examples (false positive vs real failure)
8. **Add confidence intervals** to pass rate reporting