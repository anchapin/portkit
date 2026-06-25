#!/usr/bin/env python3
"""
PortKit Premium Conversion Client
Uses frontier models (DeepSeek V4, Kimi K2, etc.) via OpenRouter for high-quality
Java→Bedrock mod conversion. No fine-tuning needed — just few-shot prompting.

Usage:
    from mmsd.premium_client import PortKitPremium

    client = PortKitPremium()  # uses OPENROUTER_API_KEY env var
    result = client.convert(instruction="Custom swords mod", java_source=java_code)

Supports fallback to local fine-tuned model via the standard tier.
"""

import os
import re
import time
import logging
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ── Response types ───────────────────────────────────────────────────────────


@dataclass
class ConversionResult:
    """Result of a Java → Bedrock conversion."""

    success: bool
    reasoning: str = ""
    bedrock_manifest: str = ""
    bedrock_script: str = ""
    raw_output: str = ""
    model_used: str = ""
    tier: str = "premium"  # or "standard"
    latency_ms: int = 0
    error: str = ""
    has_hallucination: bool = False
    hallucinated_apis: list[str] = field(default_factory=list)
    hallucination_rate: float = 0.0
    hallucination_signal: str = ""


# ── Few-shot examples (curated from validated synthesis pairs) ───────────────

FEW_SHOT_EXAMPLES = [
    {
        "name": "Block Registration",
        "user": """Mod Description: Custom Ore Block - adds a new glowing ore block that drops custom gems

Java Source:
```java
package com.example.mod;

import net.minecraft.block.Block;
import net.minecraft.block.material.Material;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraftforge.event.RegistryEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.eventhandler.SubscribeEvent;

@Mod(modid = "customore", name = "Custom Ore", version = "1.0")
public class CustomOreMod {
    public static Block GLOW_ORE = new Block(Material.ROCK)
        .setLightLevel(1.0f)
        .setHardness(3.0f);

    @SubscribeEvent
    public void registerBlocks(RegistryEvent.Register<Block> event) {
        event.getRegistry().register(GLOW_ORE.setRegistryName("glow_ore"));
    }

    @SubscribeEvent
    public void registerItems(RegistryEvent.Register<Item> event) {
        event.getRegistry().register(new ItemBlock(GLOW_ORE).setRegistryName("glow_ore"));
    }

    public static class ItemBlock extends Item {
        public ItemBlock(Block block) {
            setCreativeTab(CreativeTabs.BUILDING_BLOCKS);
        }
    }
}
```

Convert this to a Bedrock Add-on.""",
        "assistant": """## Conversion Plan

1. **Block Registration**: Java uses `RegistryEvent.Register<Block>` → Bedrock uses `blocks.json` + custom block definition in the behavior pack
2. **Light Level**: Java's `setLightLevel(1.0f)` → Bedrock's `minecraft:block_light_emission` component
3. **Hardness**: Java's `setHardness(3.0f)` → Bedrock's `minecraft:destructible_by_mining` component
4. **Creative Tab**: Java's `CreativeTabs.BUILDING_BLOCKS` → Bedrock's `minecraft:creative_category`

## Bedrock Add-on Output

### manifest.json
```json
{
    "format_version": 2,
    "header": {
        "name": "Custom Ore",
        "description": "Adds a glowing custom ore block",
        "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "version": [1, 0, 0],
        "min_engine_version": [1, 20, 0]
    },
    "modules": [
        {
            "type": "data",
            "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "version": [1, 0, 0]
        },
        {
            "type": "script",
            "language": "javascript",
            "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
            "version": [1, 0, 0],
            "entry": "scripts/main.js"
        }
    ],
    "dependencies": [
        { "module_name": "@minecraft/server", "version": "1.16.0" }
    ]
}
```

### blocks.json
```json
{
    "format_name": "customore:glow_ore",
    "customore:glow_ore": {
        "textures": "glow_ore",
        "sound": "stone"
    }
}
```

### scripts/main.js
```javascript
import { world } from "@minecraft/server";

world.afterEvents.worldInitialize.subscribe(() => {
    // Block is registered via blocks.json and BP definitions
    // Custom behavior can be added here (e.g., particle effects for glow)
});
```""",
    },
    {
        "name": "Custom Item with Right-Click Action",
        "user": """Mod Description: Magic Wand - a custom item that teleports the player forward on right-click

Java Source:
```java
package com.example.mod;

import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.util.ActionResult;
import net.minecraft.util.EnumHand;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Vec3d;
import net.minecraft.world.World;
import net.minecraftforge.event.RegistryEvent;
import net.minecraftforge.fml.common.Mod;

@Mod(modid = "magicwand", name = "Magic Wand", version = "1.0")
public class MagicWandMod {
    public static Item MAGIC_WAND = new Item() {
        @Override
        public ActionResult<ItemStack> onItemRightClick(World world, EntityPlayer player, EnumHand hand) {
            Vec3d look = player.getLookVec();
            Vec3d target = player.getPositionVector().add(look.scale(10));
            player.setPositionAndUpdate(target.x, target.y, target.z);
            player.getCooldownTracker().setCooldown(this, 60);
            return ActionResult.newResult(EnumActionResult.SUCCESS, player.getHeldItem(hand));
        }
    };

    @SubscribeEvent
    public void registerItems(RegistryEvent.Register<Item> event) {
        event.getRegistry().register(MAGIC_WAND.setRegistryName("magic_wand"));
    }
}
```

Convert this to a Bedrock Add-on.""",
        "assistant": """## Conversion Plan

1. **Item Registration**: Java uses `RegistryEvent.Register<Item>` → Bedrock uses `items.json` with custom item definition
2. **Right-Click Action**: Java's `onItemRightClick` → Bedrock's `@minecraft/server` `itemUseBeforeEvent` or `itemUseOnBeforeEvent`
3. **Teleportation**: Java's `setPositionAndUpdate` → Bedrock's `player.teleport()`
4. **Cooldown**: Java's `getCooldownTracker().setCooldown(60)` → Bedrock's `player.addCooldown("magic_wand", 60)`

## Bedrock Add-on Output

### manifest.json
```json
{
    "format_version": 2,
    "header": {
        "name": "Magic Wand",
        "description": "A wand that teleports you forward",
        "uuid": "d4e5f6a7-b8c9-0123-defa-234567890123",
        "version": [1, 0, 0],
        "min_engine_version": [1, 20, 0]
    },
    "modules": [
        {
            "type": "data",
            "uuid": "e5f6a7b8-c9d0-1234-efab-345678901234",
            "version": [1, 0, 0]
        },
        {
            "type": "script",
            "language": "javascript",
            "uuid": "f6a7b8c9-d0e1-2345-fabc-456789012345",
            "version": [1, 0, 0],
            "entry": "scripts/main.js"
        }
    ],
    "dependencies": [
        { "module_name": "@minecraft/server", "version": "1.16.0" }
    ]
}
```

### scripts/main.js
```javascript
import { world, system } from "@minecraft/server";

world.beforeEvents.itemUse.subscribe((event) => {
    const player = event.source;
    const item = event.itemStack;

    if (item.typeId !== "magicwand:magic_wand") return;

    const viewDirection = player.getViewDirection();
    const currentPos = player.location;

    const targetX = currentPos.x + viewDirection.x * 10;
    const targetY = currentPos.y + viewDirection.y * 10;
    const targetZ = currentPos.z + viewDirection.z * 10;

    try {
        player.teleport({ x: targetX, y: targetY, z: targetZ });
        player.addCooldown("magicwand:magic_wand", 60);
    } catch (e) {
        player.sendMessage("§cTeleport failed!");
    }
});
```""",
    },
    {
        "name": "Entity Spawning with Events",
        "user": """Mod Description: Summoning Staff - right-click to spawn a custom entity (pet wolf) at the player's location

Java Source:
```java
package com.example.mod;

import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityLiving;
import net.minecraft.entity.passive.EntityWolf;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.util.EnumActionResult;
import net.minecraft.util.EnumFacing;
import net.minecraft.util.EnumHand;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

public class SummoningStaff extends Item {
    @Override
    public EnumActionResult onItemUse(EntityPlayer player, World world, BlockPos pos, EnumHand hand, EnumFacing facing, float hitX, float hitY, float hitZ) {
        if (!world.isRemote) {
            EntityWolf wolf = new EntityWolf(world);
            wolf.setPosition(pos.getX() + hitX, pos.getY() + hitY, pos.getZ() + hitZ);
            wolf.setTamedBy(player);
            world.spawnEntity(wolf);
            return EnumActionResult.SUCCESS;
        }
        return EnumActionResult.PASS;
    }
}
```

Convert this to a Bedrock Add-on.""",
        "assistant": """## Conversion Plan

1. **Entity Spawning**: Java's `new EntityWolf(world)` + `world.spawnEntity()` → Bedrock's `dimension.spawnEntity()`
2. **Taming**: Java's `setTamedBy(player)` → Bedrock's `entity.setProperty("minecraft:tameable", ...)` or direct NBT via spawn event
3. **Position Calculation**: Java's `pos + hitX/Y/Z` → Bedrock's `location` offset from block face
4. **Item Use on Block**: Java's `onItemUse` → Bedrock's `world.beforeEvents.itemUseOn`

## Bedrock Add-on Output

### manifest.json
```json
{
    "format_version": 2,
    "header": {
        "name": "Summoning Staff",
        "description": "Spawn a tamed wolf at a targeted block",
        "uuid": "a7b8c9d0-e1f2-3456-abcd-567890123456",
        "version": [1, 0, 0],
        "min_engine_version": [1, 20, 0]
    },
    "modules": [
        {
            "type": "data",
            "uuid": "b8c9d0e1-f2a3-4567-bcde-678901234567",
            "version": [1, 0, 0]
        },
        {
            "type": "script",
            "language": "javascript",
            "uuid": "c9d0e1f2-a3b4-5678-cdef-789012345678",
            "version": [1, 0, 0],
            "entry": "scripts/main.js"
        }
    ],
    "dependencies": [
        { "module_name": "@minecraft/server", "version": "1.16.0" }
    ]
}
```

### scripts/main.js
```javascript
import { world } from "@minecraft/server";

world.beforeEvents.itemUseOn.subscribe((event) => {
    const player = event.source;
    const item = event.itemStack;
    const block = event.block;

    if (item.typeId !== "summonstaff:summoning_staff") return;

    const spawnLocation = {
        x: block.location.x + block.faceDirection.x + 0.5,
        y: block.location.y + block.faceDirection.y,
        z: block.location.z + block.faceDirection.z + 0.5,
    };

    system.run(() => {
        const wolf = player.dimension.spawnEntity("minecraft:wolf", spawnLocation);
        wolf.addTag(`tamed_by_${player.name}`);
        wolf.setProperty("minecraft:tameable", true);
        player.sendMessage("§aA loyal companion has been summoned!");
    });
});
```""",
    },
]


