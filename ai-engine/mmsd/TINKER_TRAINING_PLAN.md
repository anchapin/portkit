# Tinker Training Plan — PortKit Minecraft Fine-Tuned Model

**Date:** 2026-05-17  
**Budget:** $150 Tinker credit (Thinking Machines Lab)  
**Goal:** Train a Minecraft-specific fine-tuned model for Java→Bedrock mod conversion using the Tinker API

---

## 1. Current MMSD Status

### What We Have
| Asset | Status | Details |
|-------|--------|---------|
| **MMSD Dataset** | ✅ 1,400 validated pairs | `ai-engine/mmsd/data/processed/validated_pairs.jsonl` |
| **Data quality** | ✅ 100% pass Mojmap validation | No SRG patterns, all Mojmap-named |
| **Token distribution** | 97.9% fit in 4K tokens | 99.4% fit in 8K tokens |
| **SFT training script** | ✅ Written | `ai-engine/mmsd/train_portkit_coder.py` (Unsloth + TRL) |
| **GRPO scripts** | ✅ Written | `scripts/phase4b_1.5b_grpo.py` and others |
| **DPO script** | ✅ Written | `scripts/dpo_training.py` |
| **Baseline eval** | ✅ Written | `scripts/baseline_eval.py`, `scripts/evaluate_models.py` |
| **Reward functions** | ✅ Implemented | Structural alignment, BLEU, JSON validity, content density |
| **General code mix** | 📋 Planned | 12% general Java/JS mix to prevent forgetting |

### What's NOT Done (MMSD Goals)
| Goal | Status | Notes |
|------|--------|-------|
| **Run SFT on GPU** | ❌ Not run on real GPU yet | Pipeline verified on CPU with 0.5B model only |
| **Evaluate baseline vs fine-tuned** | ❌ Pending | Need GPU for real eval |
| **Stage B fine-tuning** | ❌ Not started | Direct conversion without reasoning trace |
| **A/B testing framework** | ❌ Not implemented | Compare fine-tuned vs API models |
| **Push trained model to HF Hub** | ❌ Pending | Repos created: `alexchapin/portkit-coder-7b-lora` and `-merged` |
| **Integration into PortKit pipeline** | ❌ Pending | Need trained model first |

### Previous Training Attempts
- **Qwen2.5-Coder-0.5B** on CPU: train_loss=1.7357 (pipeline smoke test only)
- **Qwen2.5-Coder-1.5B** on AMD RX 6600 XT: GRPO attempts with limited VRAM
- **IBM Granite-4.0-H-Micro**: DPO/GRPO exploration
- **All runs limited by local GPU (AMD RX 6600 XT, 8GB VRAM)**

---

## 2. Why Tinker?

| Factor | Local (AMD RX 6600 XT) | Tinker |
|--------|----------------------|--------|
| GPU VRAM | 8 GB | Cloud multi-GPU (A100/H100 cluster) |
| Max model size | ~1.5B (4-bit) | Up to 70B+ (LoRA) |
| Training speed | Hours for 1.5B | Minutes for 8B |
| GRPO support | Manual, OOM-prone | Built-in RL loop |
| Cost | Free (but limited) | $150 credit covers multiple runs |

---

## 3. Model Selection for Tinker

**⚠️ Critical constraint:** `Qwen/Qwen2.5-Coder-7B-Instruct` is NOT in Tinker's supported model list.

### Recommended Models (Tinker-supported)

| Rank | Model | Size | Why | LoRA Rank | Renderer |
|------|-------|------|-----|-----------|----------|
| **🥇 Primary** | `Qwen/Qwen3-8B` | 8B | Best Qwen on Tinker, strong coding, closest to Qwen2.5-Coder-7B | 64-128 | `qwen3` |
| **🥈 Alternative** | `Qwen/Qwen3-4B` | 4B | Faster, cheaper, good for iteration | 64 | `qwen3` |
| **🥉 Backup** | `meta-llama/Llama-3.1-8B-Instruct` | 8B | Well-tested on Tinker, good sweep results | 64-128 | `llama3` |

