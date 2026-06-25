"""
Vendor Translation Formalism for Java → Bedrock Construct Mapping.

Applies the mathematical formulation of the vendor-translation problem from
industrial PLC code translation (Ladder Logic → Siemens/Rockwell) to
formalize PortKit's Java Forge/Fabric → Bedrock Scripting API construct mapping.

The formalism introduces a Canonical IR (Intermediate Representation) as an
explicit middle layer between source and target dialects, enabling:
- Principled handling of no-direct-equivalent constructs
- Explicit semantic delta documentation for approximate mappings
- Systematic completeness checking across construct categories
- Grounded semantics for "semantically correct" conversion

Architecture:
  Vendor Dialect A (Java)  →  Canonical IR  →  Vendor Dialect B (Bedrock)
         Parser                      ↑              Generator
                                   Maps

Paper reference: Ladder Logic Translation using Large Language Models
in Industrial Automation (arxiv.org/abs/2605.31458)
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

# Expose public types at package level
__all__ = [
    "ConstructCategory",
    "SemanticEquivalence",
    "IRConstruct",
    "IRParameter",
    "EventHandler",
    "TickFunction",
    "BlockInteraction",
    "BlockBreak",
    "EntitySpawn",
    "MappingDelta",
    "MappingEntry",
    "FormalMappingTable",
    "JavaDialectParser",
    "BedrockDialectGenerator",
    "VendorFormalism",
]


# ---------------------------------------------------------------------------
# Canonical IR — Vendor-Neutral Construct Representations
# ---------------------------------------------------------------------------


class ConstructCategory(Enum):
    """High-level categories of constructs, used for MMSD tagging."""

    EVENT = auto()
    TICK = auto()
    BLOCK_INTERACTION = auto()
    BLOCK_BREAK = auto()
    ENTITY_SPAWN = auto()
    ITEM_USE = auto()
    COMMAND = auto()
    DATA_STORAGE = auto()
    PLAYER_PROPERTY = auto()
    RECIPE = auto()
    UNKNOWN = auto()


class SemanticEquivalence(Enum):
    """Classification of how well a construct maps to its canonical form."""

    DIRECT = auto()
    APPROXIMATE = auto()
    NO_EQUIVALENT = auto()
    VENDOR_SPECIFIC = auto()


@dataclass(frozen=True)
class IRParameter:
    """A named, typed parameter in a canonical construct."""

    name: str
    type: str
    description: str = ""


@dataclass(frozen=True)
class IRConstruct(ABC):
    """
    Base class for all Canonical IR constructs.

    Each IRConstruct is a vendor-neutral representation of a Minecraft
    modding concept. Subclasses carry the semantic information needed to
    generate equivalent code in any target dialect.
    """

    canonical_name: str
    category: ConstructCategory

    @abstractmethod
    def semantic_summary(self) -> str:
        """Human-readable summary of what this construct represents."""

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for inspection / MMSD annotation."""


@dataclass(frozen=True)
class EventHandler(IRConstruct):
    """
    Canonical representation of an event handler.

    Java equivalent:  @SubscribeEvent methods (any Event subclass)
    Bedrock equivalent: world.afterEvents.* / world.beforeEvents.* subscribe()

    Parameters
    ----------
        event_type: Canonical event name (e.g., "player_interact", "block_break")
        subscribe_lambda_body: Statements to run when the event fires
        is_after: True = afterEvents (fire after state change),
                  False = beforeEvents (fire before state change, cancellable)
    """

    event_type: str
    subscribe_lambda_body: str
    is_after: bool = True
    semantic_equivalence: SemanticEquivalence = field(default=SemanticEquivalence.DIRECT)

    def semantic_summary(self) -> str:
        return (
            f"Run '{self.subscribe_lambda_body}' whenever "
            f"'{self.event_type}' event fires (is_after={self.is_after})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "category": self.category.name,
            "construct_type": "EventHandler",
            "event_type": self.event_type,
            "is_after": self.is_after,
            "semantic_equivalence": self.semantic_equivalence.name,
            "subscribe_lambda_body": self.subscribe_lambda_body,
        }


