#!/usr/bin/env python3
"""Quick verification of pivot_ir module."""
import sys
sys.path.insert(0, '/home/alex/Projects/portkit/ai-engine/mmsd/tinker')

from pivot_ir import (
    parse_java_to_pivot_ir, emit_pivot_ir_to_bedrock,
    compute_apf_reward, compare_direct_vs_pivot,
    SAMPLE_TEST_CASES, DEFAULT_APF_CONFIG
)

# Quick demo
sample_java = '''
class MyBlock extends Block {
    public void onInteract(PlayerInteractEvent e) {
        e.getPlayer().sendMessage("Hello!");
    }
}
'''

ir = parse_java_to_pivot_ir(sample_java)
print("Parsed IR:")
print(f"  Blocks: {list(ir.blocks.keys())}")
print(f"  Events: {len(ir.global_events)}")

output = emit_pivot_ir_to_bedrock(ir)
print(f"\nGenerated files: {list(output.keys())}")

# APF reward
completion = """```json
{"format_version": 2, "header": {"name": "Test"}}
```
```javascript
import { world } from "@minecraft/server";
world.afterEvents.tick.subscribe(() => {});
```
"""

reward, comps = compute_apf_reward(completion, "reference")
print(f"\nAPF Reward: {reward:.3f}")
print(f"  Entity: {comps['entity_coverage']:.2f}")
print(f"  Event: {comps['event_coverage']:.2f}")
print(f"  API: {comps['api_coverage']:.2f}")
print(f"  Structure: {comps['structure']:.2f}")

print("\nAll components working!")