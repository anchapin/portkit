#!/usr/bin/env python3
"""
PortKit Coder Fine-Tuning — Stage A (Reasoning + Code Generation)
Fine-tunes Qwen2.5-Coder-7B-Instruct with QLoRA on MMSD synthesis pairs,
mixed with general Java/JS code data (12% ratio) to mitigate catastrophic forgetting.

Data pipeline:
1. git clone portkit repo (sparse) + git lfs pull for synthesis_pairs.jsonl
2. Run structural validation → validated_pairs.jsonl
3. Download and sample general Java/JS code pairs from HuggingFace (~200 examples)
4. Format as ChatML conversations (system + user + assistant)
5. Mix datasets: ~12% general / ~88% MMSD by token count
6. 90/10 train/eval split (no shuffle, deterministic)
7. QLoRA fine-tuning with SFTTrainer
8. Push LoRA adapter + merged model to HF Hub

Adaption Lab Integration (Issue #1677):
- Adaption lab datasets at ai-engine/mmsd/data/processed/adaption_*.jsonl
- Validated adaption data is merged into adaption_lab_merged.jsonl
- Include via --include-adaption flag or INCLUDE_ADAPTION=1 env var
"""

import os
import json
import subprocess
import re
import shutil
import torch
import gc
from pathlib import Path
from typing import Tuple

from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, TaskType
from trl import SFTTrainer, SFTConfig

try:
    from mmsd.adaption_data_loader import AdaptionDatasetLoader, load_training_data
except ImportError:
    AdaptionDatasetLoader = None
    load_training_data = None

# ── Config ─────────────────────────────────────────────────────────────────

MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"
LORA_REPO = "alexchapin/portkit-coder-7b-lora"
MERGED_REPO = "alexchapin/portkit-coder-7b-merged"

TRACKIO_PROJECT = os.environ.get("TRACKIO_PROJECT", "portkit-sft")
TRACKIO_SPACE_ID = os.environ.get("TRACKIO_SPACE_ID", "")

# QLoRA
LORA_R = 64
LORA_ALPHA = 128
LORA_DROPOUT = 0.1
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

# Training
MAX_LENGTH = 4096
NUM_EPOCHS = 3
BATCH_SIZE = 2
GRAD_ACCUM = 8
LR = 2e-4
WARMUP = 0.05
SCHEDULER = "cosine"
SEED = 42
TRAIN_RATIO = 0.9

# Catastrophic forgetting mitigation: general code mix
GENERAL_CODE_DATASET = "m-a-p/CodeFeedback-Filtered-Instruction"
GENERAL_CODE_LANGUAGES = ["java", "javascript"]
GENERAL_CODE_SAMPLE_SIZE = 200
MIX_RATIO = 0.12  # ~12% of training tokens from general code

# Adaption lab integration (Issue #1677)
INCLUDE_ADAPTION = os.environ.get("INCLUDE_ADAPTION", "0") == "1"
ADAPTION_DATA_DIR = "ai-engine/mmsd/data/processed"
ADAPTION_WEIGHT = float(os.environ.get("ADAPTION_WEIGHT", "1.0"))

SYSTEM_PROMPT = (
    "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) "
    "to Bedrock Edition Add-ons. Given a mod description and Java source code, "
    "first reason through the platform mapping, then produce the Bedrock Add-on implementation.\n\n"
    "IMPORTANT: Target Bedrock Scripting API version 2.x (@minecraft/server ^2.0.0) for all scripting output.\n"
    "- manifest.json must use format_version 2 with min_engine_version [1, 21, 0]\n"
    "- All scripting imports must use @minecraft/server and @minecraft/server-ui only\n"
    "- Do NOT mix API 1.x and 2.x patterns in the same output"
)


# ── Data ───────────────────────────────────────────────────────────────────


def clone_and_validate() -> str:
    """Clone portkit repo, run validation, return path to validated_pairs.jsonl."""
    work = Path("/tmp/portkit_train")
    work.mkdir(exist_ok=True)
    validated = work / "validated_pairs.jsonl"

    if validated.exists() and validated.stat().st_size > 1000:
        print(f"[data] Using cached {validated}")
        return str(validated)

    repo = work / "portkit"
    if not repo.exists():
        print("[data] Cloning portkit repo (sparse + LFS)...")
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--sparse",
                "https://github.com/anchapin/portkit.git",
                str(repo),
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "sparse-checkout",
                "set",
                "ai-engine/mmsd/synthesis_pairs.jsonl",
                "ai-engine/mmsd/validators/",
                "ai-engine/mmsd/run_validation.py",
                "ai-engine/mmsd/__init__.py",
                "ai-engine/__init__.py",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "lfs",
                "pull",
                "--include=ai-engine/mmsd/synthesis_pairs.jsonl",
            ],
            check=False,
        )

    raw = repo / "ai-engine/mmsd/synthesis_pairs.jsonl"
    assert raw.exists() and raw.stat().st_size > 100_000, (
        f"Bad data file: {raw.stat().st_size if raw.exists() else 0} bytes"
    )

    # Prepare processed dir
    proc_dir = repo / "ai-engine/mmsd/data/processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(raw), str(proc_dir / "synthesis_pairs.jsonl"))

    # Run validation
    print("[data] Running validation...")
    _run_validation(str(proc_dir / "synthesis_pairs.jsonl"), str(validated))

    if not validated.exists() or validated.stat().st_size < 1000:
        print("[data] Validation output empty, falling back to raw data")
        shutil.copy2(str(raw), str(validated))

    print(f"[data] {validated.stat().st_size / 1e6:.1f} MB ready")
    return str(validated)


