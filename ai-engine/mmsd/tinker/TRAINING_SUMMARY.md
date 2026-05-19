# PortKit Model Training Summary

## Models Trained

| Model | Training Method | Steps | Group Size | LR | Final Reward | Published |
|-------|---------------|-------|------------|-----|--------------|-----------|
| **SFT v1** | Supervised Fine-tuning | 200 | - | 2e-5 | NLL 0.334 (eval) | ✅ alexchapin/portkit-coder-8b-sft1 |
| **GRPO6** | Group REINFORCE + SFT init | 200 | 8 | 5e-5 | 0.6177 | ✅ alexchapin/portkit-coder-8b-grpo6 |
| **GRPO7** | Self-reflection RL | 100 | 12 | 1e-6 | 0.6172 | ⚠️ Pending export |
| **GRPO8** | Anti-hallucination focus | Planned | 10 | 1e-6 | - | ⏳ Pending |

## Training Details

### GRPO6 (Completed)
- **Checkpoints**: `tinker://aae0b5aa-f324-5e4d-9105-3c2eab183f90:train:0/sampler_weights/final`
- **Log path**: `/home/alex/Projects/portkit/ai-engine/mmsd/tinker/logs/grpo6_sft1_Qwen_Qwen3-8B_20260518_093216/`
- **Method**: Started from SFT v1 checkpoint, 200 steps with group_size=8
- **Reward components**: manifest_structure, js_api_correctness, code_bleu, content_density, length_ratio

### GRPO7 (Completed)
- **Checkpoints**: `tinker://a9902a9f-027d-5c29-947a-635beeb5e37b:train:0/sampler_weights/final`
- **Log path**: `/home/alex/Projects/portkit/ai-engine/mmsd/tinker/logs/grpo7_self_reflect_Qwen_Qwen3-8B_20260518_163529/`
- **Method**: Self-reflection rewards inspired by ReflexiC, 100 steps with group_size=12
- **Additional rewards**: self_reflection (correction patterns), structure_building, js_syntax
- **Key insight**: Lower LR (1e-6) for stability; slightly better JS API correctness (72.7% vs 72.5%)
- **Export status**: ✅ Downloaded to `exports/grpo7_local`, merged to `exports/grpo7_merged`
  - ⚠️ HF token lacks write permissions for model upload (fine-grained token for inference only)
  - Local weights available at: `/home/alex/Projects/portkit/ai-engine/mmsd/tinker/exports/grpo7_merged/`

### GRPO8 (Planned)
- **Script**: `/home/alex/Projects/portkit/ai-engine/mmsd/tinker/grpo8_train.py`
- **Method**: Anti-hallucination focus with stronger API validation
- **New components**: count_hallucinated_apis, score_real_api_usage, score_concise_output
- **Lower temperature**: 0.5 (vs 0.9) for more precise output

## Evaluation Results

### Training Metrics (GRPO7 final steps)
```
Step 90-99: avg_reward ~0.67, max_reward ~0.82
Components:
  - manifest_completeness: ~1.00 (excellent)
  - structure_building: ~0.70 (good)
  - api_correctness: ~0.73 (decent)
  - js_syntax: ~0.60 (needs improvement)
  - self_reflection: ~0.08 (minimal impact)
```

### Reference Analysis (Local Evaluation)
- Average reference reward: 0.54
- Hallucination rate: ~30% of samples contain hallucinated APIs
- Common issues: ServerPlayerAPI, require('@minecraft/server'), getServer()

## Key Files

```
ai-engine/mmsd/tinker/
├── grpo6_train.py      # GRPO6 training script
├── grpo7_train.py      # GRPO7 with self-reflection
├── grpo8_train.py      # GRPO8 anti-hallucination (new)
├── reward_v2.py         # Reward functions
├── evaluate_v2.py       # Full evaluation (requires Tinker)
├── evaluate_local.py   # Static analysis (local)
├── export_grpo6.py     # Export GRPO6 to Hub
├── export_grpo7.py     # Export GRPO7 to Hub (new)
└── logs/
    ├── grpo6_sft1_Qwen_Qwen3-8B_20260518_093216/
    └── grpo7_self_reflect_Qwen_Qwen3-8B_20260518_163529/
```

## What's Needed

### 1. Export GRPO7 (Blocked by HF credits)
```bash
cd /home/alex/Projects/portkit/ai-engine/mmsd/tinker
python export_grpo7.py --push-merged
```
- Requires Tinker SDK and HF credits
- Check budget: https://huggingface.co/settings/billing

### 2. Continue GRPO8 Training (Blocked by HF credits)
```bash
cd /home/alex/Projects/portkit/ai-engine/mmsd/tinker
python grpo8_train.py \
    --checkpoint-path tinker://a9902a9f-027d-5c29-947a-635beeb5e37b:train:0/weights/final \
    --max-steps 120 \
    --group-size 10
```
- Focus: Anti-hallucination, concise output, real API usage
- Est. cost: ~$15 for 120 steps

### 3. Full Evaluation (Requires Tinker access)
```bash
cd /home/alex/Projects/portkit/ai-engine/mmsd/tinker
python evaluate_v2.py --compare --max-samples 50
```

## Key Insights from Research

1. **Group-relative advantages** reduce variance but may cause difficulty bias (Dr. GRPO paper: use `scale_rewards=False`)

2. **Self-reflection rewards** (ReflexiCoder) showed +14-16% improvement in code generation tasks

3. **vLLM acceleration** can dramatically speed up GRPO by separating generation from training

4. **PEFT + GRPO** works well: LoRA r=32, alpha=16, lr=1e-5

5. **Concise output** scoring helps: optimal ratio 0.7-1.2x reference length

## Hallucinated APIs to Avoid

Hard hallucinations (NEVER valid in Bedrock):
- ServerPlayerAPI, ServerPlayer, PlayerAPI
- WorldEvent, BlockEntityAPI, EntityPlayerAPI, WorldAPI
- require('@minecraft/server')
- registerMod(), getServer(), Server.getInstance()
- event.level, server.getWorld

Real Bedrock APIs (ALWAYS valid):
- world.afterEvents, world.beforeEvents
- system.runInterval, system.runTimeout
- player.sendMessage, player.getComponent
- { world, system, player } imports from @minecraft/server

## Budget Status

- **HuggingFace Jobs**: Credits exhausted (~$0 remaining)
- **Tinker Platform**: ~$88 remaining (estimated from recent runs)
- **Total spent so far**: ~$30-40

## Next Steps

1. ✅ Research GRPO improvements → Completed
2. ✅ Download GRPO7 adapter weights → Completed (local: `exports/grpo7_local`)
3. ✅ Merge GRPO7 with base model → Completed (local: `exports/grpo7_merged`)
4. ⚠️ Export GRPO7 to Hub → Blocked by fine-grained HF token (needs repo.content.write)
5. ⏳ Run GRPO8 training → Ready when budget confirmed
6. ⏳ Full evaluation → Pending GRPO8 training