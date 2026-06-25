#!/usr/bin/env python3
"""
Generate synthetic adaption lab datasets for testing the MMSD pipeline.

This creates sample data that follows the MMSD format but represents
"adaption lab" data. It is NOT real conversion data - just for pipeline testing.

Usage:
    python generate_adaption_samples.py --count 50 --output ai-engine/mmsd/data/processed/
"""

import argparse
import json
import random


JAVA_TEMPLATES = [
    """```java
package com.example.adaption;

import net.minecraft.world.level.block.Block;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.Mod;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

@Mod("adaptionmod")
public class AdaptionMod {
    public AdaptionMod() {{
        IEventBus modEventBus = FMLJavaModLoadingContext.get().getModEventBus();
        ModBlocks.BLOCKS.register(modEventBus);
        ModItems.ITEMS.register(modEventBus);
        MinecraftForge.EVENT_BUS.register(this);
    }}
}}
```""",
    """```java
package com.example.adaption;

import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;

@Mod.EventBusSubscriber(bus = Mod.EventBusSubscriber.Bus.MOD)
public class ModItems {{
    public static final DeferredRegister<Item> ITEMS = DeferredRegister.create(ForgeRegistries.ITEMS, "adaptionmod");

    public static final RegistryObject<Item> EXAMPLE_ITEM = ITEMS.register("example_item",
        () -> new Item(new Item.Properties()));
}}
```""",
]

BEDROCK_TEMPLATES = [
    """```json
{{
    "format_version": 2,
    "header": {{
        "description": "Adaption Mod",
        "name": "adaptionmod",
        "uuid": "00000000-0000-0000-0000-000000000001",
        "version": [1, 0, 0],
        "min_engine_version": [1, 21, 0]
    }},
    "modules": [
        {{
            "type": "resources",
            "uuid": "00000000-0000-0000-0000-000000000002",
            "version": [1, 0, 0]
        }}
    ]
}}
```""",
    """```javascript
import {{ world, system }} from "@minecraft/server";

system.runInterval(() => {{
    const players = world.getPlayers();
    players.forEach(player => {{
        player.sendMessage("Adaption Mod loaded!");
    }});
}}, 20);
```""",
]

INSTRUCTIONS = [
    "A simple item mod that adds a basic collectible resource",
    "A block mod with a custom crafting station",
    "An entity mod that adds a passive mob",
    "A tool mod with custom durability and abilities",
    "A food mod with special saturation effects",
    "A decorative block mod with multiple variants",
]

REASONING_TEMPLATES = [
    """To convert this mod, we need to:

1. Define the custom item in a JSON file with proper identifier
2. Set up the item's properties (max stack size, durability, etc.)
3. Create a JavaScript handler for any interactions
4. Register the item in the manifest

The key mapping between Java Forge and Bedrock:
- Forge DeferredRegister → Bedrock JSON definition
- RegistryObject<Item> → Item component in JSON
- Item.Properties → Item component properties""",
    """Implementation approach:

1. Create block definition in JSON with format_version 1.16.0+
2. Define block states for any variations
3. Set up crafting recipe in JSON
4. JavaScript for any interactive behavior

Java Forge → Bedrock mapping:
- Block class → minecraft:block component
- BlockState → block states JSON
- Event handlers → system.runInterval() or event listeners""",
]


def generate_adaption_entry(idx: int, include_errors: bool = False) -> dict:
    """Generate a single synthetic adaption entry."""
    instruction = f"[Adaption Lab Sample {idx}] {random.choice(INSTRUCTIONS)}"

    java_source = random.choice(JAVA_TEMPLATES)
    bedrock_source = random.choice(BEDROCK_TEMPLATES)
    reasoning_trace = random.choice(REASONING_TEMPLATES)

    if include_errors and random.random() < 0.1:
        java_source = "Error: Synthetic test error\n" + java_source

    entry = {
        "instruction": instruction,
        "reasoning_trace": reasoning_trace,
        "java_source": java_source,
        "bedrock_source": bedrock_source,
    }

    if include_errors and random.random() < 0.05:
        entry["_test_error_marker"] = True

    return entry


def generate_adaption_dataset(count: int, output_path: str, include_errors: bool = False):
    """Generate a synthetic adaption dataset file."""
    print(f"Generating {count} synthetic adaption samples...")

    with open(output_path, "w") as f:
        for i in range(count):
            entry = generate_adaption_entry(i, include_errors=include_errors)
            f.write(json.dumps(entry) + "\n")

    print(f"Wrote {count} entries to {output_path}")

    size = sum(1 for _ in open(output_path))
    print(f"Verified: {size} lines in output file")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic adaption lab datasets")
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of samples to generate",
    )
    parser.add_argument(
        "--output",
        default="ai-engine/mmsd/data/processed/adaption_minecraft_mod_to_bedrock.jsonl",
        help="Output file path",
    )
    parser.add_argument(
        "--include-errors",
        action="store_true",
        help="Include synthetic error entries for testing error handling",
    )

    args = parser.parse_args()

    generate_adaption_dataset(args.count, args.output, args.include_errors)

    print("\nGenerated files:")
    print(f"  {args.output}")

    if args.output.endswith(".jsonl"):
        base = args.output.replace(".jsonl", "")
        extra_files = [
            base + "_bedrock_mod_conversions.jsonl",
            base + "_mod_conversion_pairs.jsonl",
        ]
        for extra in extra_files:
            generate_adaption_dataset(min(args.count, 30), extra, args.include_errors)
            print(f"  {extra}")


if __name__ == "__main__":
    main()
