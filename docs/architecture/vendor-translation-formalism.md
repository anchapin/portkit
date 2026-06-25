# Vendor Translation Formalism for Java → Bedrock Construct Mapping

## Overview

This document formalizes the Java (Forge/Fabric) → Bedrock Scripting API conversion problem using the **vendor-translation formalism** from industrial PLC code translation. The formalism was introduced in *Ladder Logic Translation using Large Language Models in Industrial Automation* (arxiv.org/abs/2605.31458) and adapted for the PortKit Java → Bedrock domain.

## Problem Structure

The Java → Bedrock conversion is structurally isomorphic to the PLC vendor-translation problem:

| PLC Domain | PortKit Domain |
|---|---|
| Rockwell → Siemens | Java Forge/Fabric → Bedrock Scripting API |
| Incompatible programming environments | Java + Forge API vs. TypeScript + Bedrock Scripting API |
| Incompatible constructs | Java EventBus → Bedrock `afterEvents`; TileEntity.tick() → `system.runInterval()` |
| Sparse proprietary documentation | Bedrock Scripting API underdocumented vs. Java Forge |
| No-direct-equivalent constructs | Forge Capability system (no Bedrock equivalent) |

## Formal Architecture

The formalism introduces an explicit **Canonical Intermediate Representation (IR)** as a vendor-neutral middle layer:

```
┌──────────────────────────┐    ┌──────────────────┐    ┌─────────────────────────────┐
│  Vendor Dialect A (Java) │ →  │  Canonical IR    │ →  │ Vendor Dialect B (Bedrock) │
│                          │    │                  │    │                             │
│  JavaDialectParser        │    │  IRConstruct     │    │  BedrockDialectGenerator     │
│  (extracts semantics)     │    │  (neutral form)  │    │  (generates target code)    │
└──────────────────────────┘    │                  │    └─────────────────────────────┘
                                 │  FormalMappingTable
                                 │  (typed mapping table)
                                 └──────────────────┘
```

### Why the Canonical IR Layer?

**Without canonical IR:** Java → Bedrock conversion happens implicitly, with semantic approximations hidden inside the LLM's behavior. Completeness checking is impossible; "no equivalent" cases are handled inconsistently.

**With canonical IR:** Every construct has an explicit, vendor-neutral definition. The mapping table makes the confidence and semantic delta of every translation explicit. Completeness checking is straightforward — just look at which `ConstructCategory` entries exist in the table.

## Canonical IR Construct Types

The canonical IR defines the following vendor-neutral construct types:

| Construct | Category | Semantic Equivalence | Notes |
|---|---|---|---|
| `EventHandler(event_type, body)` | `EVENT` | DIRECT | `@SubscribeEvent` → `world.afterEvents.subscribe` |
| `TickFunction(interval_ticks, body)` | `TICK` | APPROXIMATE | `BlockEntity.tick()` → `system.runInterval()` |
| `BlockInteraction(trigger_item, target_block, body)` | `BLOCK_INTERACTION` | DIRECT | `PlayerInteractEvent` → `playerInteractWithBlock` |
| `BlockBreak(block_type, drop_xp, body)` | `BLOCK_BREAK` | DIRECT | `BlockEvent.BreakEvent` → `blockBreak` |
| `EntitySpawn(entity_type, body)` | `ENTITY_SPAWN` | DIRECT | `EntityJoinLevelEvent` → `entitySpawn` |

## Semantic Equivalence Classification

Each mapping entry is classified into one of four categories:

- **`DIRECT`**: The canonical form has a direct, semantically equivalent Bedrock form. Confidence ≥ 0.8 typically.
- **`APPROXIMATE`**: A functional Bedrock equivalent exists but with documented behavioral differences. Confidence 0.5–0.85. See `MappingDelta` entries.
- **`NO_EQUIVALENT`**: No Bedrock equivalent exists. A workaround strategy must be documented.
- **`VENDOR_SPECIFIC`**: The construct is specific to one vendor and cannot be canonicalized.

## Formal Mapping Table

The `FormalMappingTable` (`ai-engine/conversion/vendor_formalism.py`) is the core artifact:

```python
@dataclass
class MappingEntry:
    java_construct_id: str
    canonical_construct: IRConstruct
    bedrock_js_pattern: str
    confidence: float           # 0.0–1.0
    equivalence: SemanticEquivalence
    deltas: List[MappingDelta] # For APPROXIMATE / NO_EQUIVALENT
    limitations: List[str]
    requires_manual_review: bool
    category: ConstructCategory
```

