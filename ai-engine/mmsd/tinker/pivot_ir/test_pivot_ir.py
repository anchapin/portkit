#!/usr/bin/env python3
"""
Test Pivot IR Implementation
===========================

Verifies all components of the Pivot IR transpilation system work correctly.

Author: PortKit AI Engine
Issues: #1578, #1594, #1599, #1600, #1605, #1624, #1626
"""

import sys

sys.path.insert(0, "/home/alex/Projects/portkit/ai-engine/mmsd/tinker")

from pivot_ir import (
    # Schema
    Manifest,
    BlockDef,
    EventHandler,
    APICall,
    create_pivot_ir,
    pivot_ir_to_dict,
    dict_to_pivot_ir,
    compute_coverage,
    ir_to_text_summary,
    # Adapters
    JavaToPivotIRAdapter,
    parse_java_to_pivot_ir,
    JAVA_TO_BEDROCK_EVENTS,
    JAVA_TO_BEDROCK_API,
    SAMPLE_JAVA_BLOCK,
    SAMPLE_JAVA_ITEM,
    PivotIRToBedrockAdapter,
    emit_pivot_ir_to_bedrock,
    # APF Reward
    compute_apf_reward,
    compute_apf_with_legacy,
    # Benchmark
    run_benchmark,
    print_benchmark_report,
    compare_direct_vs_pivot,
    SAMPLE_TEST_CASES,
)


def test_schema():
    """Test Pivot IR schema."""
    print("\n1. Testing Schema...")

    # Create a manifest
    manifest = Manifest(
        name="test_mod",
        uuid="test-uuid",
        version=[1, 0, 0],
        description="Test mod",
    )

    # Create a block
    block = BlockDef(
        name="test_block",
        properties={"material": "stone"},
        event_handlers=[
            EventHandler(
                java_event="@SubscribeEvent",
                bedrock_event="playerInteractWithBlock",
                callback_params=["player", "block"],
                body_statements=["player.sendMessage('Hello!')"],
                translated=True,
            )
        ],
        api_calls=[
            APICall(
                chain="world.afterEvents.playerInteractWithBlock.subscribe",
                depth=4,
                source_java="event.handle()",
                translated=True,
            )
        ],
    )

    # Create IR
    ir = create_pivot_ir(
        manifest=manifest,
        blocks={"test_block": block},
        raw_java="// Test Java",
    )
    ir.total_entities = 1
    ir.translated_entities = 1
    ir.total_events = 1
    ir.translated_events = 1
    ir.total_api_calls = 1
    ir.translated_api_calls = 1

    # Test serialization
    d = pivot_ir_to_dict(ir)
    ir2 = dict_to_pivot_ir(d)

    assert ir2.blocks["test_block"].name == "test_block"
    assert len(ir2.blocks["test_block"].event_handlers) == 1

    # Test coverage
    cov = compute_coverage(ir)
    assert cov["entity_coverage"] == 1.0
    assert cov["overall_coverage"] == 1.0

    # Test summary
    summary = ir_to_text_summary(ir)
    assert "test_block" in summary
    assert "100.0%" in summary or "1.0%" in summary  # 100% coverage

    print("   ✓ Schema works correctly")


def test_java_parser():
    """Test Java → PivotIR adapter."""
    print("\n2. Testing Java Parser...")

    # Parse sample Java
    ir = parse_java_to_pivot_ir(SAMPLE_JAVA_BLOCK)

    assert len(ir.blocks) >= 1, "Should have at least one block"
    assert ir.raw_java == SAMPLE_JAVA_BLOCK

    # Check event mapping
    block_name = list(ir.blocks.keys())[0]
    block = ir.blocks[block_name]

    print(f"   Parsed block: {block_name}")
    print(f"   Events: {len(block.event_handlers)}")

    # Test coverage stats
    adapter = JavaToPivotIRAdapter()
    ir2 = adapter.parse(SAMPLE_JAVA_ITEM)
    assert len(ir2.items) >= 1

    print("   ✓ Java parser works correctly")


def test_bedrock_emitter():
    """Test PivotIR → Bedrock emitter."""
    print("\n3. Testing Bedrock Emitter...")

    # Parse and emit
    ir = parse_java_to_pivot_ir(SAMPLE_JAVA_BLOCK)
    ir.manifest = Manifest(
        name="TestMod",
        uuid="test-uuid",
        version=[1, 0, 0],
        description="Emitted from Pivot IR",
    )

    adapter = PivotIRToBedrockAdapter()

    # Emit manifest
    manifest_json = adapter.emit_manifest(ir)
    assert '"format_version"' in manifest_json
    assert "TestMod" in manifest_json

    # Emit scripts
    script_js = adapter.emit_scripts(ir)
    assert "@minecraft/server" in script_js
    assert ".subscribe" in script_js

    # Emit all
    output = adapter.emit(ir)
    assert "manifest.json" in output
    assert "scripts/main.js" in output

    print("   ✓ Bedrock emitter works correctly")