def _has_error_fields(entry: dict) -> bool:
    for field in ["reasoning_trace", "java_source", "bedrock_source"]:
        val = entry.get(field, "")
        if isinstance(val, str) and (val.startswith("Error:") or val.startswith("ERROR_PREFIX")):
            return True
    return False


def _validate_java(source: str) -> Tuple[bool, str]:
    code = re.sub(r"```java(.*?)```", r"\1", source, flags=re.DOTALL).strip()
    if not code:
        code = source
    checks = {
        "package": r"package [\w.]+;",
        "class": r"public class \w+",
        "imports": r"import [\w.*]+;",
        "braces": r"\{.*?\}",
    }
    for name, pat in checks.items():
        if not re.search(pat, code, re.DOTALL):
            return False, f"Missing {name}"
    return True, "OK"


def _validate_bedrock(source: str) -> Tuple[bool, str]:
    blocks = re.findall(r"```json(.*?)```", source, re.DOTALL)
    if not blocks and "format_version" not in source:
        return False, "No JSON blocks"
    for block in blocks:
        clean = re.sub(r"//.*", "", block)
        try:
            json.loads(clean)
        except json.JSONDecodeError:
            return False, "Invalid JSON"
    return True, "OK"


def _run_validation(input_path: str, output_path: str):
    valid = 0
    total = 0
    with open(input_path) as inf, open(output_path, "w") as outf:
        for line in inf:
            total += 1
            try:
                entry = json.loads(line)
                if _has_error_fields(entry):
                    continue
                j_ok, _ = _validate_java(entry["java_source"])
                b_ok, _ = _validate_bedrock(entry["bedrock_source"])
                if j_ok and b_ok:
                    outf.write(json.dumps(entry) + "\n")
                    valid += 1
            except Exception:
                pass
    print(f"[data] Validated: {valid}/{total}")


def format_stage_a(example: dict) -> dict:
    instruction = example.get("instruction", example.get("description", ""))
    java_source = example.get("java_source", example.get("source", ""))
    reasoning_trace = example.get("reasoning_trace", example.get("reasoning", ""))
    bedrock_source = example.get("bedrock_source", example.get("target", ""))

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Mod Description: {instruction}\n\n"
                    f"Java Source:\n{java_source}\n\n"
                    "Convert this to a Bedrock Add-on. First explain your conversion approach, then provide the files."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    f"## Conversion Plan\n{reasoning_trace}\n\n"
                    f"## Bedrock Add-on Output\n{bedrock_source}"
                ),
            },
        ]
    }


GENERAL_SYSTEM_PROMPT = (
    "You are a general-purpose code assistant. Provide clear, correct code solutions "
    "with concise explanations when helpful."
)


def format_general_code(example: dict) -> dict:
    instruction = example.get("instruction", example.get("input", ""))
    response = example.get("output", example.get("response", ""))

    if not instruction or not response:
        return None

    return {
        "messages": [
            {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Write code for: {instruction}",
            },
            {
                "role": "assistant",
                "content": response,
            },
        ]
    }