@dataclass(frozen=True)
class TickFunction(IRConstruct):
    """
    Canonical representation of a recurring tick-frequency callback.

    Java equivalent:  BlockEntity.tick() / Level.tick() scheduled update
    Bedrock equivalent: system.runInterval(() => { ... }, intervalTicks)

    Parameters
    ----------
        interval_ticks: Number of ticks between invocations (1 = every tick)
        tick_body: Statements to run each interval
        description: What the tick function does (for documentation)
    """

    interval_ticks: int = 1
    tick_body: str = ""
    semantic_equivalence: SemanticEquivalence = SemanticEquivalence.APPROXIMATE

    def semantic_summary(self) -> str:
        return (
            f"Run '{self.tick_body}' every {self.interval_ticks} tick(s) "
            f"({20 / self.interval_ticks:.1f} Hz approx)"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "category": self.category.name,
            "construct_type": "TickFunction",
            "interval_ticks": self.interval_ticks,
            "tick_body": self.tick_body,
            "semantic_equivalence": self.semantic_equivalence.name,
        }


@dataclass(frozen=True)
class BlockInteraction(IRConstruct):
    """
    Canonical representation of a player-block interaction (right-click).

    Java equivalent:  PlayerInteractEvent / @SubscribeEvent on RightClickBlock
    Bedrock equivalent: world.afterEvents.playerInteractWithBlock.subscribe(...)

    Parameters
    ----------
        trigger_item: Item type that triggers the interaction (None = any)
        target_block: Block type being interacted with
        cancelable: Whether the event can be cancelled in the original
        interaction_body: Statements to execute
    """

    trigger_item: Optional[str] = None
    target_block: Optional[str] = None
    cancelable: bool = True
    interaction_body: str = ""
    semantic_equivalence: SemanticEquivalence = SemanticEquivalence.DIRECT

    def semantic_summary(self) -> str:
        item = self.trigger_item or "any item"
        block = self.target_block or "any block"
        return f"Player right-clicks {block} holding {item}: {self.interaction_body}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "category": self.category.name,
            "construct_type": "BlockInteraction",
            "trigger_item": self.trigger_item,
            "target_block": self.target_block,
            "cancelable": self.cancelable,
            "interaction_body": self.interaction_body,
            "semantic_equivalence": self.semantic_equivalence.name,
        }


@dataclass(frozen=True)
class BlockBreak(IRConstruct):
    """
    Canonical representation of a block-break event.

    Java equivalent:  BlockEvent.BreakEvent / PlayerDestroyBlockEvent
    Bedrock equivalent: world.afterEvents.blockBreak.subscribe(...)

    Parameters
    ----------
        block_type: Block being broken (None = any)
        drop_xp: Whether XP is dropped
        break_body: Statements to execute
    """

    block_type: Optional[str] = None
    drop_xp: bool = False
    break_body: str = ""
    semantic_equivalence: SemanticEquivalence = SemanticEquivalence.DIRECT

    def semantic_summary(self) -> str:
        block = self.block_type or "any block"
        return f"Player breaks {block}: {self.break_body}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "category": self.category.name,
            "construct_type": "BlockBreak",
            "block_type": self.block_type,
            "drop_xp": self.drop_xp,
            "break_body": self.break_body,
            "semantic_equivalence": self.semantic_equivalence.name,
        }


@dataclass(frozen=True)
class EntitySpawn(IRConstruct):
    """
    Canonical representation of an entity spawn / world-join event.

    Java equivalent:  EntityJoinLevelEvent / subscribe method on mod events
    Bedrock equivalent: world.afterEvents.entitySpawn.subscribe(...)

    Parameters
    ----------
        entity_type: The entity type being spawned
        spawn_body: Statements to run when entity spawns
    """

    entity_type: Optional[str] = None
    spawn_body: str = ""
    semantic_equivalence: SemanticEquivalence = SemanticEquivalence.DIRECT

    def semantic_summary(self) -> str:
        entity = self.entity_type or "any entity"
        return f"Entity {entity} spawns: {self.spawn_body}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "category": self.category.name,
            "construct_type": "EntitySpawn",
            "entity_type": self.entity_type,
            "spawn_body": self.spawn_body,
            "semantic_equivalence": self.semantic_equivalence.name,
        }