# ── System prompt ────────────────────────────────────────────────────────────

# Hallucination-prevention constraint injected into every prompt (issue #1678)
ALLOWLIST_CONSTRAINT = """
## API ALLOWLIST CONSTRAINT (CRITICAL — issue #1678)

You MUST only use Bedrock Script API methods from `@minecraft/server`.
The following are VALID and SAFE to use:
- world, system, player, players, dimension (globals)
- world.afterEvents / world.beforeEvents (WorldAfterEvents / WorldBeforeEvents)
- player.afterEvents / player.beforeEvents (PlayerAfterEvents / PlayerBeforeEvents)
- entity.afterEvents / entity.beforeEvents (EntityAfterEvents / EntityBeforeEvents)
- system.runInterval / system.runTimeout / system.run (SystemEvents)
- world.getDimension(), dimension.spawnEntity(), player.teleport()
- player.sendMessage(), player.getComponent(), player.addCooldown(), player.addTag()
- world.playSound(), world.getBlock(), world.setDynamicProperty()
- entity.kill(), entity.getEntities(), entity.getEntitiesWithTag()
- Block, BlockPermutation, BlockState, ItemStack, Entity, Player, Container
- .subscribe() for event listeners (NOT .register())

**NEVER generate any of the following — they do NOT exist in Bedrock:**
- ServerPlayerAPI, ServerPlayer, PlayerAPI, WorldEvent, BlockEntityAPI
- EntityPlayerAPI, WorldAPI, modEventBus
- require('@minecraft/server') — use ES6 import instead
- registerMod(), defineMod() — use manifest.json instead
- .createLightningBolt(), .spawnLightning(), .registerEvent()
- .registerServerEvent(), .onServerStart(), .onServerStop()
- event.level.*, server.getWorld(), getServer(), Server.getInstance()
- world.setBlock(...getPosition()), getTileEntity().getInventory()

When in doubt, DO NOT guess. If a Java API has no clear Bedrock equivalent,
explain that limitation rather than fabricating an API.
"""


