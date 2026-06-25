#!/usr/bin/env python3
"""
PortKit Coder Evaluation Script
Evaluates fine-tuned model vs baseline on the held-out eval split.

Metrics:
1. BLEU score (Bedrock output similarity to ground truth)
2. Exact JSON validity rate (% of manifest.json with required fields)
3. JavaScript syntax check (% of .js output that parses without errors)
4. Reasoning coherence (manual — requires human review of 20 samples)

Usage:
  python evaluate.py --model alexchapin/portkit-coder-7b-merged --eval-data /path/to/eval.jsonl
  python evaluate.py --baseline Qwen/Qwen2.5-Coder-7B-Instruct --eval-data /path/to/eval.jsonl
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from typing import Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ── Prompt Template ────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) "
    "to Bedrock Edition Add-ons. Given a mod description and Java source code, "
    "first reason through the platform mapping, then produce the Bedrock Add-on implementation."
)

EVAL_PROMPT_TEMPLATE = (
    "Mod Description: {instruction}\n\n"
    "Java Source:\n{java_source}\n\n"
    "Convert this to a Bedrock Add-on. First explain your conversion approach, then provide the files."
)


# ── Metric Functions ───────────────────────────────────────────────────────


def compute_bleu(references: list[str], hypotheses: list[str]) -> dict:
    """Compute BLEU score using sacrebleu or nltk."""
    try:
        from sacrebleu.metrics import BLEU

        bleu = BLEU(effective_order=True)
        # sacrebleu expects list of reference lists
        refs = [[r] for r in references]
        result = bleu.corpus_score(hypotheses, refs)
        return {"bleu": result.score, "bleu_details": str(result)}
    except ImportError:
        pass

    # Fallback: NLTK BLEU
    try:
        from nltk.translate.bleu_score import corpus_bleu, SmoothingFunction

        smooth = SmoothingFunction().method1
        refs_tok = [[r.split()] for r in references]
        hyps_tok = [h.split() for h in hypotheses]
        score = corpus_bleu(refs_tok, hyps_tok, smoothing_function=smooth)
        return {"bleu": score * 100, "bleu_details": f"NLTK BLEU (smoothed): {score * 100:.2f}"}
    except ImportError:
        return {"bleu": -1, "bleu_details": "No BLEU library available (install sacrebleu or nltk)"}


def extract_bedrock_output(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract manifest.json and JS code from model output."""
    manifest = None
    js_code = None

    # Try extracting JSON blocks
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    for block in json_blocks:
        if "format_version" in block or "header" in block or "modules" in block:
            manifest = block.strip()
            break

    # Try extracting JS blocks
    js_blocks = re.findall(r"```(?:javascript|js)\s*(.*?)\s*```", text, re.DOTALL)
    if js_blocks:
        # Find the longest JS block (likely the main script)
        js_code = max(js_blocks, key=len).strip()

    # Fallback: look for JSON-like content after "## Bedrock Add-on Output"
    if not manifest:
        bedrock_section = re.search(r"## Bedrock Add-on Output(.*?)(?:##|\Z)", text, re.DOTALL)
        if bedrock_section:
            section = bedrock_section.group(1)
            # Find first { ... } that looks like a manifest
            brace_match = re.search(r'\{[^{}]*"format_version"[^{}]*\}', section, re.DOTALL)
            if brace_match:
                manifest = brace_match.group(0)

    return manifest, js_code


def check_json_validity(manifest_str: Optional[str]) -> dict:
    """Check if extracted manifest is valid JSON with required fields."""
    if manifest_str is None:
        return {"valid": False, "reason": "No manifest extracted"}

    try:
        data = json.loads(manifest_str)
    except json.JSONDecodeError as e:
        return {"valid": False, "reason": f"JSON parse error: {e}"}

    has_version = "format_version" in data
    has_header = "header" in data

    return {
        "valid": has_version and has_header,
        "has_format_version": has_version,
        "has_header": has_header,
        "reason": "OK"
        if (has_version and has_header)
        else f"Missing: {[] if has_version else ['format_version']}{[] if has_header else [' header']}",
    }


def check_js_syntax(js_code: Optional[str]) -> dict:
    """Run node --check on extracted JS code."""
    if js_code is None:
        return {"valid": False, "reason": "No JS code extracted"}

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(js_code)
            f.flush()
            result = subprocess.run(
                ["node", "--check", f.name], capture_output=True, text=True, timeout=10
            )
            os.unlink(f.name)
            if result.returncode == 0:
                return {"valid": True, "reason": "Syntax OK"}
            else:
                return {"valid": False, "reason": result.stderr.strip()}
    except FileNotFoundError:
        return {"valid": None, "reason": "node not available for syntax check"}
    except Exception as e:
        return {"valid": False, "reason": str(e)}