# ---------------------------------------------------------------------------
# Formal Mapping Table Entries
# ---------------------------------------------------------------------------


@dataclass
class MappingDelta:
    """
    Documents the semantic difference for APPROXIMATE / NO_EQUIVALENT mappings.

    This is the key artifact for "principled no-equivalent handling" —
    instead of leaving semantic approximations implicit, we formalize them here.
    """

    delta_type: str
    java_behavior: str
    bedrock_behavior: str
    workaround: str
    mmd_tag: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "delta_type": self.delta_type,
            "java_behavior": self.java_behavior,
            "bedrock_behavior": self.bedrock_behavior,
            "workaround": self.workaround,
            "mmd_tag": self.mmd_tag,
        }


@dataclass
class MappingEntry:
    """
    A single entry in the formal construct mapping table.

    Maps a Java construct → Canonical IR → Bedrock construct with full
    provenance, confidence, and semantic delta documentation.
    """

    java_construct_id: str
    canonical_construct: IRConstruct
    bedrock_js_pattern: str
    confidence: float
    equivalence: SemanticEquivalence
    deltas: List[MappingDelta] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    requires_manual_review: bool = False
    category: ConstructCategory = ConstructCategory.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "java_construct_id": self.java_construct_id,
            "canonical_construct": self.canonical_construct.to_dict(),
            "bedrock_js_pattern": self.bedrock_js_pattern,
            "confidence": self.confidence,
            "equivalence": self.equivalence.name,
            "deltas": [d.to_dict() for d in self.deltas],
            "limitations": self.limitations,
            "requires_manual_review": self.requires_manual_review,
            "category": self.category.name,
        }


# ---------------------------------------------------------------------------
# Formal Mapping Table
# ---------------------------------------------------------------------------


class FormalMappingTable:
    """
    Typed table of JavaConstruct → CanonicalIR → BedrockConstruct mappings.

    This is the core artifact of the formalism — all supported construct
    types are registered here with their canonical form, Bedrock equivalent,
    confidence scores, and explicit semantic deltas.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, MappingEntry] = {}
        self._canonical_to_entry: Dict[str, MappingEntry] = {}
        self._initialize_table()

    def _initialize_table(self) -> None:
        self._add_event_handler_mappings()
        self._add_tick_function_mappings()
        self._add_block_interaction_mappings()
        self._add_block_break_mappings()
        self._add_entity_spawn_mappings()
        for entry in self._entries.values():
            self._canonical_to_entry[entry.canonical_construct.canonical_name] = entry

    # -- Event Handler Mappings ----------------------------------------------

    def _add_event_handler_mappings(self) -> None:
        self._entries["java_player_interact"] = MappingEntry(
            java_construct_id="java_player_interact",
            canonical_construct=EventHandler(
                canonical_name="player_interact",
                category=ConstructCategory.EVENT,
                event_type="player_interact_block",
                subscribe_lambda_body="// interact handler",
                is_after=True,
                semantic_equivalence=SemanticEquivalence.DIRECT,
            ),
            bedrock_js_pattern="""\
world.afterEvents.playerInteractWithBlock.subscribe((event) => {
    const player = event.player;
    const block = event.block;
    const dimension = player.dimension;
    // interact handler
});""",
            confidence=0.80,
            equivalence=SemanticEquivalence.DIRECT,
            limitations=[
                "@SubscribeEvent → world.afterEvents.subscribe",
                "Event object properties differ between Java and Bedrock",
                "Client/server split needs explicit handling",
                "Cancellability: Java event.setCanceled() has no direct Bedrock equivalent",
            ],
            requires_manual_review=True,
            category=ConstructCategory.EVENT,
        )

        self._entries["java_entity_join"] = MappingEntry(
            java_construct_id="java_entity_join",
            canonical_construct=EntitySpawn(
                canonical_name="entity_spawn",
                category=ConstructCategory.ENTITY_SPAWN,
                entity_type=None,
                spawn_body="// entity spawn handler",
                semantic_equivalence=SemanticEquivalence.DIRECT,
            ),
            bedrock_js_pattern="""\