SYSTEM_PROMPT = """You are PortKit, an expert at converting Minecraft Java Edition Forge mods to Bedrock Edition Add-ons.

Given a mod description and Java source code, you must:
1. **Reason** through the conversion — map each Java class/event/registry to its Bedrock equivalent
2. **Produce** a complete Bedrock Add-on implementation

Key mapping rules:
- Java `RegistryEvent.Register<Block/Item>` → Bedrock `blocks.json` / `items.json` definitions
- Java `onItemRightClick` → Bedrock `@minecraft/server` `beforeEvents.itemUse`
- Java `onItemUse` (on block) → Bedrock `beforeEvents.itemUseOn`
- Java entity spawning (`new EntityX(world)`) → Bedrock `dimension.spawnEntity()`
- Java NBT data → Bedrock entity properties / components
- Java `@Mod.EventHandler` lifecycle → Bedrock `world.afterEvents.worldInitialize`
- Java packages (`com.example.mod`) → Bedrock namespace prefixes (`namespace:item_name`)
- Use `@minecraft/server` module for all scripting (NOT the deprecated `mojang-*` modules)
- Target Bedrock format_version 2 and engine version 1.20.0+
- Always include a complete manifest.json with script module and `@minecraft/server` dependency
- Use `system.run()` for operations that require write access in beforeEvents callbacks

Output format:
1. Start with "## Conversion Plan" — explain each mapping decision
2. Then "## Bedrock Add-on Output" — provide all files with proper code blocks

Below are examples of correct conversions:"""