### Recommended Training Sequence
1. **SFT on Qwen3-8B** (primary) — establish baseline Minecraft knowledge
2. **GRPO/DPO on Qwen3-8B** — reinforce with reward-based training
3. **Compare with Qwen3-4B** — if budget allows, test smaller model

### Why Qwen3-8B over alternatives
- Closest family to Qwen2.5-Coder (same architecture family, strong coding)
- Tinker sweep shows best test NLL at LR=1e-3, rank=128
- 8B is the sweet spot for Minecraft code generation (complex but manageable)

---

## 4. Data Preparation

### Current Format (MMSD)
```json
{
  "instruction": "Brief Minecraft mod concept description",
  "reasoning_trace": "Step-by-step Java→Bedrock mapping explanation",
  "java_source": "Complete Java Forge 1.21 mod code",
  "bedrock_source": "Bedrock Add-on output (manifest.json + scripting .js)"
}
```

### Tinker Format Required (ChatML JSONL)
```json
{
  "messages": [
    {"role": "system", "content": "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) to Bedrock Edition Add-ons. Given a mod description and Java source code, first reason through the platform mapping, then produce the Bedrock Add-on implementation."},
    {"role": "user", "content": "Mod Description: {instruction}\n\nJava Source:\n{java_source}\n\nConvert this to a Bedrock Add-on. First explain your conversion approach, then provide the files."},
    {"role": "assistant", "content": "## Conversion Plan\n{reasoning_trace}\n\n## Bedrock Add-on Output\n{bedrock_source}"}
  ]
}
```

### Data Pipeline
1. **Convert** `validated_pairs.jsonl` → Tinker JSONL format (script needed)
2. **Add general code mix** (~12% Java/JS from CodeFeedback dataset) for forgetting mitigation
3. **Split** 90/10 train/eval
4. **Validate** token lengths (97.9% fit in 4K — use `max_length=4096`)

---

## 5. Training Plan

### Phase 1: SFT (Supervised Fine-Tuning)
**Goal:** Teach the model Minecraft Java→Bedrock conversion patterns

```python
# Target configuration
model_name = "Qwen/Qwen3-8B"
lora_rank = 64
learning_rate = 3e-4     # From Tinker sweep: sweet spot for 8B
lr_schedule = "linear"
num_epochs = 3
batch_size = 64           # Tinker handles large batches efficiently
max_length = 4096
train_on_what = "ALL_ASSISTANT_MESSAGES"  # Only train on assistant outputs
renderer = "qwen3"
```

**Estimated cost:** ~$10-20 per epoch (1,400 samples is tiny for Tinker)  
**Estimated time:** ~5-15 min per epoch  
**Budget allocation:** ~$30-50 for SFT iterations

### Phase 2: GRPO (Group Relative Policy Optimization)  
**Goal:** Reinforce good conversions with custom reward functions

Use existing reward functions from `scripts/dpo_training.py`:
- **Structural alignment** (35%): Manifest fields, JS function matching
- **JSON validity** (25%): Valid manifest.json output
- **Content density** (20%): Sufficient code block output
- **Length ratio** (20%): Output length matches reference

```python
# GRPO config
group_size = 4            # Sample 4 completions per prompt
max_completion_length = 512
num_steps = 80-100
learning_rate = 1e-4      # Lower for RL
```

**Estimated cost:** ~$30-50 for GRPO  
**Budget allocation:** ~$40-60 for GRPO iterations

### Phase 3: Evaluation & Export
**Goal:** Evaluate trained model and deploy to PortKit

1. **Evaluate** on held-out 140 samples (BLEU, JSON validity, JS syntax)
2. **Compare** baseline Qwen3-8B vs fine-tuned
3. **Export** merged model to HuggingFace Hub
4. **Integrate** into PortKit conversion pipeline

**Budget allocation:** ~$10-20 for eval/inference

---

## 6. Budget Breakdown