world.afterEvents.entitySpawn.subscribe((event) => {
    const entity = event.entity;
    // entity spawn handler
});""",
            confidence=0.80,
            equivalence=SemanticEquivalence.DIRECT,
            limitations=[
                "EntityJoinLevelEvent → entitySpawn afterEvent",
                "Client-side spawn events have limited Bedrock access",
            ],
            requires_manual_review=True,
            category=ConstructCategory.ENTITY_SPAWN,
        )

    # -- Tick Function Mappings ----------------------------------------------

    def _add_tick_function_mappings(self) -> None:
        self._entries["java_ticking_tile"] = MappingEntry(
            java_construct_id="java_ticking_tile",
            canonical_construct=TickFunction(
                canonical_name="block_tick",
                category=ConstructCategory.TICK,
                interval_ticks=1,
                tick_body="// tick handler",
                semantic_equivalence=SemanticEquivalence.APPROXIMATE,
            ),
            bedrock_js_pattern="""\
import {{ system }} from "@minecraft/server";

system.runInterval(() => {{
    // tick handler
}}, {interval_ticks}); // {frequency_hz:.1f} Hz""",
            confidence=0.65,
            equivalence=SemanticEquivalence.APPROXIMATE,
            deltas=[
                MappingDelta(
                    delta_type="EXECUTION_MODEL",
                    java_behavior="Minecraft tick loop calls BlockEntity.tick() "
                    "synchronously per-block in a deterministic per-tick order",
                    bedrock_behavior="system.runInterval() is a best-effort timer "
                    "running at ~20 Hz with no guaranteed tick ordering",
                    workaround="Use a ticking entity component (minecraft:tick) or "
                    "accept that tick ordering is not preserved",
                    mmd_tag="TICK_ORDERING_NON_DETERMINISTIC",
                ),
                MappingDelta(
                    delta_type="SCALABILITY",
                    java_behavior="Tick is called per-block entity only for loaded chunks",
                    bedrock_behavior="runInterval callback runs globally — all block "
                    "positions must be iterated explicitly",
                    workaround="Track custom block positions and filter per-tick",
                    mmd_tag="TICK_SCOPE_GLOBAL",
                ),
            ],
            limitations=[
                "No built-in per-block tick system in Bedrock",
                "Must use Script API system.runInterval",
                "Performance: iterating all block positions is expensive",
                "Tick ordering is not preserved",
            ],
            requires_manual_review=True,
            category=ConstructCategory.TICK,
        )

    # -- Block Interaction Mappings -------------------------------------------

    def _add_block_interaction_mappings(self) -> None:
        self._entries["java_block_right_click"] = MappingEntry(
            java_construct_id="java_block_right_click",
            canonical_construct=BlockInteraction(
                canonical_name="block_right_click",
                category=ConstructCategory.BLOCK_INTERACTION,
                trigger_item=None,
                target_block=None,
                cancelable=True,
                interaction_body="// right-click handler",
                semantic_equivalence=SemanticEquivalence.DIRECT,
            ),
            bedrock_js_pattern="""\
world.afterEvents.playerInteractWithBlock.subscribe((event) => {{
    const player = event.player;
    const block = event.block;
    const item = event.itemStack;

    // right-click handler
}});""",
            confidence=0.80,
            equivalence=SemanticEquivalence.DIRECT,
            limitations=[
                "Java: event.setCanceled(true) prevents block action (e.g., door open)",
                "Bedrock: cannot prevent default block action via Script API",
                "Client-side events in Bedrock are very limited",
            ],
            requires_manual_review=True,
            category=ConstructCategory.BLOCK_INTERACTION,
        )

    # -- Block Break Mappings ------------------------------------------------

    def _add_block_break_mappings(self) -> None:
        self._entries["java_block_break"] = MappingEntry(
            java_construct_id="java_block_break",
            canonical_construct=BlockBreak(
                canonical_name="block_break",
                category=ConstructCategory.BLOCK_BREAK,
                block_type=None,
                drop_xp=False,
                break_body="// block break handler",
                semantic_equivalence=SemanticEquivalence.DIRECT,
            ),
            bedrock_js_pattern="""\
world.afterEvents.blockBreak.subscribe((event) => {{
    const player = event.player;
    const block = event.block;
    const brokenBlockPermutation = event.brokenBlockPermutation;

    // block break handler
}});""",
            confidence=0.85,
            equivalence=SemanticEquivalence.DIRECT,
            deltas=[
                MappingDelta(
                    delta_type="XP_DROPS",
                    java_behavior="event.setExpToDrop(n) controls XP drops directly",
                    bedrock_behavior="XP must be awarded via player.giveExperience() "
                    "manually after the event",
                    workaround="Track XP amount in a variable and award after event",
                    mmd_tag="BREAK_XP_MANUAL_AWARD",
                ),
            ],
            limitations=[
                "BlockBreakEvent → blockBreak afterEvent",
                "XP dropping requires separate player.giveExperience() call",
                "blockFace (which face was broken) is not available in Bedrock",
            ],
            requires_manual_review=True,
            category=ConstructCategory.BLOCK_BREAK,
        )

    # -- Entity Spawn Mappings -----------------------------------------------

    def _add_entity_spawn_mappings(self) -> None:
        self._entries["java_entity_spawn"] = MappingEntry(
            java_construct_id="java_entity_spawn",
            canonical_construct=EntitySpawn(
                canonical_name="entity_spawn",
                category=ConstructCategory.ENTITY_SPAWN,
                entity_type=None,
                spawn_body="// entity spawn handler",
                semantic_equivalence=SemanticEquivalence.DIRECT,
            ),
            bedrock_js_pattern="""\
world.afterEvents.entitySpawn.subscribe((event) => {{
    const entity = event.entity;
    // entity spawn handler
}});""",
            confidence=0.80,
            equivalence=SemanticEquivalence.DIRECT,
            limitations=[
                "EntityJoinLevelEvent → entitySpawn afterEvent",
                "Bedrock has no equivalent for EntityConstructing or init methods",
                "Client-side entity spawn events are very limited",
            ],
            requires_manual_review=True,
            category=ConstructCategory.ENTITY_SPAWN,
        )

    # -- Public API ----------------------------------------------------------

    def get(self, java_construct_id: str) -> Optional[MappingEntry]:
        return self._entries.get(java_construct_id)

    def get_by_canonical_name(self, canonical_name: str) -> Optional[MappingEntry]:
        return self._canonical_to_entry.get(canonical_name)

    def get_by_category(self, category: ConstructCategory) -> List[MappingEntry]:
        return [e for e in self._entries.values() if e.category == category]

    def get_all(self) -> List[MappingEntry]:
        return list(self._entries.values())

    def coverage_report(self) -> Dict[str, Any]:
        categories = set(e.category for e in self._entries.values())
        return {
            "total_mappings": len(self._entries),
            "categories_covered": len(categories),
            "categories": [c.name for c in categories],
            "avg_confidence": sum(e.confidence for e in self._entries.values())
            / max(len(self._entries), 1),
            "requires_manual_review": sum(
                1 for e in self._entries.values() if e.requires_manual_review
            ),
        }


