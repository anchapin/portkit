#!/usr/bin/env python3
"""
Hallucination Catalog — PortKit AI Engine Training Data
=======================================================
Catalogs hallucination patterns from reward code for synthetic data generation.

Patterns sourced from:
- grpo8_train.py: count_hallucinated_apis() — 4-tier penalty system (#1648-1650)
- reward_v2.py: score_js_api_correctness() — hallucinated_patterns list

Usage:
    from hallucination_catalog import HALLUCINATION_PATTERNS, HallucinationType
    catalog = HallucinationCatalog()
    findings = catalog.detect(code)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Pattern


class HallucinationType(Enum):
    """Hallucination severity classification."""

    HARD = "hard"  # Completely fabricated APIs (Tier 1, #1648)
    SEMANTIC = "semantic"  # Valid syntax, invalid semantics (#1647)
    LINGERING = "lingering"  # References to removed/deprecated APIs
    STRUCTURAL = "structural"  # Incorrect manifest structure patterns


@dataclass
class HallucinationPattern:
    """A single hallucination pattern with metadata."""

    id: str
    pattern: str
    regex: Pattern
    Hallucination_type: HallucinationType
    penalty: float
    description: str
    examples: List[str] = field(default_factory=list)
    fixed_by: List[str] = field(default_factory=list)  # Issue references


@dataclass
class HallucinationFinding:
    """A detected hallucination in code."""

    pattern_id: str
    matched_text: str
    line_number: int
    context: str
    hallucination_type: HallucinationType
    penalty: float


class HallucinationCatalog:
    """Catalog of known hallucination patterns for Bedrock API conversion."""

    # =========================================================================
    # TIER 1: Hard hallucinations — NEVER valid in Bedrock (#1648)
    # =========================================================================
    HARD_HALLUCINATIONS: List[HallucinationPattern] = [
        # Java-mod-style fake classes
        HallucinationPattern(
            id="hard_001",
            pattern=r"\bServerPlayerAPI\b",
            regex=re.compile(r"\bServerPlayerAPI\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Java-mod-style fake class — ServerPlayerAPI does not exist in Bedrock",
            examples=["ServerPlayerAPI.getPlayer(id)", "ServerPlayerAPI.create()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_002",
            pattern=r"\bServerPlayer\b",
            regex=re.compile(r"\bServerPlayer\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Java-mod-style class — use Player from @minecraft/server",
            examples=["ServerPlayer.sendMessage()", "new ServerPlayer()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_003",
            pattern=r"\bPlayerAPI\b",
            regex=re.compile(r"\bPlayerAPI\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent API — Bedrock has no PlayerAPI class",
            examples=["PlayerAPI.getAllPlayers()", "PlayerAPI.create()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_004",
            pattern=r"\bWorldEvent\b",
            regex=re.compile(r"\bWorldEvent\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent event class — use world.afterEvents or world.beforeEvents",
            examples=["WorldEvent.listen()", "WorldEvent.broadcast()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_005",
            pattern=r"\bmodEventBus\b",
            regex=re.compile(r"\bmodEventBus\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Java mod loader pattern — Bedrock uses different event system",
            examples=["modEventBus.register()", "modEventBus.listen()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_006",
            pattern=r"\bBlockEntityAPI\b",
            regex=re.compile(r"\bBlockEntityAPI\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent class — use world.getBlock() and Block properties",
            examples=["BlockEntityAPI.get()", "BlockEntityAPI.set()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_007",
            pattern=r"\bEntityPlayerAPI\b",
            regex=re.compile(r"\bEntityPlayerAPI\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Hybrid Java/Bedrock class that doesn't exist",
            examples=["EntityPlayerAPI.spawn()", "EntityPlayerAPI.getEntities()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_008",
            pattern=r"\bWorldAPI\b",
            regex=re.compile(r"\bWorldAPI\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent wrapper class — use world directly",
            examples=["WorldAPI.getInstance()", "WorldAPI.createWorld()"],
            fixed_by=["#1648"],
        ),
        # Non-existent require/define patterns
        HallucinationPattern(
            id="hard_009",
            pattern=r'require\(["\']@minecraft/server["\']',
            regex=re.compile(r'require\(["\']@minecraft/server["\']'),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="CommonJS require — Bedrock uses ES6 import syntax",
            examples=['require("@minecraft/server")', 'require("@minecraft/server-ui")'],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_010",
            pattern=r"\bregisterMod\(",
            regex=re.compile(r"\bregisterMod\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Java mod loader pattern — Bedrock uses manifest.json",
            examples=["registerMod(myMod)", "registerMod('modId', config)"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_011",
            pattern=r"\bdefineMod\(",
            regex=re.compile(r"\bdefineMod\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent mod definition API",
            examples=["defineMod('my_mod', { init: fn })", "defineMod(config)"],
            fixed_by=["#1648"],
        ),
        # Non-existent methods on known classes
        HallucinationPattern(
            id="hard_012",
            pattern=r"\.createLightningBolt\(",
            regex=re.compile(r"\.createLightningBolt\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent world method — use dimension.spawnEntity()",
            examples=["world.createLightningBolt(location)", "world.createLightningBolt(player)"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_013",
            pattern=r"\.spawnLightning\(",
            regex=re.compile(r"\.spawnLightning\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent spawn method",
            examples=["dimension.spawnLightning(loc)", "world.spawnLightning()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_014",
            pattern=r"\.registerEvent\(",
            regex=re.compile(r"\.registerEvent\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Wrong event registration — use .subscribe() on afterEvents/beforeEvents",
            examples=["player.registerEvent('tick', handler)", "world.registerEvent('tick')"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_015",
            pattern=r"\.registerServerEvent\(",
            regex=re.compile(r"\.registerServerEvent\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent server event API",
            examples=[
                "system.registerServerEvent('start', handler)",
                "world.registerServerEvent()",
            ],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_016",
            pattern=r"\.onServerStart\(",
            regex=re.compile(r"\.onServerStart\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent lifecycle hook — use WorldInitializeEvent or tick events",
            examples=["world.onServerStart(() => {})", "system.onServerStart(run)"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_017",
            pattern=r"\.onServerStop\(",
            regex=re.compile(r"\.onServerStop\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent lifecycle hook",
            examples=["world.onServerStop(() => {})", "system.onServerStop(handler)"],
            fixed_by=["#1648"],
        ),
        # Non-existent static accessors
        HallucinationPattern(
            id="hard_018",
            pattern=r"event\.level\.",
            regex=re.compile(r"event\.level\.", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent event property chain — use event.source or event.dimension",
            examples=["event.level.createBlock()", "event.level.getEntities()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_019",
            pattern=r"server\.getWorld\(",
            regex=re.compile(r"server\.getWorld\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent server method — use world.getDimension()",
            examples=["server.getWorld('overworld')", "server.getWorld('nether')"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_020",
            pattern=r"getServer\(\)\.",
            regex=re.compile(r"getServer\(\)\.", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent static accessor — use system or world directly",
            examples=["getServer().getWorld()", "getServer().sendMessage()"],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_021",
            pattern=r"Server\.getInstance\(\)",
            regex=re.compile(r"Server\.getInstance\(\)", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Java singleton pattern — Bedrock has no Server singleton",
            examples=["Server.getInstance().getWorld()", "Server.getInstance().broadcast()"],
            fixed_by=["#1648"],
        ),
        # Non-existent property chains
        HallucinationPattern(
            id="hard_022",
            pattern=r"\.getTileEntity\(\).*\.getInventory\(",
            regex=re.compile(r"\.getTileEntity\(\)[^)]*\.getInventory\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Chained method that doesn't exist in Bedrock API",
            examples=[
                "block.getTileEntity().getInventory()",
                "chest.getTileEntity().getInventory()",
            ],
            fixed_by=["#1648"],
        ),
        HallucinationPattern(
            id="hard_023",
            pattern=r"world\.setBlock\(.*\.getPosition\(",
            regex=re.compile(r"world\.setBlock\([^)]*\.getPosition\(", re.IGNORECASE),
            Hallucination_type=HallucinationType.HARD,
            penalty=-0.3,
            description="Non-existent block placement API",
            examples=[
                "world.setBlock(location.getPosition())",
                "world.setBlock(pos.getPosition())",
            ],
            fixed_by=["#1648"],
        ),
    ]

    # =========================================================================
    # TIER 2: Semantic hallucinations — valid syntax, wrong semantics (#1647)
    # =========================================================================
    SEMANTIC_HALLUCINATIONS: List[HallucinationPattern] = [
        HallucinationPattern(
            id="sem_001",
            pattern=r"import\s+\{[^}]*\bLightningBoltEvent\b[^}]*\}\s+from\s+['\"]@minecraft/server['\"]",
            regex=re.compile(
                r"import\s+\{[^}]*\bLightningBoltEvent\b[^}]*\}\s+from\s+['\"]@minecraft/server['\"]",
                re.IGNORECASE,
            ),
            Hallucination_type=HallucinationType.SEMANTIC,
            penalty=-0.15,
            description="Non-existent event class — LightningBoltEvent doesn't exist",
            examples=[
                "import { LightningBoltEvent } from '@minecraft/server'",
                "LightningBoltEvent.subscribe()",
            ],
            fixed_by=["#1647"],
        ),
        HallucinationPattern(
            id="sem_002",
            pattern=r"import\s+\{[^}]*\bPlayerEvent\b[^}]*\}\s+from\s+['\"]@minecraft/server['\"]",
            regex=re.compile(
                r"import\s+\{[^}]*\bPlayerEvent\b[^}]*\}\s+from\s+['\"]@minecraft/server['\"]",
                re.IGNORECASE,
            ),
            Hallucination_type=HallucinationType.SEMANTIC,
            penalty=-0.15,
            description="Wrong event namespace — use PlayerAfterEvents/PlayerBeforeEvents",
            examples=["import { PlayerEvent } from '@minecraft/server'", "PlayerEvent.subscribe()"],
            fixed_by=["#1647"],
        ),
        HallucinationPattern(
            id="sem_003",
            pattern=r"import\s+\{[^}]*\bWorldEvent\b[^}]*\}\s+from\s+['\"]@minecraft/server['\"]",
            regex=re.compile(
                r"import\s+\{[^}]*\bWorldEvent\b[^}]*\}\s+from\s+['\"]@minecraft/server['\"]",
                re.IGNORECASE,
            ),
            Hallucination_type=HallucinationType.SEMANTIC,
            penalty=-0.15,
            description="Non-existent event class — use WorldAfterEvents or WorldBeforeEvents",
            examples=["import { WorldEvent } from '@minecraft/server'", "WorldEvent.listen()"],
            fixed_by=["#1647"],
        ),
        HallucinationPattern(
            id="sem_004",
            pattern=r"\bPlayerEvent\b",
            regex=re.compile(r"\bPlayerEvent\b", re.IGNORECASE),
            Hallucination_type=HallucinationType.SEMANTIC,
            penalty=-0.15,
            description="Ambiguous event class — specify PlayerAfterEvents or PlayerBeforeEvents",
            examples=["world.onPlayerEvent('tick', handler)", "PlayerEvent.broadcast()"],
            fixed_by=["#1647"],
        ),
    ]

    # =========================================================================
    # TIER 3: Lingering hallucinations — deprecated/removed patterns
    # =========================================================================
    LINGERING_HALLUCINATIONS: List[HallucinationPattern] = [
        HallucinationPattern(
            id="ling_001",
            pattern=r"\.register\(\s*\w+\s*,\s*\w+\s*\)",
            regex=re.compile(r"\.register\(\s*\w+\s*,\s*\w+\s*\)", re.IGNORECASE),
            Hallucination_type=HallucinationType.LINGERING,
            penalty=-0.1,
            description="Old event registration pattern — use .subscribe() instead",
            examples=["events.tick.register(handler)", "events.blockPlace.register(fn)"],
            fixed_by=["#1647"],
        ),
        HallucinationPattern(
            id="ling_002",
            pattern=r"import\s+\{[^}]*\}\s+from\s+['\"]minecraft/server['\"]",
            regex=re.compile(
                r"import\s+\{[^}]*\}\s+from\s+['\"]minecraft/server['\"]", re.IGNORECASE
            ),
            Hallucination_type=HallucinationType.LINGERING,
            penalty=-0.1,
            description="Wrong module path — must be '@minecraft/server' (with @)",
            examples=[
                'import { world } from "minecraft/server"',
                "import { player } from 'minecraft/server'",
            ],
            fixed_by=["#1647"],
        ),
    ]

    # Valid Bedrock classes for semantic validation (#1647)
    VALID_MINECRAFT_CLASSES: set = {
        # Core classes
        "world",
        "system",
        "player",
        "players",
        "dimension",
        "Block",
        "BlockPermutation",
        "BlockState",
        "ItemStack",
        "Entity",
        "EntityInventoryComponent",
        "Player",
        "Container",
        "ItemEnchants",
        "Enchantment",
        "EnchantmentType",
        "Vector3",
        "BoundingBox",
        "Location",
        "WorldAfterEvents",
        "WorldBeforeEvents",
        "WorldInitializeEvent",
        "PlayerAfterEvents",
        "PlayerBeforeEvents",
        "EntityAfterEvents",
        "EntityBeforeEvents",
        "SystemEvents",
        "TickEvent",
        "LoadEvent",
        "PropertyRegistry",
        "BoolSignProperty",
        "IntSignProperty",
        "MessageChannel",
        "RawMessage",
        "RawMessageWithArgs",
        "Scoreboard",
        "Objective",
        "ScoreboardIdentity",
        "BossBar",
        "BossBarDisplay",
        "ActionEventData",
        "IBlock",
        "IInventory",
        "IEntity",
        "IPlayer",
        # Event classes
        "BlockEvent",
        "BlockHitEvent",
        "BlockPlaceEvent",
        "BlockDestroyEvent",
        "EntityEvent",
        "PlayerSpawnEvent",
        "ItemUseEvent",
        "ItemUseOnEvent",
        "ProjectileHitEvent",
        "ExplosionEvent",
        "EntityDieEvent",
        "EntityHealthChangedEvent",
        "PlayerDimensionChangeEvent",
        # Component classes
        "MinecraftEntityTypes",
        "MinecraftBlockTypes",
        "MinecraftItemTypes",
        # Other
        "DynamicPropertiesDefinition",
        "PropertyDefinition",
    }

    @property
    def all_patterns(self) -> List[HallucinationPattern]:
        """Get all hallucination patterns."""
        return (
            self.HARD_HALLUCINATIONS + self.SEMANTIC_HALLUCINATIONS + self.LINGERING_HALLUCINATIONS
        )

    def detect(self, code: str) -> List[HallucinationFinding]:
        """Detect hallucinations in code."""
        findings = []
        lines = code.split("\n")

        for pattern in self.all_patterns:
            for line_num, line in enumerate(lines, 1):
                matches = pattern.regex.finditer(line)
                for match in matches:
                    findings.append(
                        HallucinationFinding(
                            pattern_id=pattern.id,
                            matched_text=match.group(),
                            line_number=line_num,
                            context=line.strip(),
                            hallucination_type=pattern.Hallucination_type,
                            penalty=pattern.penalty,
                        )
                    )

        return findings

    def count_total_penalty(self, code: str) -> float:
        """Calculate total hallucination penalty for code."""
        findings = self.detect(code)
        hard_count = sum(1 for f in findings if f.hallucination_type == HallucinationType.HARD)
        lying_penalty = -0.2 if hard_count > 0 and self._has_minecraft_import(code) else 0.0
        binary_penalty = -0.2 if hard_count > 0 else 0.0

        total = sum(f.penalty for f in findings) + lying_penalty + binary_penalty
        return max(-1.0, min(0.0, total))

    def _has_minecraft_import(self, code: str) -> bool:
        """Check if code imports @minecraft/server."""
        return bool(re.search(r"from\s+['\"]@minecraft/server['\"]", code))

    def get_detection_report(self, code: str) -> dict:
        """Generate a detailed detection report."""
        findings = self.detect(code)
        return {
            "total_findings": len(findings),
            "by_type": {
                "hard": sum(1 for f in findings if f.hallucination_type == HallucinationType.HARD),
                "semantic": sum(
                    1 for f in findings if f.hallucination_type == HallucinationType.SEMANTIC
                ),
                "lingering": sum(
                    1 for f in findings if f.hallucination_type == HallucinationType.LINGERING
                ),
            },
            "total_penalty": self.count_total_penalty(code),
            "findings": [
                {
                    "id": f.pattern_id,
                    "line": f.line_number,
                    "type": f.hallucination_type.value,
                    "penalty": f.penalty,
                    "matched": f.matched_text,
                    "context": f.context,
                }
                for f in sorted(findings, key=lambda x: x.line_number)
            ],
        }


# Export singleton for convenience
HALLUCINATION_CATALOG = HallucinationCatalog()
HALLUCINATION_PATTERNS = HALLUCINATION_CATALOG.all_patterns