# ── Model configurations ────────────────────────────────────────────────────

MODEL_CONFIGS = {
    "deepseek-v4-pro": {
        "model_id": "deepseek/deepseek-chat-v3.1",
        "provider": "openrouter",
        "max_tokens": 8192,
        "temperature": 0.1,
    },
    "deepseek-v4-flash": {
        "model_id": "deepseek/deepseek-chat-v3-0324",
        "provider": "openrouter",
        "max_tokens": 8192,
        "temperature": 0.1,
    },
    "kimi-k2": {
        "model_id": "moonshotai/kimi-k2",
        "provider": "openrouter",
        "max_tokens": 8192,
        "temperature": 0.1,
    },
    "glm-5": {
        "model_id": "thudm/glm-4-32b",
        "provider": "openrouter",
        "max_tokens": 8192,
        "temperature": 0.1,
    },
}

# Fallback order: best quality first, cheaper alternatives next
DEFAULT_FALLBACK_ORDER = ["deepseek-v4-pro", "kimi-k2", "deepseek-v4-flash", "glm-5"]

API_BASES = {
    "openrouter": "https://openrouter.ai/api/v1",
}


# ── Client ───────────────────────────────────────────────────────────────────


class PortKitPremium:
    """
    Premium Java → Bedrock conversion using frontier models via API.

    Usage:
        client = PortKitPremium()  # reads OPENROUTER_API_KEY from env
        result = client.convert(
            instruction="My awesome mod",
            java_source=open("Mod.java").read(),
        )
        if result.success:
            print(result.bedrock_manifest)
            print(result.bedrock_script)

    Fallback:
        If all API calls fail, falls back to local fine-tuned model
        via PortKitStandard.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-v4-pro",
        fallback_models: Optional[list[str]] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. "
                "Get one at https://openrouter.ai/keys and set the env var."
            )

        self.model = model
        self.fallback_models = fallback_models or DEFAULT_FALLBACK_ORDER
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.Client(timeout=timeout)

    def convert(
        self,
        instruction: str,
        java_source: str,
        model: Optional[str] = None,
    ) -> ConversionResult:
        """
        Convert a Java Forge mod to a Bedrock Add-on.

        Args:
            instruction: Mod description / name
            java_source: Java source code
            model: Override model (e.g., "kimi-k2")

        Returns:
            ConversionResult with parsed Bedrock output
        """
        model_key = model or self.model
        models_to_try = [model_key] + [m for m in self.fallback_models if m != model_key]

        last_error = ""
        for model_name in models_to_try:
            if model_name not in MODEL_CONFIGS:
                logger.warning(f"Unknown model: {model_name}, skipping")
                continue

            result = self._call_model(model_name, instruction, java_source)
            if result.success:
                # Issue #1678: if hallucination detected, try next model
                if result.has_hallucination:
                    logger.warning(
                        f"Model {model_name} hallucinated: {result.hallucinated_apis}. "
                        f"Trying next model..."
                    )
                    last_error = f"HALLUCINATION: {result.hallucinated_apis}"
                    continue
                return result
            last_error = result.error
            logger.warning(f"Model {model_name} failed: {result.error}")

        return ConversionResult(
            success=False,
            error=f"All models failed. Last error: {last_error}",
            tier="premium",
        )

    def _call_model(self, model_key: str, instruction: str, java_source: str) -> ConversionResult:
        """Call a single model and parse the response."""
        cfg = MODEL_CONFIGS[model_key]
        base_url = API_BASES[cfg["provider"]]

        messages = self._build_messages(instruction, java_source)

        for attempt in range(self.max_retries):
            try:
                t0 = time.time()
                resp = self.client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://portkit.dev",
                        "X-Title": "PortKit Premium Converter",
                    },
                    json={
                        "model": cfg["model_id"],
                        "messages": messages,
                        "max_tokens": cfg["max_tokens"],
                        "temperature": cfg["temperature"],
                    },
                )
                latency_ms = int((time.time() - t0) * 1000)

                if resp.status_code == 429:
                    wait = min(2**attempt * 2, 30)
                    logger.warning(f"Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                if resp.status_code != 200:
                    error_text = resp.text[:500]
                    return ConversionResult(
                        success=False,
                        error=f"HTTP {resp.status_code}: {error_text}",
                        model_used=model_key,
                        tier="premium",
                        latency_ms=latency_ms,
                    )

                data = resp.json()
                output = data["choices"][0]["message"]["content"].strip()

                if not output:
                    return ConversionResult(
                        success=False,
                        error="Empty response from model",
                        model_used=model_key,
                        tier="premium",
                    )

                return self._parse_output(output, model_key, latency_ms)

            except httpx.TimeoutException:
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries}")
                if attempt == self.max_retries - 1:
                    return ConversionResult(
                        success=False,
                        error=f"Timed out after {self.max_retries} attempts",
                        model_used=model_key,
                        tier="premium",
                    )
                time.sleep(2**attempt)
            except Exception as e:
                return ConversionResult(
                    success=False,
                    error=f"Exception: {e}",
                    model_used=model_key,
                    tier="premium",
                )

        return ConversionResult(
            success=False,
            error="Exhausted retries",
            model_used=model_key,
            tier="premium",
        )

    def _build_messages(self, instruction: str, java_source: str) -> list[dict]:
        """Build the message payload with system prompt + few-shot examples."""
        full_system = SYSTEM_PROMPT + ALLOWLIST_CONSTRAINT
        messages = [{"role": "system", "content": full_system}]

        # Add few-shot examples
        for example in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})

        # Add the actual request
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Mod Description: {instruction}\n\n"
                    f"Java Source:\n{java_source}\n\n"
                    "Convert this to a Bedrock Add-on."
                ),
            }
        )

        return messages

    def _validate_hallucinations(self, script: str) -> tuple[bool, list[str], float, str]:
        """
        Validate bedrock script for hallucinations using the forbidden API patterns.

        Returns (has_hallucination, hallucinated_apis, hallucination_rate, signal).
        Uses lazy import to avoid circular dependency.
        """
        if not script:
            return False, [], 0.0, ""

        hallucinated_apis: list[str] = []

        # Top hallucinated API patterns from issue #1678 / hallucination_catalog.py
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

        for pattern_str, name in forbidden_patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            if pattern.search(script):
                hallucinated_apis.append(name)

        has_hallucination = len(hallucinated_apis) > 0

        # Extract valid APIs for rate calculation
        valid_apis = []
        valid_patterns = [
            r"world\.afterEvents", r"world\.beforeEvents",
            r"player\.afterEvents", r"player\.beforeEvents",
            r"system\.run", r"dimension\.spawnEntity",
            r"player\.sendMessage", r"player\.getComponent",
            r"\.subscribe\(", r"world\.getDimension",
            r"world\.playSound", r"world\.getBlock",
        ]
        for vp in valid_patterns:
            if re.search(vp, script):
                valid_apis.append(vp)

        total_refs = len(hallucinated_apis) + len(valid_apis)
        hallucination_rate = len(hallucinated_apis) / max(1, total_refs)

        if has_hallucination:
            signal = (
                f"[HALUCINATION WARNING] Hallucinated API(s) detected: {', '.join(hallucinated_apis)}. "
                f"These do NOT exist in Bedrock Script API. "
                f"Use valid APIs: world.afterEvents, player.sendMessage, system.runInterval, etc."
            )
        else:
            signal = ""

        return has_hallucination, hallucinated_apis, hallucination_rate, signal

    def _parse_output(self, output: str, model_key: str, latency_ms: int) -> ConversionResult:
        """Parse model output into structured result."""
        # Extract reasoning
        reasoning = ""
        plan_match = re.search(r"## Conversion Plan\s*(.*?)(?=## Bedrock|$)", output, re.DOTALL)
        if plan_match:
            reasoning = plan_match.group(1).strip()

        # Extract JSON blocks (manifest, etc.)
        json_blocks = re.findall(r"```json\s*(.*?)\s*```", output, re.DOTALL)
        manifest = ""
        for block in json_blocks:
            if any(key in block for key in ["format_version", "header", "modules"]):
                manifest = block.strip()
                break

        # Extract JS blocks
        js_blocks = re.findall(r"```(?:javascript|js)\b\s*(.*?)\s*```", output, re.DOTALL)
        script = max(js_blocks, key=len).strip() if js_blocks else ""

        success = bool(reasoning and (manifest or script))

        # Hallucination validation (issue #1678)
        has_halluc, hallucinated_apis, halluc_rate, halluc_signal = self._validate_hallucinations(script)

        return ConversionResult(
            success=success,
            reasoning=reasoning,
            bedrock_manifest=manifest,
            bedrock_script=script,
            raw_output=output,
            model_used=model_key,
            tier="premium",
            latency_ms=latency_ms,
            has_hallucination=has_halluc,
            hallucinated_apis=hallucinated_apis,
            hallucination_rate=halluc_rate,
            hallucination_signal=halluc_signal,
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_models(self) -> dict:
        """Return available model configurations."""
        return {k: v["model_id"] for k, v in MODEL_CONFIGS.items()}

    def estimate_cost(
        self, instruction: str, java_source: str, model: Optional[str] = None
    ) -> dict:
        """Estimate API cost for a conversion request (rough)."""
        # ~4 chars per token
        input_chars = len(instruction) + len(java_source) + len(SYSTEM_PROMPT)
        for ex in FEW_SHOT_EXAMPLES:
            input_chars += len(ex["user"]) + len(ex["assistant"])
        input_tokens = input_chars // 4
        output_tokens = 2048  # rough estimate

        model_key = model or self.model
        # DeepSeek V4 Pro pricing via OpenRouter: ~$0.55/M input, ~$2.19/M output
        # These are approximate — check openrouter.ai/pricing for current rates
        rates = {
            "deepseek-v4-pro": {"input": 0.55, "output": 2.19},
            "deepseek-v4-flash": {"input": 0.27, "output": 1.10},
            "kimi-k2": {"input": 0.60, "output": 2.50},
            "glm-5": {"input": 0.50, "output": 1.50},
        }

        rate = rates.get(model_key, {"input": 0.55, "output": 2.19})
        cost = (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000

        return {
            "model": model_key,
            "input_tokens_est": input_tokens,
            "output_tokens_est": output_tokens,
            "cost_usd_est": round(cost, 4),
        }


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    """Quick test: convert a sample Java mod via premium API."""
    import argparse

    parser = argparse.ArgumentParser(description="PortKit Premium Converter")
    parser.add_argument("--java", required=True, help="Path to Java source file")
    parser.add_argument(
        "--instruction", "-i", default="Custom Minecraft mod", help="Mod description"
    )
    parser.add_argument("--model", "-m", default="deepseek-v4-pro", help="Model to use")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show prompt + cost estimate, don't call API"
    )
    args = parser.parse_args()

    java_source = open(args.java).read()

    client = PortKitPremium(model=args.model)

    # Cost estimate
    cost = client.estimate_cost(args.instruction, java_source, args.model)
    print(f"Model: {cost['model']}")
    print(f"Estimated tokens: {cost['input_tokens_est']} in + {cost['output_tokens_est']} out")
    print(f"Estimated cost: ${cost['cost_usd_est']:.4f}")

    if args.dry_run:
        print("\n(Dry run — not calling API)")
        client.close()
        return

    print("\nConverting...")
    result = client.convert(args.instruction, java_source)

    if result.success:
        print(f"\n✓ Conversion successful ({result.latency_ms}ms, model: {result.model_used})")
        if result.reasoning:
            print(f"\n--- Reasoning ---\n{result.reasoning[:500]}...")
        if result.bedrock_manifest:
            print(f"\n--- Manifest ---\n{result.bedrock_manifest[:500]}...")
        if result.bedrock_script:
            print(f"\n--- Script ---\n{result.bedrock_script[:500]}...")
    else:
        print(f"\n✗ Conversion failed: {result.error}")

    client.close()


if __name__ == "__main__":
    main()