def check_hallucination(js_code: Optional[str]) -> dict:
    """
    Check Bedrock JS for hallucinated API patterns (issue #1678).

    Returns dict with:
      - hallucinated: bool — True if any hallucinated API found
      - apis: list[str] — hallucinated API names found
      - rate: float — hallucination rate (hallucinated / (hallucinated + valid))
    """
    if not js_code:
        return {"hallucinated": False, "apis": [], "rate": 0.0}

    hallucinated_apis: list[str] = []
    valid_apis: list[str] = []

    forbidden_patterns = [
        (r"\bServerPlayerAPI\b", "ServerPlayerAPI"),
        (r"\bServerPlayer\b", "ServerPlayer"),
        (r"\bPlayerAPI\b", "PlayerAPI"),
        (r"\bWorldEvent\b", "WorldEvent"),
        (r"\bmodEventBus\b", "modEventBus"),
        (r"\bBlockEntityAPI\b", "BlockEntityAPI"),
        (r"\bEntityPlayerAPI\b", "EntityPlayerAPI"),
        (r"\bWorldAPI\b", "WorldAPI"),
        (r'require\(["\']@minecraft/server["\']\)', "require(@minecraft/server)"),
        (r"\bregisterMod\(", "registerMod"),
        (r"\bdefineMod\(", "defineMod"),
        (r"\.createLightningBolt\(", "createLightningBolt"),
        (r"\.spawnLightning\(", "spawnLightning"),
        (r"\.registerEvent\(", "registerEvent"),
        (r"\.registerServerEvent\(", "registerServerEvent"),
        (r"\.onServerStart\(", "onServerStart"),
        (r"\.onServerStop\(", "onServerStop"),
        (r"event\.level\.", "event.level"),
        (r"server\.getWorld\(", "server.getWorld"),
        (r"getServer\(\)", "getServer"),
        (r"Server\.getInstance\(\)", "Server.getInstance"),
    ]

    import re
    for pattern_str, name in forbidden_patterns:
        if re.search(pattern_str, js_code, re.IGNORECASE):
            hallucinated_apis.append(name)

    valid_patterns = [
        (r"world\.afterEvents", "world.afterEvents"),
        (r"world\.beforeEvents", "world.beforeEvents"),
        (r"player\.afterEvents", "player.afterEvents"),
        (r"player\.beforeEvents", "player.beforeEvents"),
        (r"system\.run", "system.run"),
        (r"dimension\.spawnEntity", "dimension.spawnEntity"),
        (r"player\.sendMessage", "player.sendMessage"),
        (r"player\.getComponent", "player.getComponent"),
        (r"\.subscribe\(", ".subscribe"),
        (r"world\.getDimension", "world.getDimension"),
        (r"world\.playSound", "world.playSound"),
    ]
    for pattern_str, name in valid_patterns:
        if re.search(pattern_str, js_code):
            valid_apis.append(name)

    total = len(hallucinated_apis) + len(valid_apis)
    rate = len(hallucinated_apis) / max(1, total)

    return {
        "hallucinated": len(hallucinated_apis) > 0,
        "apis": hallucinated_apis,
        "rate": rate,
    }


