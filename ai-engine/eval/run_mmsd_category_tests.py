#!/usr/bin/env python3
r"""
run_mmsd_category_tests — CLI runner for MMSD category-specific functional tests
================================================================================

Usage:
    python -m ai_engine.eval.run_mmsd_category_tests --dataset-path ai-engine/mmsd/data/processed/synthesis_pairs.jsonl --output report.json

Outputs:
  - report.json: Category-level pass/fail counts + per-pair error summaries
  - Exit code 0 if all categories pass, 1 if any failures
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ai_root = Path(__file__).parent.parent
sys.path.insert(0, str(ai_root))

from eval.mmsd_category_tests import (
    CATEGORIES,
    DATASET_PATH,
    load_mmsd_pairs,
    validate_pair_category,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run MMSD category-specific functional tests and produce a report.",
    )
    parser.add_argument(
        "--dataset-path",
        type=str,
        default=DATASET_PATH,
        help="Path to MMSD synthesis_pairs.jsonl file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="mmsd_category_report.json",
        help="Output report path (JSON)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-pair pass/fail details"
    )
    parser.add_argument(
        "--pairs-limit",
        type=int,
        default=0,
        help="Limit number of pairs tested per category (0 = all)",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading dataset from: {dataset_path}")
    pairs = load_mmsd_pairs(str(dataset_path))
    print(f"Loaded {len(pairs)} pairs")

    # Count by category
    cat_counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
    cat_counts["other"] = 0
    for pair in pairs:
        for cat in pair.categories:
            if cat in cat_counts:
                cat_counts[cat] += 1

    print("\nPairs per category:")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        if n > 0:
            print(f"  {cat}: {n}")

    # Run validation
    print("\nRunning category validation...")
    all_passed = True
    results = {}

    for cat_name in sorted(CATEGORIES.keys()):
        count = cat_counts.get(cat_name, 0)
        if count == 0:
            continue

        cat_pairs = [p for p in pairs if cat_name in p.categories]
        if args.pairs_limit > 0:
            cat_pairs = cat_pairs[: args.pairs_limit]

        passed = 0
        failed = 0
        errors = []

        for pair in cat_pairs:
            try:
                ok, msg = validate_pair_category(pair, cat_name)
                if ok:
                    passed += 1
                    if args.verbose:
                        print(f"  PASS [{cat_name}] pair {pair.idx}: {msg[:80]}")
                else:
                    failed += 1
                    all_passed = False
                    err = f"Pair {pair.idx}: {msg}"
                    errors.append(err)
                    if args.verbose:
                        print(f"  FAIL [{cat_name}] {err}")

            except Exception as e:
                failed += 1
                all_passed = False
                errors.append(f"Pair {pair.idx} EXCEPTION: {e}")

        pass_rate = round(passed / len(cat_pairs), 3) if cat_pairs else 0.0
        results[cat_name] = {
            "total": len(cat_pairs),
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "errors": errors[:10],
        }

        status = "PASS" if failed == 0 else "FAIL"
        print(f"  [{status}] {cat_name}: {passed}/{len(cat_pairs)} passed ({pass_rate:.1%})")

    # Write report
    report = {
        "dataset_path": str(dataset_path),
        "total_pairs": len(pairs),
        "pairs_per_category": cat_counts,
        "category_results": results,
        "overall_passed": all_passed,
    }

    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to: {output_path}")

    if all_passed:
        print("\nAll category tests PASSED")
        sys.exit(0)
    else:
        total_fails = sum(r["failed"] for r in results.values())
        print(f"\nSome tests FAILED — {total_fails} failures total")
        sys.exit(1)


if __name__ == "__main__":
    main()