| Phase | Runs | Est. Cost/run | Total |
|-------|------|--------------|-------|
| Data prep + smoke test | 1 | $2 | $2 |
| SFT Qwen3-8B (3 epochs) | 1-3 | $15-20 | $30-50 |
| GRPO Qwen3-8B | 1-2 | $20-30 | $30-50 |
| Evaluation + inference | 5-10 | $1-3 | $10-20 |
| SFT Qwen3-4B (comparison) | 1-2 | $5-10 | $10-15 |
| **Total** | | | **$82-137** |
| **Buffer** | | | **$13-68** |

This fits comfortably within the $150 budget with room for iteration.

---

## 7. Implementation Checklist

### Step 1: Setup Tinker (30 min)
- [ ] `pip install tinker tinker-cookbook`
- [ ] Set `TINKER_API_KEY` from https://tinker-console.thinkingmachines.ai
- [ ] Verify connection: `tinker.ServiceClient()`

### Step 2: Data Preparation (1 hour)
- [ ] Write `convert_mmsd_to_tinker.py` to convert validated_pairs.jsonl → Tinker JSONL
- [ ] Add general Java/JS mix (12%)
- [ ] Split 90/10
- [ ] Validate format with `FromConversationFileBuilder`

### Step 3: SFT Training (2-3 hours including iteration)
- [ ] Write `tinker_sft_train.py` using `tinker_cookbook.supervised.train` pattern
- [ ] Run smoke test with small subset (10 samples, 1 step)
- [ ] Run full SFT (1,400 samples, 3 epochs)
- [ ] Log metrics (train loss, eval loss)

### Step 4: GRPO Training (2-3 hours)
- [ ] Write `tinker_grpo_train.py` using `tinker_cookbook.recipes.rl_basic` pattern
- [ ] Implement reward function as Tinker `Env`
- [ ] Run GRPO on SFT checkpoint
- [ ] Log reward progression

### Step 5: Evaluation & Export (1-2 hours)
- [ ] Run evaluation on held-out set
- [ ] Compare baseline vs fine-tuned metrics
- [ ] Export merged model to HF Hub
- [ ] Update TRAINING_REPORT.md with results

---

## 8. Files to Create

| File | Purpose |
|------|---------|
| `ai-engine/mmsd/tinker/convert_data.py` | Convert MMSD → Tinker JSONL format |
| `ai-engine/mmsd/tinker/sft_train.py` | SFT training via Tinker API |
| `ai-engine/mmsd/tinker/grpo_train.py` | GRPO training via Tinker API |
| `ai-engine/mmsd/tinker/reward.py` | Reward functions for GRPO |
| `ai-engine/mmsd/tinker/evaluate.py` | Evaluation on held-out set |
| `ai-engine/mmsd/tinker/TINKER_TRAINING_PLAN.md` | This document |

---

## 9. Success Criteria

| Metric | Baseline (Qwen3-8B) | Target (Fine-tuned) |
|--------|---------------------|---------------------|
| BLEU score | ~5-15 (est.) | >30 |
| JSON validity | ~10-30% (est.) | >70% |
| JS syntax | ~20-40% (est.) | >60% |
| Structural alignment | Low | >0.5 (composite) |
| Reasoning coherence | N/A | Manual 3+/5 avg |

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Qwen3-8B doesn't support Qwen3 renderer | Low | High | Test with small run first |
| SFT causes catastrophic forgetting | Medium | Medium | Include 12% general code mix |
| GRPO reward gaming | Medium | Medium | Multi-component reward, monitor diversity |
| Budget overrun | Low | High | Start with Qwen3-4B if costs are high |
| Data too small (1,400 pairs) | Medium | Medium | SFT should still help; plan data expansion |

---

## 11. Next Steps After Training

1. **Deploy to Ollama** for local inference in PortKit
2. **A/B test** against API-based models (GPT-4o, Claude)
3. **Expand MMSD** with real conversion data from production
4. **Iterate** — the flywheel: more data → better model → better conversions → more data
5. **Consider larger model** (Qwen3-14B or Qwen3-32B) once data grows to 5K+ pairs