# ---------------------------------------------------------------------------
# Vendor Dialect A: Java → Canonical IR
# ---------------------------------------------------------------------------


class JavaDialectParser:
    """
    Parses Java mod source code to extract Canonical IR constructs.

    Uses regex-based extraction as a lightweight parser. In production,
    this would be replaced by an AST-based analyzer (e.g., using Eclipse JDT
    or a similar Java parser).
    """

    EVENT_HANDLER_PATTERNS = [
        re.compile(
            r"@SubscribeEvent\s*\n\s*"
            r"(?:public\s+|private\s+|protected\s+|static\s+)*"
            r"\w+\s+(\w+)\s*\([^)]*Event[^)]*\)\s*(?:throws[^{]{.*?)?\{",
            re.DOTALL,
        ),
        re.compile(
            r"(?:public\s+|private\s+|protected\s+|static\s+)*"
            r"\w+\s+(\w+)\s*\([^)]*Event[^)]*\)\s*\{",
            re.DOTALL,
        ),
    ]

    TICK_HANDLER_PATTERNS = [
        re.compile(
            r"public\s+static\s+void\s+(\w*tick\w*)\s*\("
            r"[^{]*Level[^{]*BlockPos[^{]*BlockState[^{]*(\w+Entity)[^{]*\{",
            re.DOTALL,
        ),
        re.compile(
            r"public\s+void\s+(\w*tick\w*)\s*\(\s*\)\s*\{",
            re.DOTALL,
        ),
    ]

    RIGHT_CLICK_PATTERNS = [
        re.compile(
            r"PlayerInteractEvent\.RightClickBlock",
            re.DOTALL,
        ),
        re.compile(
            r"@SubscribeEvent\s*\n\s*.*?PlayerInteractEvent",
            re.DOTALL,
        ),
    ]

    BLOCK_BREAK_PATTERNS = [
        re.compile(
            r"BlockEvent\.BreakEvent",
            re.DOTALL,
        ),
        re.compile(
            r"PlayerDestroyBlockEvent",
            re.DOTALL,
        ),
    ]

    ENTITY_JOIN_PATTERNS = [
        re.compile(
            r"EntityJoinLevelEvent",
            re.DOTALL,
        ),
    ]

    def parse(self, java_source: str) -> List[IRConstruct]:
        constructs: List[IRConstruct] = []
        constructs.extend(self._extract_event_handlers(java_source))
        constructs.extend(self._extract_tick_functions(java_source))
        constructs.extend(self._extract_block_interactions(java_source))
        constructs.extend(self._extract_block_breaks(java_source))
        constructs.extend(self._extract_entity_spawns(java_source))
        return constructs

    def _extract_event_handlers(self, source: str) -> List[EventHandler]:
        handlers: List[EventHandler] = []

        if "PlayerInteractEvent" in source:
            event_type = "player_interact_block"
            if "RightClickBlock" in source:
                event_type = "player_right_click_block"
            handlers.append(
                EventHandler(
                    canonical_name="player_interact",
                    category=ConstructCategory.EVENT,
                    event_type=event_type,
                    subscribe_lambda_body=self._extract_method_body(source, "PlayerInteractEvent"),
                    is_after=True,
                    semantic_equivalence=SemanticEquivalence.DIRECT,
                )
            )

        if "EntityJoinLevelEvent" in source:
            handlers.append(
                EventHandler(
                    canonical_name="entity_join",
                    category=ConstructCategory.EVENT,
                    event_type="entity_join_level",
                    subscribe_lambda_body=self._extract_method_body(source, "EntityJoinLevelEvent"),
                    is_after=True,
                    semantic_equivalence=SemanticEquivalence.DIRECT,
                )
            )

        return handlers

    def _extract_tick_functions(self, source: str) -> List[TickFunction]:
        functions: List[TickFunction] = []

        tick_match = re.search(
            r"public\s+static\s+void\s+(\w*tick\w*)\s*\("
            r"[^{]*Level[^{]*BlockPos[^{]*BlockState[^{]*(\w+Entity)[^{]*\{",
            source,
            re.DOTALL,
        )
        if tick_match:
            functions.append(
                TickFunction(
                    canonical_name="block_tick",
                    category=ConstructCategory.TICK,
                    interval_ticks=1,
                    tick_body=self._extract_tick_body(source, tick_match),
                    semantic_equivalence=SemanticEquivalence.APPROXIMATE,
                )
            )
        return functions

    def _extract_block_interactions(self, source: str) -> List[BlockInteraction]:
        interactions: List[BlockInteraction] = []
        if "PlayerInteractEvent" in source and "RightClickBlock" in source:
            trigger_item = None
            if "ItemStack" in source or "is(" in source:
                item_match = re.search(r"is\s*\(\s*Items\.(\w+)", source)
                if item_match:
                    trigger_item = f"minecraft:{item_match.group(1).lower()}"
            target_block = None
            block_match = re.search(r"Blocks\.(\w+)", source)
            if block_match:
                target_block = f"minecraft:{block_match.group(1).lower()}"

            interactions.append(
                BlockInteraction(
                    canonical_name="block_right_click",
                    category=ConstructCategory.BLOCK_INTERACTION,
                    trigger_item=trigger_item,
                    target_block=target_block,
                    cancelable=True,
                    interaction_body=self._extract_method_body(source, "PlayerInteractEvent"),
                    semantic_equivalence=SemanticEquivalence.DIRECT,
                )
            )
        return interactions

    def _extract_block_breaks(self, source: str) -> List[BlockBreak]:
        breaks: List[BlockBreak] = []
        if "BlockEvent.BreakEvent" in source or "PlayerDestroyBlockEvent" in source:
            block_type = None
            block_match = re.search(r"Blocks\.(\w+)", source)
            if block_match:
                block_type = f"minecraft:{block_match.group(1).lower()}"
            breaks.append(
                BlockBreak(
                    canonical_name="block_break",
                    category=ConstructCategory.BLOCK_BREAK,
                    block_type=block_type,
                    drop_xp="setExpToDrop" in source,
                    break_body=self._extract_method_body(source, "BreakEvent"),
                    semantic_equivalence=SemanticEquivalence.DIRECT,
                )
            )
        return breaks

    def _extract_entity_spawns(self, source: str) -> List[EntitySpawn]:
        spawns: List[EntitySpawn] = []
        if "EntityJoinLevelEvent" in source:
            entity_type = None
            entity_match = re.search(r"EntityType\.(\w+)", source)
            if entity_match:
                entity_type = f"minecraft:{entity_match.group(1).lower()}"
            spawns.append(
                EntitySpawn(
                    canonical_name="entity_spawn",
                    category=ConstructCategory.ENTITY_SPAWN,
                    entity_type=entity_type,
                    spawn_body=self._extract_method_body(source, "EntityJoinLevelEvent"),
                    semantic_equivalence=SemanticEquivalence.DIRECT,
                )
            )
        return spawns

    def _extract_method_body(self, source: str, event_class: str) -> str:
        pattern = rf"{event_class}[^{{]{{(?:\s*[^}}]*){{([^}}]*)}}}}"
        match = re.search(pattern, source, re.DOTALL)
        if match:
            return match.group(1).strip()
        return "// handler body (could not extract)"

    def _extract_tick_body(self, source: str, match: re.Match) -> str:
        start = match.end()
        brace_count = 1
        pos = start
        while pos < len(source) and brace_count > 0:
            if source[pos] == "{":
                brace_count += 1
            elif source[pos] == "}":
                brace_count -= 1
            pos += 1
        return source[start : pos - 1].strip()


