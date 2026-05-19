#!/usr/bin/env python3
"""
Pivot IR Benchmark — Compare Direct vs. Pivot-based Conversion
============================================================

This module provides benchmark utilities for comparing:
1. Direct conversion (Java → Bedrock in one step)
2. Pivot-based conversion (Java → PivotIR → Bedrock)

Benchmark Metrics:
  - Coverage: Entity, event, API coverage percentages
  - Accuracy: BLEU-like overlap with reference
  - Hallucination: Count of fabricated APIs
  - Latency: Time for conversion

Author: PortKit AI Engine
Issues: #1578, #1624, #1626
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path

from pivot_ir.schema import PivotIR, dict_to_pivot_ir, pivot_ir_to_dict
from pivot_ir.java_parser import parse_java_to_pivot_ir, JavaToPivotIRAdapter
from pivot_ir.bedrock_emitter import emit_pivot_ir_to_bedrock, PivotIRToBedrockAdapter


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    method: str  # "direct" or "pivot_ir"
    java_source: str
    reference_output: str
    generated_output: str
    generation_time_ms: float
    
    # Coverage metrics
    entity_coverage: float = 0.0
    event_coverage: float = 0.0
    api_coverage: float = 0.0
    
    # Quality metrics
    bleu_score: float = 0.0
    hallucination_count: int = 0
    has_valid_json: bool = False
    has_valid_js: bool = False
    
    # Pivot IR specific (only for pivot_ir method)
    ir_dict: Optional[dict] = None
    
    # Comparison
    vs_direct_score: Optional[float] = None


def compute_bleu(reference: str, hypothesis: str) -> float:
    """Simple BLEU-like F1 score for text overlap."""
    ref_tokens = set(reference.lower().split())
    hyp_tokens = set(hypothesis.lower().split())
    
    if not hyp_tokens or not ref_tokens:
        return 0.0
    
    overlap = len(ref_tokens & hyp_tokens)
    precision = overlap / len(hyp_tokens)
    recall = overlap / len(ref_tokens)
    
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def extract_json(text: str) -> bool:
    """Check if text contains valid JSON."""
    import re
    blocks = re.findall(r"```json\s*(\{[^}]*(?:\{[^}]*\}[^}]*)*\})", text, re.DOTALL)
    for block in blocks:
        try:
            json.loads(block)
            return True
        except json.JSONDecodeError:
            pass
    return '"format_version"' in text and '"header"' in text


def extract_js(text: str) -> bool:
    """Check if text contains JavaScript with proper imports."""
    import re
    has_import = bool(re.search(r"from\s+['\"]@minecraft/server['\"]", text))
    has_world = bool(re.search(r"\bworld\b", text))
    return has_import and has_world


def count_hallucinations(text: str) -> int:
    """Count hallucinated APIs in text."""
    import re
    patterns = [
        r"\bServerPlayerAPI\b",
        r"\bPlayerAPI\b",
        r"\bWorldEvent\b",
        r"\bmodEventBus\b",
        r"\bBlockEntityAPI\b",
        r"\.createLightningBolt\(",
        r"\.spawnLightning\(",
        r"\.registerEvent\(",
    ]
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, text, re.IGNORECASE))
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Conversion Methods
# ─────────────────────────────────────────────────────────────────────────────

def direct_conversion(java_source: str) -> tuple[str, float]:
    """Simulate direct conversion (placeholder for actual model).
    
    In production, this would call the actual conversion model.
    For benchmark, we simulate with rule-based conversion.
    
    Returns:
        Tuple of (output, time_ms)
    """
    start = time.time()
    
    # Use Pivot IR as proxy for direct conversion
    # (In production, the model does this directly)
    adapter = JavaToPivotIRAdapter()
    ir = adapter.parse(java_source)
    
    # Emit Bedrock code
    emitter = PivotIRToBedrockAdapter()
    output_dict = emitter.emit(ir)
    
    # Combine output
    output_parts = []
    if "manifest.json" in output_dict:
        output_parts.append(output_dict["manifest.json"])
    if "scripts/main.js" in output_dict:
        output_parts.append("```javascript\n" + output_dict["scripts/main.js"] + "\n```")
    
    output = "\n\n".join(output_parts)
    
    elapsed = (time.time() - start) * 1000
    return output, elapsed


def pivot_ir_conversion(java_source: str) -> tuple[str, float, PivotIR]:
    """Pivot-based conversion with full IR tracking.
    
    Returns:
        Tuple of (output, time_ms, ir)
    """
    start = time.time()
    
    # Parse to IR
    adapter = JavaToPivotIRAdapter()
    ir = adapter.parse(java_source)
    
    # Emit Bedrock code
    emitter = PivotIRToBedrockAdapter()
    output_dict = emitter.emit(ir)
    
    # Combine output
    output_parts = []
    if "manifest.json" in output_dict:
        output_parts.append(output_dict["manifest.json"])
    if "scripts/main.js" in output_dict:
        output_parts.append("```javascript\n" + output_dict["scripts/main.js"] + "\n```")
    
    output = "\n\n".join(output_parts)
    
    elapsed = (time.time() - start) * 1000
    return output, elapsed, ir


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_single_benchmark(
    java_source: str,
    reference_output: str,
    method: str,
) -> BenchmarkResult:
    """Run a single benchmark.
    
    Args:
        java_source: The Java input
        reference_output: Expected Bedrock output
        method: "direct" or "pivot_ir"
        
    Returns:
        BenchmarkResult
    """
    if method == "direct":
        output, elapsed = direct_conversion(java_source)
        ir = None
    else:
        output, elapsed, ir = pivot_ir_conversion(java_source)
    
    # Compute metrics
    bleu = compute_bleu(reference_output, output)
    hallucinations = count_hallucinations(output)
    has_json = extract_json(output)
    has_js = extract_js(output)
    
    # Coverage (from IR if available)
    entity_cov = 0.0
    event_cov = 0.0
    api_cov = 0.0
    
    if ir is not None:
        total_entities = len(ir.blocks) + len(ir.items) + len(ir.entities)
        translated_entities = (
            sum(1 for b in ir.blocks.values() if b.translated) +
            sum(1 for i in ir.items.values() if i.translated) +
            sum(1 for e in ir.entities.values() if e.translated)
        )
        entity_cov = translated_entities / total_entities if total_entities > 0 else 0.0
        
        all_events = (
            list(ir.global_events) +
            [h for b in ir.blocks.values() for h in b.event_handlers] +
            [h for i in ir.items.values() for h in i.event_handlers] +
            [h for e in ir.entities.values() for h in e.event_handlers]
        )
        total_events = len(all_events)
        translated_events = sum(1 for h in all_events if h.translated)
        event_cov = translated_events / total_events if total_events > 0 else 0.0
        
        all_apis = (
            list(ir.global_apis) +
            [a for b in ir.blocks.values() for a in b.api_calls] +
            [a for i in ir.items.values() for a in i.api_calls] +
            [a for e in ir.entities.values() for a in e.api_calls]
        )
        total_apis = len(all_apis)
        translated_apis = sum(1 for a in all_apis if a.translated)
        api_cov = translated_apis / total_apis if total_apis > 0 else 0.0
    
    result = BenchmarkResult(
        method=method,
        java_source=java_source,
        reference_output=reference_output,
        generated_output=output,
        generation_time_ms=elapsed,
        entity_coverage=entity_cov,
        event_coverage=event_cov,
        api_coverage=api_cov,
        bleu_score=bleu,
        hallucination_count=hallucinations,
        has_valid_json=has_json,
        has_valid_js=has_js,
        ir_dict=pivot_ir_to_dict(ir) if ir else None,
    )
    
    return result


def run_benchmark(
    test_cases: list[dict],
    methods: Optional[list[str]] = None,
) -> list[BenchmarkResult]:
    """Run benchmark for multiple test cases.
    
    Args:
        test_cases: List of dicts with "java" and "reference" keys
        methods: List of methods to test ["direct", "pivot_ir"]
        
    Returns:
        List of BenchmarkResult
    """
    if methods is None:
        methods = ["direct", "pivot_ir"]
    
    results = []
    
    for case in test_cases:
        java = case["java"]
        reference = case["reference"]
        
        for method in methods:
            result = run_single_benchmark(java, reference, method)
            results.append(result)
    
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Report
# ─────────────────────────────────────────────────────────────────────────────

def print_benchmark_report(results: list[BenchmarkResult]) -> None:
    """Print a formatted benchmark report.
    
    Args:
        results: List of BenchmarkResult
    """
    print("\n" + "=" * 80)
    print("PIVOT IR BENCHMARK REPORT")
    print("=" * 80)
    
    # Group by method
    by_method: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        by_method.setdefault(r.method, []).append(r)
    
    for method, method_results in by_method.items():
        print(f"\n{method.upper()}")
        print("-" * 40)
        
        avg_bleu = sum(r.bleu_score for r in method_results) / len(method_results)
        avg_time = sum(r.generation_time_ms for r in method_results) / len(method_results)
        total_hallucinations = sum(r.hallucination_count for r in method_results)
        valid_json = sum(1 for r in method_results if r.has_valid_json)
        valid_js = sum(1 for r in method_results if r.has_valid_js)
        
        avg_entity = sum(r.entity_coverage for r in method_results) / len(method_results)
        avg_event = sum(r.event_coverage for r in method_results) / len(method_results)
        avg_api = sum(r.api_coverage for r in method_results) / len(method_results)
        
        print(f"  BLEU Score:        {avg_bleu:.3f}")
        print(f"  Avg Time:         {avg_time:.1f}ms")
        print(f"  Hallucinations:   {total_hallucinations}")
        print(f"  Valid JSON:       {valid_json}/{len(method_results)}")
        print(f"  Valid JS:         {valid_js}/{len(method_results)}")
        print(f"  Avg Entity Cov:   {avg_entity:.1%}")
        print(f"  Avg Event Cov:    {avg_event:.1%}")
        print(f"  Avg API Cov:      {avg_api:.1%}")
    
    # Compare methods
    if len(by_method) >= 2:
        print("\n" + "=" * 80)
        print("COMPARISON")
        print("=" * 80)
        
        methods = list(by_method.keys())
        method_a = methods[0]
        method_b = methods[1]
        
        results_a = by_method[method_a]
        results_b = by_method[method_b]
        
        bleu_diff = (
            sum(r.bleu_score for r in results_b) / len(results_b) -
            sum(r.bleu_score for r in results_a) / len(results_a)
        )
        time_diff = (
            sum(r.generation_time_ms for r in results_b) / len(results_b) -
            sum(r.generation_time_ms for r in results_a) / len(results_a)
        )
        
        print(f"\n  {method_b} vs {method_a}:")
        print(f"    BLEU improvement: {bleu_diff:+.3f}")
        print(f"    Time difference:  {time_diff:+.1f}ms")


def compare_direct_vs_pivot(test_cases: list[dict]) -> dict:
    """Compare direct vs pivot-based conversion.
    
    Args:
        test_cases: List of dicts with "java" and "reference" keys
        
    Returns:
        Dictionary with comparison results
    """
    results = run_benchmark(test_cases, methods=["direct", "pivot_ir"])
    
    # Compute comparison
    direct_results = [r for r in results if r.method == "direct"]
    pivot_results = [r for r in results if r.method == "pivot_ir"]
    
    comparison = {
        "total_cases": len(test_cases),
        "direct": {
            "avg_bleu": sum(r.bleu_score for r in direct_results) / len(direct_results),
            "avg_time_ms": sum(r.generation_time_ms for r in direct_results) / len(direct_results),
            "total_hallucinations": sum(r.hallucination_count for r in direct_results),
            "valid_json_count": sum(1 for r in direct_results if r.has_valid_json),
            "valid_js_count": sum(1 for r in direct_results if r.has_valid_js),
            "avg_entity_coverage": sum(r.entity_coverage for r in direct_results) / len(direct_results),
            "avg_event_coverage": sum(r.event_coverage for r in direct_results) / len(direct_results),
            "avg_api_coverage": sum(r.api_coverage for r in direct_results) / len(direct_results),
        },
        "pivot_ir": {
            "avg_bleu": sum(r.bleu_score for r in pivot_results) / len(pivot_results),
            "avg_time_ms": sum(r.generation_time_ms for r in pivot_results) / len(pivot_results),
            "total_hallucinations": sum(r.hallucination_count for r in pivot_results),
            "valid_json_count": sum(1 for r in pivot_results if r.has_valid_json),
            "valid_js_count": sum(1 for r in pivot_results if r.has_valid_js),
            "avg_entity_coverage": sum(r.entity_coverage for r in pivot_results) / len(pivot_results),
            "avg_event_coverage": sum(r.event_coverage for r in pivot_results) / len(pivot_results),
            "avg_api_coverage": sum(r.api_coverage for r in pivot_results) / len(pivot_results),
        },
        "improvement": {},
    }
    
    # Compute improvements
    comparison["improvement"]["bleu"] = (
        comparison["pivot_ir"]["avg_bleu"] - comparison["direct"]["avg_bleu"]
    )
    comparison["improvement"]["time_ms"] = (
        comparison["pivot_ir"]["avg_time_ms"] - comparison["direct"]["avg_time_ms"]
    )
    comparison["improvement"]["entity_coverage"] = (
        comparison["pivot_ir"]["avg_entity_coverage"] - comparison["direct"]["avg_entity_coverage"]
    )
    
    return comparison


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_TEST_CASES = [
    {
        "name": "Simple Block",
        "java": """