def load_general_code_dataset() -> list:
    """Download and sample general Java/JS code pairs for catastrophic forgetting mitigation."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("[general] datasets not installed, skipping general code mix")
        return []

    cache_dir = Path("/tmp/portkit_general_code")
    cache_dir.mkdir(exist_ok=True)

    sample_file = cache_dir / "general_code_sample.jsonl"
    if sample_file.exists() and sample_file.stat().st_size > 1000:
        print(f"[general] Using cached sample from {sample_file}")
        examples = []
        with open(sample_file) as f:
            for line in f:
                if line.strip():
                    examples.append(json.loads(line))
        return examples

    print(f"[general] Loading {GENERAL_CODE_DATASET}...")
    try:
        dataset = load_dataset(
            GENERAL_CODE_DATASET,
            split="train",
            trust_remote_code=True,
            cache_dir=str(cache_dir),
        )
    except Exception as e:
        print(f"[general] Failed to load dataset: {e}")
        return []

    lang_field = None
    for candidate in ["lang", "language", " Programming_Language"]:
        if candidate in dataset.column_names:
            lang_field = candidate
            break

    if lang_field is None:
        print(f"[general] No language column found. Columns: {dataset.column_names}")
        return []

    print(f"[general] Filtering to {GENERAL_CODE_LANGUAGES}...")
    filtered = dataset.filter(lambda x: x.get(lang_field) in GENERAL_CODE_LANGUAGES)

    if len(filtered) == 0:
        print("[general] No examples found after filtering, skipping mix")
        return []

    sample_size = min(GENERAL_CODE_SAMPLE_SIZE, len(filtered))
    print(f"[general] Sampling {sample_size} examples from {len(filtered)} filtered")

    try:
        sampled = filtered.shuffle(seed=SEED).select(range(sample_size))
    except Exception as e:
        print(f"[general] Shuffle/select failed: {e}")
        sampled = filtered.select(range(min(sample_size, len(filtered))))

    examples = []
    for item in sampled:
        formatted = format_general_code(item)
        if formatted is not None:
            examples.append(formatted)

    with open(sample_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"[general] Saved {len(examples)} formatted examples")
    return examples


def count_tokens(messages: list, tokenizer) -> int:
    """Rough token count for a messages list using the tokenizer."""
    text = ""
    for msg in messages:
        text += msg["role"] + ": " + msg["content"] + "\n"
    return len(tokenizer.encode(text))


def mix_datasets(
    mmsd_examples: list, general_examples: list, target_ratio: float = MIX_RATIO
) -> list:
    """Mix MMSD and general code examples to achieve target token ratio (~12%)."""
    if not general_examples:
        return mmsd_examples

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    mmsd_tokens = sum(count_tokens(ex["messages"], tokenizer) for ex in mmsd_examples)
    general_tokens = sum(count_tokens(ex["messages"], tokenizer) for ex in general_examples)

    print(f"[mix] MMSD tokens: {mmsd_tokens:,}, General tokens: {general_tokens:,}")

    target_general_tokens = int(mmsd_tokens * target_ratio / (1 - target_ratio))
    general_count = general_examples
    current_general_tokens = general_tokens

    if current_general_tokens > target_general_tokens:
        scale = target_general_tokens / current_general_tokens
        n = max(1, int(len(general_examples) * scale))
        general_count = general_examples[:n]
        current_general_tokens = sum(
            count_tokens(ex["messages"], tokenizer) for ex in general_count
        )
        print(f"[mix] Scaled general sample to {len(general_count)} examples to hit target ratio")

    actual_ratio = current_general_tokens / (mmsd_tokens + current_general_tokens)
    print(f"[mix] Target ratio: {target_ratio:.1%}, Actual ratio: {actual_ratio:.1%}")

    mixed = mmsd_examples + general_count
    import random

    random.seed(SEED)
    random.shuffle(mixed)
    return mixed


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("PortKit Coder SFT — Stage A")
    print(f"Model: {MODEL_ID}")
    print(f"LoRA: r={LORA_R}, α={LORA_ALPHA}")
    print(f"Effective batch: {BATCH_SIZE * GRAD_ACCUM}, LR: {LR}")
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(
            f"GPU: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB"
        )
    print("=" * 60)

    # ── Data ────────────────────────────────────────────────────────────────
    data_path = clone_and_validate()
    pairs = []
    with open(data_path) as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))

    adaption_pairs = []
    if INCLUDE_ADAPTION and load_training_data is not None:
        _, adaption_pairs, data_stats = load_training_data(
            mmsd_path=data_path,
            adaption_data_dir=ADAPTION_DATA_DIR,
            include_adaption=True,
            adaption_weight=ADAPTION_WEIGHT,
        )
        print(f"[adaption] Loaded {len(adaption_pairs)} adaption pairs")
        print(f"[adaption] Stats: {data_stats}")

    n = len(pairs) + len(adaption_pairs)
    split = int(len(pairs) * TRAIN_RATIO)
    mmsd_train = [format_stage_a(p) for p in pairs[:split]]
    eval_ds = Dataset.from_list([format_stage_a(p) for p in pairs[split:]])

    if adaption_pairs:
        adaption_train = [format_stage_a(p) for p in adaption_pairs]
        mmsd_train.extend(adaption_train)
        print(f"[adaption] Extended training set with {len(adaption_pairs)} adaption pairs")

    general_examples = load_general_code_dataset()
    if general_examples:
        mixed_train = mix_datasets(mmsd_train, general_examples, target_ratio=MIX_RATIO)
        train_ds = Dataset.from_list(mixed_train)
        print(
            f"Data: {n} total → {len(train_ds)} train (mixed, {len(general_examples)} general), {len(eval_ds)} eval"
        )
    else:
        train_ds = Dataset.from_list(mmsd_train)
        print(f"Data: {n} total → {len(train_ds)} train, {len(eval_ds)} eval")

    # ── Model ───────────────────────────────────────────────────────────────
    print("\nLoading model...")
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb,
        torch_dtype=torch.bfloat16,
        use_cache=False,
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    peft_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES,
        task_type=TaskType.CAUSAL_LM,
        bias="none",
    )

    # ── Train ───────────────────────────────────────────────────────────────
    report_to = "trackio" if TRACKIO_SPACE_ID else "none"
    args = SFTConfig(
        output_dir="./portkit-lora",
        max_length=MAX_LENGTH,
        packing=False,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LR,
        warmup_ratio=WARMUP,
        lr_scheduler_type=SCHEDULER,
        optim="paged_adamw_8bit",
        seed=SEED,
        gradient_checkpointing=True,
        bf16=True,
        logging_strategy="steps",
        logging_steps=10,
        logging_first_step=True,
        disable_tqdm=True,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=3,
        push_to_hub=True,
        hub_model_id=LORA_REPO,
        hub_private_repo=True,
        run_name=f"portkit-sft-stageA-lr{LR}-bs{BATCH_SIZE * GRAD_ACCUM}",
        report_to=report_to,
    )

    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    print("\n▶ Training...")
    result = trainer.train()
    train_metrics = result.metrics
    print(f"✓ Train loss: {train_metrics.get('train_loss', 'N/A'):.4f}")
    print(f"  Runtime: {train_metrics.get('train_runtime', 'N/A'):.0f}s")

    print("\n▶ Evaluation...")
    eval_metrics = trainer.evaluate()
    for k, v in eval_metrics.items():
        print(f"  {k}: {v}")

    # ── Save & Push LoRA ────────────────────────────────────────────────────
    trainer.save_model("./portkit-lora/final")
    try:
        trainer.push_to_hub()
        print(f"✓ LoRA pushed to {LORA_REPO}")
    except Exception as e:
        print(f"✗ LoRA push failed: {e}")

    # ── Merge & Push ────────────────────────────────────────────────────────
    print("\n▶ Merging & pushing...")
    try:
        from peft import AutoPeftModelForCausalLM

        del model, trainer
        gc.collect()
        torch.cuda.empty_cache()

        merged = AutoPeftModelForCausalLM.from_pretrained(
            "./portkit-lora/final",
            torch_dtype=torch.bfloat16,
            device_map="auto",
        ).merge_and_unload()

        merged.push_to_hub(MERGED_REPO, private=True, safe_serialization=True)
        tokenizer.push_to_hub(MERGED_REPO, private=True)
        print(f"✓ Merged model pushed to {MERGED_REPO}")
    except Exception as e:
        print(f"✗ Merge/push failed: {e}")

    # ── Summary ─────────────────────────────────────────────────────────────
    summary = {
        "model_id": MODEL_ID,
        "lora": {
            "r": LORA_R,
            "alpha": LORA_ALPHA,
            "dropout": LORA_DROPOUT,
            "target_modules": TARGET_MODULES,
        },
        "training": {
            "epochs": NUM_EPOCHS,
            "batch_size": BATCH_SIZE,
            "grad_accum": GRAD_ACCUM,
            "effective_bs": BATCH_SIZE * GRAD_ACCUM,
            "lr": LR,
            "max_length": MAX_LENGTH,
            "warmup": WARMUP,
            "scheduler": SCHEDULER,
        },
        "data": {
            "total": n,
            "train": len(train_ds),
            "eval": len(eval_ds),
            "mmsd_pairs": len(pairs),
            "adaption_pairs": len(adaption_pairs),
            "adaption_weight": ADAPTION_WEIGHT if INCLUDE_ADAPTION else None,
            "general_code_mix": {
                "dataset": GENERAL_CODE_DATASET,
                "sample_size": GENERAL_CODE_SAMPLE_SIZE,
                "target_ratio": MIX_RATIO,
                "languages": GENERAL_CODE_LANGUAGES,
            },
        },
        "results": {
            "train_loss": train_metrics.get("train_loss"),
            "eval_loss": eval_metrics.get("eval_loss"),
            "train_runtime_s": train_metrics.get("train_runtime"),
        },
        "repos": {"lora": LORA_REPO, "merged": MERGED_REPO},
    }
    with open("./training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n✓ Summary: {json.dumps(summary['results'], indent=2)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