# ---------------------------------------------------------------------------
# Vendor Dialect B: Canonical IR → Bedrock
# ---------------------------------------------------------------------------


class BedrockDialectGenerator:
    """
    Generates Bedrock Script API code from Canonical IR constructs.

    Each generate_* method takes a canonical IR construct and returns
    Bedrock-equivalent JavaScript code as a string.
    """

    def generate(self, ir_construct: IRConstruct) -> str:
        if isinstance(ir_construct, EventHandler):
            return self._generate_event_handler(ir_construct)
        elif isinstance(ir_construct, TickFunction):
            return self._generate_tick_function(ir_construct)
        elif isinstance(ir_construct, BlockInteraction):
            return self._generate_block_interaction(ir_construct)
        elif isinstance(ir_construct, BlockBreak):
            return self._generate_block_break(ir_construct)
        elif isinstance(ir_construct, EntitySpawn):
            return self._generate_entity_spawn(ir_construct)
        return f"// Unsupported IR construct: {ir_construct.canonical_name}"

    def generate_from_java_id(
        self, java_construct_id: str, table: FormalMappingTable
    ) -> Optional[str]:
        entry = table.get(java_construct_id)
        if entry is None:
            return None
        return self.generate(entry.canonical_construct)

    def _generate_event_handler(self, handler: EventHandler) -> str:
        event_map = {
            "player_interact_block": "world.afterEvents.playerInteractWithBlock",
            "entity_join_level": "world.afterEvents.entitySpawn",
            "player_right_click_block": "world.afterEvents.playerInteractWithBlock",
        }
        event_api = event_map.get(handler.event_type, f"world.afterEvents.{handler.event_type}")
        return f"""\
{event_api}.subscribe((event) => {{
    // {handler.semantic_summary()}
    {handler.subscribe_lambda_body}
}});"""

    def _generate_tick_function(self, func: TickFunction) -> str:
        interval = max(1, func.interval_ticks)
        frequency = 20.0 / interval
        return f"""\
import {{ system }} from "@minecraft/server";

// {func.semantic_summary()}
system.runInterval(() => {{
    {func.tick_body}
}}, {interval}); // {frequency:.1f} Hz approx"""

    def _generate_block_interaction(self, interaction: BlockInteraction) -> str:
        item_check = ""
        if interaction.trigger_item:
            item_check = f"""
    if (event.itemStack?.typeId !== "{interaction.trigger_item}") return;"""

        block_check = ""
        if interaction.target_block:
            block_check = f"""
    if (event.block?.typeId !== "{interaction.target_block}") return;"""

        return f"""\
world.afterEvents.playerInteractWithBlock.subscribe((event) => {{
    const player = event.player;
    const block = event.block;{item_check}{block_check}
    // {interaction.semantic_summary()}
    {interaction.interaction_body}
}});"""

    def _generate_block_break(self, brk: BlockBreak) -> str:
        block_check = ""
        if brk.block_type:
            block_check = f"""
    if (event.brokenBlockPermutation?.type?.id !== "{brk.block_type}") return;"""

        xp_line = ""
        if brk.drop_xp:
            xp_line = "    // Award XP: player.giveExperience(XP_AMOUNT);"

        return f"""\
world.afterEvents.blockBreak.subscribe((event) => {{
    const player = event.player;
    const block = event.block;{block_check}
    // {brk.semantic_summary()}
    {brk.break_body}
{xp_line}}});"""

    def _generate_entity_spawn(self, spawn: EntitySpawn) -> str:
        entity_check = ""
        if spawn.entity_type:
            entity_check = f"""
    if (event.entity?.typeId !== "{spawn.entity_type}") return;"""

        return f"""\
world.afterEvents.entitySpawn.subscribe((event) => {{
    const entity = event.entity;{entity_check}
    // {spawn.semantic_summary()}
    {spawn.spawn_body}
}});"""