### Current Construct Coverage

| Java Construct ID | Canonical IR | Bedrock API | Confidence | Equivalence |
|---|---|---|---|---|
| `java_player_interact` | `EventHandler` | `world.afterEvents.playerInteractWithBlock` | 0.80 | DIRECT |
| `java_block_break` | `BlockBreak` | `world.afterEvents.blockBreak` | 0.85 | DIRECT |
| `java_ticking_tile` | `TickFunction` | `system.runInterval` | 0.65 | APPROXIMATE |
| `java_entity_join` | `EntitySpawn` | `world.afterEvents.entitySpawn` | 0.80 | DIRECT |
| `java_block_right_click` | `BlockInteraction` | `world.afterEvents.playerInteractWithBlock` | 0.80 | DIRECT |

## Semantic Delta Documentation

The key innovation for "principled no-equivalent handling" is the `MappingDelta` struct, which formally documents behavioral differences for APPROXIMATE mappings:

```python
@dataclass
class MappingDelta:
    delta_type: str       # e.g., "EXECUTION_MODEL", "XP_DROPS"
    java_behavior: str    # What Java actually does
    bedrock_behavior: str # What Bedrock actually does
    workaround: str       # How to approximate the behavior
    mmd_tag: str         # MMSD annotation tag
```

### Example: `TickFunction` Semantic Deltas

**`java_ticking_tile` → `system.runInterval`** has two documented deltas:

1. **EXECUTION_MODEL** (mmd_tag: `TICK_ORDERING_NON_DETERMINISTIC`)
   - Java: Minecraft tick loop calls `BlockEntity.tick()` synchronously per-block in deterministic order
   - Bedrock: `system.runInterval()` is best-effort at ~20 Hz with no guaranteed tick ordering
   - Workaround: Accept non-determinism, or use a ticking entity component

2. **SCALABILITY** (mmd_tag: `TICK_SCOPE_GLOBAL`)
   - Java: Tick is called per-block-entity only for loaded chunks
   - Bedrock: Callback runs globally — all block positions must be iterated explicitly
   - Workaround: Track custom block positions and filter per-tick

### Example: `BlockBreak` Semantic Delta

**`java_block_break`** has one documented delta:

1. **XP_DROPS** (mmd_tag: `BREAK_XP_MANUAL_AWARD`)
   - Java: `event.setExpToDrop(n)` controls XP drops directly
   - Bedrock: XP must be awarded via `player.giveExperience()` manually after the event
   - Workaround: Track XP amount and call `player.giveExperience()` in the handler body

## Usage

```python
from ai_engine.conversion.vendor_formalism import VendorFormalism

vf = VendorFormalism()

# Parse Java source → canonical IR
ir_constructs = vf.parse_java(java_source)

# Generate Bedrock from canonical IR
for ir in ir_constructs:
    bedrock_code = vf.generate_bedrock(ir)

# Full pipeline: Java → {canonical IR, Bedrock code, confidence}
results = vf.translate_java_to_bedrock(java_source)

# Coverage report
report = vf.coverage_report()
# {'total_mappings': 7, 'categories_covered': 5, 'avg_confidence': 0.76, ...}
```

## MMSD Integration

Each `MappingDelta` carries an `mmd_tag` field suitable for MMSD (Multi-Modal Semantic Delta) annotation. These tags enable:
- Systematic identification of high-semantic-delta construct categories
- Grounded evaluation of conversion quality per category
- Targeted improvement of the hardest conversion categories

## Extending the Formalism

To add a new construct type:

1. Define a new `IRConstruct` subclass in `vendor_formalism.py`
2. Add extraction logic to `JavaDialectParser._extract_*`
3. Add generation logic to `BedrockDialectGenerator._generate_*`
4. Add a `MappingEntry` to `FormalMappingTable._add_*_mappings()`
5. Document any `MappingDelta` entries for APPROXIMATE mappings
6. Add unit tests in `test_vendor_formalism.py`

## References

- [Ladder Logic Translation using LLMs in Industrial Automation](https://arxiv.org/abs/2605.31458) — The paper that introduced the formalism
- [PortKit Issue #1723](https://github.com/anchapin/portkit/issues/1723) — Original issue requesting this implementation