package com.example;

import net.minecraft.world.level.block.Block;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;

public class SimpleBlock extends Block {
    public SimpleBlock() {
        super(Properties);
    }
    
    @SubscribeEvent
    public void onPlayerInteract(PlayerInteractEvent.RightClickBlock event) {
        event.getPlayer().sendMessage("Clicked!");
    }
}
""",
        "reference": """
```json
{
  "format_version": 2,
  "header": {
    "name": "SimpleBlock",
    "uuid": "sample-uuid",
    "version": [1, 0, 0]
  }
}
```
```javascript
import { world } from "@minecraft/server";
world.afterEvents.playerInteractWithBlock.subscribe((event) => {
    event.player.sendMessage("Clicked!");
});
```
""",
    },
    {
        "name": "Item with Event",
        "java": """
package com.example;

import net.minecraft.world.item.Item;
import net.minecraftforge.event.entity.player.PlayerEvent;

public class CustomItem extends Item {
    public CustomItem() {
        super(Properties);
    }
    
    @SubscribeEvent
    public void onCrafted(PlayerEvent.ItemCraftedEvent event) {
        event.getPlayer().sendMessage("Crafted!");
    }
}
""",
        "reference": """
```json
{
  "format_version": 2,
  "header": {
    "name": "CustomItem",
    "uuid": "item-uuid",
    "version": [1, 0, 0]
  }
}
```
```javascript
import { world, player } from "@minecraft/server";
// Item crafting event
world.afterEvents.itemUse.subscribe((event) => {
    player.sendMessage("Item used!");
});
```
""",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running Pivot IR Benchmark")
    print("=" * 60)
    
    # Run comparison
    comparison = compare_direct_vs_pivot(SAMPLE_TEST_CASES)
    
    print("\nComparison Results:")
    print(f"  Total cases: {comparison['total_cases']}")
    
    print("\nDirect Conversion:")
    for key, value in comparison["direct"].items():
        if isinstance(value, float):
            print(f"    {key}: {value:.3f}")
        else:
            print(f"    {key}: {value}")
    
    print("\nPivot IR Conversion:")
    for key, value in comparison["pivot_ir"].items():
        if isinstance(value, float):
            print(f"    {key}: {value:.3f}")
        else:
            print(f"    {key}: {value}")
    
    print("\nImprovement:")
    for key, value in comparison["improvement"].items():
        if isinstance(value, float):
            print(f"    {key}: {value:+.3f}")
        else:
            print(f"    {key}: {value}")
    
    print("\n" + "=" * 60)
    print("Detailed Benchmark Report:")
    results = run_benchmark(SAMPLE_TEST_CASES, methods=["direct", "pivot_ir"])
    print_benchmark_report(results)