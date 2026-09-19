r"""
Multisage Augmentation CLI
==========================

Usage:
    python -m ai_engine.conversion.multisage_augmentation \\
        --input samples.json \\
        --output augmented.json \\
        --n-variants 3

Input format (JSON, JSONL, or newline-separated Java files):
  JSON:  [{"java": "public class Foo { ... }", "bedrock": "..."}, ...]
  JSONL: {"java": "..."}\n{"java": "..."}
  .java: raw Java source files

Output: JSON array of augmented samples with multisage metadata.

Author: PortKit AI Engine
Issue: #1738
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from conversion.multisage_augmentation import MultisageAugmenter

DEFAULT_MODEL = "qwen2.5-coder:3b"
DEFAULT_API_BASE = "http://localhost:8002/v1"
DEFAULT_N_VARIANTS = 3


def load_samples(input_path: str) -> list[dict]:
    """Load samples from JSON, JSONL, or a directory of .java files."""
    path = Path(input_path)

    if path.is_dir():
        samples = []
        for java_file in sorted(path.glob("*.java")):
            content = java_file.read_text(encoding="utf-8")
            samples.append({"java": content, "source_file": str(java_file)})
        if not samples:
            raise ValueError(f"No .java files found in directory: {input_path}")
        return samples

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Empty input file: {input_path}")

    if text.startswith("["):
        return json.loads(text)
    else:
        samples = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                samples.append({"java": line})
        return samples


def save_results(results: list[dict], output_path: str) -> None:
    """Save augmented results to JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def run(
    input_path: str,
    output_path: str,
    n_variants: int = DEFAULT_N_VARIANTS,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_API_BASE,
    verify: bool = True,
) -> None:
    """Load samples, augment them, and save results."""
    print(f"[multisage] Loading samples from: {input_path}")
    samples = load_samples(input_path)
    print(f"[multisage] Loaded {len(samples)} samples")

    augmenter = MultisageAugmenter(
        model=model,
        api_base=api_base,
        verify_equivalence=verify,
    )

    def progress(completed: int, total: int, msg: str) -> None:
        pct = completed / total * 100
        print(f"[multisage] [{completed}/{total}] {pct:.0f}% — {msg}")

    t0 = time.time()
    results = augmenter.augment_dataset(
        samples,
        n_variants=n_variants,
        progress_callback=progress,
    )
    elapsed = time.time() - t0

    n_original = sum(1 for r in results if r.get("is_original"))
    n_variants_out = len(results) - n_original

    print(f"[multisage] Done in {elapsed:.1f}s")
    print(
        f"[multisage] Output: {len(results)} total entries ({n_original} original + {n_variants_out} variants)"
    )

    save_results(results, output_path)
    print(f"[multisage] Saved to: {output_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ai_engine.conversion.multisage_augmentation",
        description="Multisage multi-semantic augmentation for Java→Bedrock conversion training data.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input: JSON file, JSONL file, or directory of .java files",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--n-variants",
        "-n",
        type=int,
        default=DEFAULT_N_VARIANTS,
        help=f"Number of variants per sample (default: {DEFAULT_N_VARIANTS})",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=DEFAULT_MODEL,
        help=f"LLM model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"LLM API base URL (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        default=True,
        help="Skip LLM-based equivalence verification (faster, lower quality)",
    )

    args = parser.parse_args(argv)

    try:
        run(
            input_path=args.input,
            output_path=args.output,
            n_variants=args.n_variants,
            model=args.model,
            api_base=args.api_base,
            verify=args.verify,
        )
        return 0
    except Exception as e:
        print(f"[multisage] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