def compute_perplexity(model, tokenizer, texts: list[str], device: str = "cuda") -> float:
    """Compute perplexity on a set of texts."""
    import math

    model.eval()
    total_loss = 0
    total_tokens = 0

    with torch.no_grad():
        for text in texts:
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=4096)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = model(**inputs, labels=inputs["input_ids"])
            total_loss += outputs.loss.item() * inputs["input_ids"].size(1)
            total_tokens += inputs["input_ids"].size(1)

    avg_loss = total_loss / total_tokens if total_tokens > 0 else float("inf")
    return math.exp(avg_loss)


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Evaluate PortKit Coder model")
    parser.add_argument("--model", type=str, help="Model ID or path (merged model)")
    parser.add_argument("--lora-adapter", type=str, help="LoRA adapter path (if not merged)")
    parser.add_argument(
        "--baseline",
        type=str,
        default="Qwen/Qwen2.5-Coder-7B-Instruct",
        help="Baseline model for comparison",
    )
    parser.add_argument(
        "--eval-data",
        type=str,
        default="ai-engine/mmsd/data/processed/validated_pairs.jsonl",
        help="Path to validated pairs JSONL",
    )
    parser.add_argument(
        "--eval-split",
        type=float,
        default=0.1,
        help="Fraction of data to use as eval (from the end)",
    )
    parser.add_argument(
        "--max-samples", type=int, default=0, help="Max samples to evaluate (0 = all eval samples)"
    )
    parser.add_argument(
        "--output", type=str, default="evaluation_results.json", help="Output file for results"
    )
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    print("=" * 60)
    print("PortKit Coder Evaluation")
    print("=" * 60)

    # Load eval data
    pairs = []
    with open(args.eval_data) as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))

    # Use last 10% as eval (matching training split)
    split_idx = int(len(pairs) * (1 - args.eval_split))
    eval_pairs = pairs[split_idx:]
    if args.max_samples > 0:
        eval_pairs = eval_pairs[: args.max_samples]

    print(f"Eval samples: {len(eval_pairs)} (from {len(pairs)} total)")

    # Load model
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    results = {}

    for model_label, model_id, lora_path in [
        ("baseline", args.baseline, None),
        ("finetuned", args.model, args.lora_adapter),
    ]:
        if model_id is None:
            continue

        print(f"\n{'=' * 40}")
        print(f"Evaluating: {model_label} ({model_id})")
        print(f"{'=' * 40}")

        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            device_map=device if device != "cpu" else None,
        )

        if lora_path:
            model = PeftModel.from_pretrained(model, lora_path)
            model = model.merge_and_unload()

        model.eval()

        # Generate outputs
        predictions = []
        references = []
        json_valid_count = 0
        js_valid_count = 0
        js_check_available = True
        generation_times = []
        hallucinated_samples = 0
        total_hallucination_rate = 0.0

        for i, pair in enumerate(eval_pairs):
            prompt = EVAL_PROMPT_TEMPLATE.format(
                instruction=pair["instruction"],
                java_source=pair["java_source"],
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=3584)
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

            t0 = time.time()
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=2048,
                    temperature=0.1,
                    do_sample=True,
                    pad_token_id=tokenizer.pad_token_id,
                )
            gen_time = time.time() - t0
            generation_times.append(gen_time)

            generated = tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
            )
            predictions.append(generated)
            references.append(pair["bedrock_source"])

            # Check JSON validity
            manifest, js_code = extract_bedrock_output(generated)
            json_result = check_json_validity(manifest)
            if json_result["valid"]:
                json_valid_count += 1

            # Check JS syntax
            if js_check_available:
                js_result = check_js_syntax(js_code)
                if js_result["valid"] is None:
                    js_check_available = False
                elif js_result["valid"]:
                    js_valid_count += 1

            # Check hallucination (issue #1678)
            halluc_result = check_hallucination(js_code)
            if halluc_result["hallucinated"]:
                hallucinated_samples += 1
            total_hallucination_rate += halluc_result["rate"]

            if (i + 1) % 10 == 0:
                avg_halluc_rate = total_hallucination_rate / (i + 1)
                print(
                    f"  [{i + 1}/{len(eval_pairs)}] "
                    f"JSON valid: {json_valid_count}/{i + 1}, "
                    f"JS valid: {js_valid_count}/{i + 1}, "
                    f"Hallucination rate: {avg_halluc_rate:.1%} "
                    f"Avg time: {sum(generation_times) / len(generation_times):.1f}s"
                )

        # Compute BLEU
        bleu_results = compute_bleu(references, predictions)

        # Compute perplexity on ground truth
        try:
            ppl = compute_perplexity(model, tokenizer, references[:20], device)
            ppl_str = f"{ppl:.2f}"
        except Exception as e:
            ppl_str = f"Error: {e}"

        model_results = {
            "model_id": model_id,
            "num_samples": len(eval_pairs),
            "bleu": bleu_results["bleu"],
            "bleu_details": bleu_results["bleu_details"],
            "json_valid_pct": 100 * json_valid_count / len(eval_pairs) if eval_pairs else 0,
            "json_valid_count": json_valid_count,
            "js_valid_pct": 100 * js_valid_count / len(eval_pairs) if eval_pairs else 0,
            "js_valid_count": js_valid_count,
            "perplexity": ppl_str,
            "avg_generation_time_s": sum(generation_times) / len(generation_times)
            if generation_times
            else 0,
            # Hallucination metrics (issue #1678)
            "hallucination_rate": total_hallucination_rate / len(eval_pairs) if eval_pairs else 0.0,
            "hallucination_pct": 100 * hallucinated_samples / len(eval_pairs) if eval_pairs else 0.0,
            "hallucinated_samples": hallucinated_samples,
        }
        results[model_label] = model_results

        print(f"\n  Results for {model_label}:")
        for k, v in model_results.items():
            print(f"    {k}: {v}")

        # Clean up
        del model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {args.output}")

    # Print comparison table
    if len(results) > 1:
        print("\n" + "=" * 60)
        print("COMPARISON TABLE")
        print("=" * 60)
        print(f"{'Metric':<25} {'Baseline':>15} {'Fine-tuned':>15}")
        print("-" * 60)
        for metric in ["bleu", "json_valid_pct", "js_valid_pct", "hallucination_rate", "perplexity"]:
            baseline_val = results.get("baseline", {}).get(metric, "N/A")
            ft_val = results.get("finetuned", {}).get(metric, "N/A")
            if metric == "hallucination_rate":
                baseline_val = f"{baseline_val:.1%}" if isinstance(baseline_val, float) else baseline_val
                ft_val = f"{ft_val:.1%}" if isinstance(ft_val, float) else ft_val
            print(f"{metric:<25} {str(baseline_val):>15} {str(ft_val):>15}")


if __name__ == "__main__":
    main()