# ---------------------------------------------------------------------------
# Vendor Formalism — Top-level Orchestrator
# ---------------------------------------------------------------------------


class VendorFormalism:
    """
    Top-level orchestrator for the vendor-translation formalism.

    Coordinates the Java dialect parser, formal mapping table, and
    Bedrock dialect generator into a unified interface for the conversion
    pipeline.

    Usage:
        vf = VendorFormalism()
        ir_constructs = vf.parse_java(java_source)
        bedrock_code = vf.generate_bedrock(ir_constructs[0])
        report = vf.coverage_report()
    """

    def __init__(self) -> None:
        self.table = FormalMappingTable()
        self.java_parser = JavaDialectParser()
        self.bedrock_generator = BedrockDialectGenerator()

    def parse_java(self, java_source: str) -> List[IRConstruct]:
        return self.java_parser.parse(java_source)

    def generate_bedrock(self, ir_construct: IRConstruct) -> str:
        return self.bedrock_generator.generate(ir_construct)

    def translate_java_to_bedrock(self, java_source: str) -> List[Dict[str, Any]]:
        """
        Parse Java source and return structured translation results.

        Returns a list of dicts with the Java construct, canonical IR,
        and generated Bedrock code for each identified construct.
        """
        constructs = self.parse_java(java_source)
        results: List[Dict[str, Any]] = []
        for ir in constructs:
            bedrock_code = self.generate_bedrock(ir)
            table_entry = self.table.get_by_canonical_name(ir.canonical_name)
            results.append(
                {
                    "canonical_ir": ir.to_dict(),
                    "bedrock_code": bedrock_code,
                    "table_entry": table_entry.to_dict() if table_entry else None,
                    "confidence": (table_entry.confidence if table_entry else None),
                }
            )
        return results

    def coverage_report(self) -> Dict[str, Any]:
        return self.table.coverage_report()