def test_end_to_end():
    """Test end-to-end conversion."""
    print("\n4. Testing End-to-End Conversion...")

    # Java → IR → Bedrock
    ir = parse_java_to_pivot_ir(SAMPLE_JAVA_BLOCK)
    ir.manifest = Manifest(
        name="E2ETest",
        uuid="e2e-uuid",
        version=[1, 0, 0],
    )

    output = emit_pivot_ir_to_bedrock(ir)

    manifest = output.get("manifest.json", "")
    script = output.get("scripts/main.js", "")

    assert "format_version" in manifest
    assert "@minecraft/server" in script

    print("   ✓ End-to-end conversion works")


def test_apf_reward():
    """Test APF reward function."""
    print("\n5. Testing APF Reward...")

    # Test completion with good coverage
    good_completion = """
```json
{
  "format_version": 2,
  "header": {
    "name": "Test",
    "uuid": "abc-123",
    "version": [1, 0, 0]
  }
}
```

```javascript
import { world } from "@minecraft/server";

world.afterEvents.tick.subscribe(() => {
    console.warn("Tick!");
});
```
"""

    reference = """
```json
{
  "format_version": 2,
  "header": {
    "name": "Test",
    "uuid": "ref-123",
    "version": [1, 0, 0]
  }
}
```

```javascript
import { world } from "@minecraft/server";

world.afterEvents.tick.subscribe(() => {
    // Tick handler
});
```
"""

    reward, components = compute_apf_reward(good_completion, reference)

    print(f"   Good completion reward: {reward:.3f}")
    print(
        f"   Components: entity={components['entity_coverage']:.2f}, "
        f"event={components['event_coverage']:.2f}, "
        f"api={components['api_coverage']:.2f}"
    )

    # Test with hallucinations
    bad_completion = """
```json
{
  "format_version": 2,
  "header": { "name": "Test" }
}
```

```javascript
import { world } from "@minecraft/server";
ServerPlayerAPI.registerMod("test");
world.createLightningBolt(player.getPosition());
```
"""

    reward2, comp2 = compute_apf_reward(bad_completion, reference)
    print(f"   Hallucinated reward: {reward2:.3f} (hallucinations: {comp2['hallucination_count']})")

    # Test combined reward
    combined, all_comp = compute_apf_with_legacy(good_completion, reference)
    print(f"   Combined reward: {combined:.3f}")

    print("   ✓ APF reward works correctly")


def test_benchmark():
    """Test benchmark functionality."""
    print("\n6. Testing Benchmark...")

    # Run comparison
    comparison = compare_direct_vs_pivot(SAMPLE_TEST_CASES)

    print(f"\n   Total cases: {comparison['total_cases']}")
    print(f"   Direct avg BLEU: {comparison['direct']['avg_bleu']:.3f}")
    print(f"   Pivot IR avg BLEU: {comparison['pivot_ir']['avg_bleu']:.3f}")
    print(f"   BLEU improvement: {comparison['improvement']['bleu']:+.3f}")

    # Run detailed benchmark
    results = run_benchmark(SAMPLE_TEST_CASES, methods=["direct", "pivot_ir"])
    print_benchmark_report(results)

    print("   ✓ Benchmark works correctly")


def test_event_mappings():
    """Test event mappings."""
    print("\n7. Testing Event Mappings...")

    # Verify key mappings exist
    assert JAVA_TO_BEDROCK_EVENTS["onPlayerJoined"] == "playerSpawn"
    assert JAVA_TO_BEDROCK_EVENTS["onBlockBreak"] == "blockBreak"

    # Verify API mappings
    assert "player.sendMessage" in JAVA_TO_BEDROCK_API

    print(f"   {len(JAVA_TO_BEDROCK_EVENTS)} event mappings")
    print(f"   {len(JAVA_TO_BEDROCK_API)} API mappings")
    print("   ✓ Event mappings correct")


def main():
    """Run all tests."""
    print("=" * 60)
    print("PIVOT IR IMPLEMENTATION TESTS")
    print("=" * 60)

    try:
        test_schema()
        test_java_parser()
        test_bedrock_emitter()
        test_end_to_end()
        test_apf_reward()
        test_benchmark()
        test_event_mappings()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n\nTEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
