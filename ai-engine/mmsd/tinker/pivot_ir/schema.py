#!/usr/bin/env python3
"""
Pivot IR Schema — Structured Intermediate Representation for Java→Bedrock
========================================================================

This module defines the Pivot IR data model - a structured representation
that captures essential Java→Bedrock translation semantics.

Design Rationale:
  - Entity-centric: Blocks, Items, Entities as first-class concepts
  - Event mapping: Java events mapped to Bedrock event subscriptions
  - API patterns: Direct mappings for common Java→Bedrock API calls
  - Partial coverage: Each component can be partial (missing = 0 coverage)

IR Components:
  1. Manifest: Add-on metadata (name, uuid, version)
  2. Entities: Block, Item, Entity definitions
  3. Events: Event handler mappings (Java→Bedrock)
  4. APIs: API call patterns with coverage tracking

Author: PortKit AI Engine
Issues: #1578, #1594
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class EntityType(Enum):
    """Type of Minecraft entity."""
    BLOCK = "block"
    ITEM = "item"
    ENTITY = "entity"
    CONTAINER = "container"


class EventType(Enum):
    """Type of event handler."""
    INTERACT = "interact"
    BREAK = "break"
    PLACE = "place"
    TICK = "tick"
    SPAWN = "spawn"
    DEATH = "death"
    ATTACK = "attack"
    USE = "use"
    CUSTOM = "custom"


@dataclass
class APICall:
    """A single API call in the IR.
    
    Tracks whether this API call was successfully translated.
    """
    chain: str  # e.g., "world.afterEvents.tick.subscribe"
    depth: int  # API chain depth
    source_java: Optional[str] = None  # Original Java API call
    translated: bool = True  # Whether translation succeeded
    partial: bool = False  # If partially translated


@dataclass
class EventHandler:
    """An event handler mapping from Java to Bedrock.
    
    Captures the essential semantics of an event handler.
    """
    java_event: str  # e.g., "@SubscribeEvent", "onPlayerInteract"
    bedrock_event: str  # e.g., "playerInteractWithBlock"
    callback_params: list[str] = field(default_factory=list)  # e.g., ["player", "block"]
    body_statements: list[str] = field(default_factory=list)  # Key statements
    translated: bool = True  # Full translation success
    partial: bool = False  # Partial translation


@dataclass
class Manifest:
    """Add-on manifest metadata."""
    name: str
    uuid: str
    version: list[int]
    description: str = ""
    min_engine_version: list[int] = field(default_factory=lambda: [1, 20, 0])
    format_version: int = 2


@dataclass
class BlockDef:
    """Block definition in IR."""
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    event_handlers: list[EventHandler] = field(default_factory=list)
    api_calls: list[APICall] = field(default_factory=list)
    translated: bool = True
    partial: bool = False


@dataclass
class ItemDef:
    """Item definition in IR."""
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    event_handlers: list[EventHandler] = field(default_factory=list)
    api_calls: list[APICall] = field(default_factory=list)
    translated: bool = True
    partial: bool = False


@dataclass
class EntityDef:
    """Entity definition in IR."""
    name: str
    entity_type: str  # e.g., "minecraft:pig"
    properties: dict[str, Any] = field(default_factory=dict)
    event_handlers: list[EventHandler] = field(default_factory=list)
    api_calls: list[APICall] = field(default_factory=list)
    translated: bool = True
    partial: bool = False


@dataclass
class PivotIR:
    """Pivot IR — Structured representation of Java→Bedrock conversion.
    
    This is the core data structure that adapters work with.
    
    Attributes:
        manifest: Add-on manifest metadata
        blocks: Block definitions (keyed by name)
        items: Item definitions (keyed by name)
        entities: Entity definitions (keyed by name)
        global_events: Global event handlers (not tied to specific entity)
        global_apis: Global API calls
        raw_java: Original Java source (for debugging)
        coverage_stats: Coverage statistics for APF reward
    """
    manifest: Optional[Manifest] = None
    blocks: dict[str, BlockDef] = field(default_factory=dict)
    items: dict[str, ItemDef] = field(default_factory=dict)
    entities: dict[str, EntityDef] = field(default_factory=dict)
    global_events: list[EventHandler] = field(default_factory=list)
    global_apis: list[APICall] = field(default_factory=list)
    raw_java: str = ""  # Original Java source
    # Coverage tracking for APF reward
    total_entities: int = 0
    translated_entities: int = 0
    total_events: int = 0
    translated_events: int = 0
    total_api_calls: int = 0
    translated_api_calls: int = 0


def create_pivot_ir(
    manifest: Optional[Manifest] = None,
    blocks: Optional[dict[str, BlockDef]] = None,
    items: Optional[dict[str, ItemDef]] = None,
    entities: Optional[dict[str, EntityDef]] = None,
    global_events: Optional[list[EventHandler]] = None,
    global_apis: Optional[list[APICall]] = None,
    raw_java: str = "",
) -> PivotIR:
    """Factory function to create a PivotIR instance."""
    return PivotIR(
        manifest=manifest or Manifest(name="unnamed", uuid="", version=[0, 0, 1]),
        blocks=blocks or {},
        items=items or {},
        entities=entities or {},
        global_events=global_events or [],
        global_apis=global_apis or [],
        raw_java=raw_java,
    )


def pivot_ir_to_dict(ir: PivotIR) -> dict:
    """Convert PivotIR to dictionary for serialization."""
    def handler_to_dict(h: EventHandler) -> dict:
        return {
            "java_event": h.java_event,
            "bedrock_event": h.bedrock_event,
            "callback_params": h.callback_params,
            "body_statements": h.body_statements,
            "translated": h.translated,
            "partial": h.partial,
        }
    
    def api_to_dict(a: APICall) -> dict:
        return {
            "chain": a.chain,
            "depth": a.depth,
            "source_java": a.source_java,
            "translated": a.translated,
            "partial": a.partial,
        }
    
    def manifest_to_dict(m: Manifest) -> dict:
        return {
            "name": m.name,
            "uuid": m.uuid,
            "version": m.version,
            "description": m.description,
            "min_engine_version": m.min_engine_version,
            "format_version": m.format_version,
        }
    
    return {
        "manifest": manifest_to_dict(ir.manifest) if ir.manifest else None,
        "blocks": {
            name: {
                "name": b.name,
                "properties": b.properties,
                "event_handlers": [handler_to_dict(h) for h in b.event_handlers],
                "api_calls": [api_to_dict(a) for a in b.api_calls],
                "translated": b.translated,
                "partial": b.partial,
            }
            for name, b in ir.blocks.items()
        },
        "items": {
            name: {
                "name": i.name,
                "properties": i.properties,
                "event_handlers": [handler_to_dict(h) for h in i.event_handlers],
                "api_calls": [api_to_dict(a) for a in i.api_calls],
                "translated": i.translated,
                "partial": i.partial,
            }
            for name, i in ir.items.items()
        },
        "entities": {
            name: {
                "name": e.name,
                "entity_type": e.entity_type,
                "properties": e.properties,
                "event_handlers": [handler_to_dict(h) for h in e.event_handlers],
                "api_calls": [api_to_dict(a) for a in e.api_calls],
                "translated": e.translated,
                "partial": e.partial,
            }
            for name, e in ir.entities.items()
        },
        "global_events": [handler_to_dict(h) for h in ir.global_events],
        "global_apis": [api_to_dict(a) for a in ir.global_apis],
        "raw_java": ir.raw_java,
        "coverage_stats": {
            "total_entities": ir.total_entities,
            "translated_entities": ir.translated_entities,
            "total_events": ir.total_events,
            "translated_events": ir.translated_events,
            "total_api_calls": ir.total_api_calls,
            "translated_api_calls": ir.translated_api_calls,
        },
    }


def dict_to_pivot_ir(d: dict) -> PivotIR:
    """Reconstruct PivotIR from dictionary."""
    def dict_to_handler(h: dict) -> EventHandler:
        return EventHandler(
            java_event=h["java_event"],
            bedrock_event=h["bedrock_event"],
            callback_params=h.get("callback_params", []),
            body_statements=h.get("body_statements", []),
            translated=h.get("translated", True),
            partial=h.get("partial", False),
        )
    
    def dict_to_api(a: dict) -> APICall:
        return APICall(
            chain=a["chain"],
            depth=a.get("depth", 0),
            source_java=a.get("source_java"),
            translated=a.get("translated", True),
            partial=a.get("partial", False),
        )
    
    def dict_to_manifest(m: dict) -> Manifest:
        return Manifest(
            name=m["name"],
            uuid=m["uuid"],
            version=m["version"],
            description=m.get("description", ""),
            min_engine_version=m.get("min_engine_version", [1, 20, 0]),
            format_version=m.get("format_version", 2),
        )
    
    def dict_to_block(b: dict) -> BlockDef:
        return BlockDef(
            name=b["name"],
            properties=b.get("properties", {}),
            event_handlers=[dict_to_handler(h) for h in b.get("event_handlers", [])],
            api_calls=[dict_to_api(a) for a in b.get("api_calls", [])],
            translated=b.get("translated", True),
            partial=b.get("partial", False),
        )
    
    def dict_to_item(i: dict) -> ItemDef:
        return ItemDef(
            name=i["name"],
            properties=i.get("properties", {}),
            event_handlers=[dict_to_handler(h) for h in i.get("event_handlers", [])],
            api_calls=[dict_to_api(a) for a in i.get("api_calls", [])],
            translated=i.get("translated", True),
            partial=i.get("partial", False),
        )
    
    def dict_to_entity(e: dict) -> EntityDef:
        return EntityDef(
            name=e["name"],
            entity_type=e.get("entity_type", ""),
            properties=e.get("properties", {}),
            event_handlers=[dict_to_handler(h) for h in e.get("event_handlers", [])],
            api_calls=[dict_to_api(a) for a in e.get("api_calls", [])],
            translated=e.get("translated", True),
            partial=e.get("partial", False),
        )
    
    cov = d.get("coverage_stats", {})
    return PivotIR(
        manifest=dict_to_manifest(d["manifest"]) if d.get("manifest") else None,
        blocks={name: dict_to_block(b) for name, b in d.get("blocks", {}).items()},
        items={name: dict_to_item(i) for name, i in d.get("items", {}).items()},
        entities={name: dict_to_entity(e) for name, e in d.get("entities", {}).items()},
        global_events=[dict_to_handler(h) for h in d.get("global_events", [])],
        global_apis=[dict_to_api(a) for a in d.get("global_apis", [])],
        raw_java=d.get("raw_java", ""),
        total_entities=cov.get("total_entities", 0),
        translated_entities=cov.get("translated_entities", 0),
        total_events=cov.get("total_events", 0),
        translated_events=cov.get("translated_events", 0),
        total_api_calls=cov.get("total_api_calls", 0),
        translated_api_calls=cov.get("translated_api_calls", 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# IR Statistics
# ─────────────────────────────────────────────────────────────────────────────

def compute_coverage(ir: PivotIR) -> dict[str, float]:
    """Compute coverage statistics for APF reward calculation.
    
    Returns dict with coverage percentages for entities, events, and APIs.
    """
    entity_coverage = (
        ir.translated_entities / ir.total_entities if ir.total_entities > 0 else 0.0
    )
    event_coverage = (
        ir.translated_events / ir.total_events if ir.total_events > 0 else 0.0
    )
    api_coverage = (
        ir.translated_api_calls / ir.total_api_calls if ir.total_api_calls > 0 else 0.0
    )
    
    return {
        "entity_coverage": entity_coverage,
        "event_coverage": event_coverage,
        "api_coverage": api_coverage,
        "overall_coverage": (entity_coverage + event_coverage + api_coverage) / 3,
    }


def ir_to_text_summary(ir: PivotIR) -> str:
    """Generate a human-readable summary of the IR."""
    lines = ["PivotIR Summary", "=" * 50]
    
    if ir.manifest:
        lines.append(f"Manifest: {ir.manifest.name} v{ir.manifest.version}")
    
    lines.append(f"\nBlocks: {len(ir.blocks)}")
    for name, block in ir.blocks.items():
        lines.append(f"  - {name}: {len(block.event_handlers)} events, {len(block.api_calls)} APIs")
    
    lines.append(f"\nItems: {len(ir.items)}")
    for name, item in ir.items.items():
        lines.append(f"  - {name}: {len(item.event_handlers)} events, {len(item.api_calls)} APIs")
    
    lines.append(f"\nEntities: {len(ir.entities)}")
    for name, entity in ir.entities.items():
        lines.append(f"  - {name} ({entity.entity_type}): {len(entity.event_handlers)} events")
    
    lines.append(f"\nGlobal Events: {len(ir.global_events)}")
    lines.append(f"Global APIs: {len(ir.global_apis)}")
    
    cov = compute_coverage(ir)
    lines.append(f"\nCoverage:")
    lines.append(f"  Entities: {cov['entity_coverage']:.1%}")
    lines.append(f"  Events: {cov['event_coverage']:.1%}")
    lines.append(f"  APIs: {cov['api_coverage']:.1%}")
    lines.append(f"  Overall: {cov['overall_coverage']:.1%}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick test of schema
    manifest = Manifest(
        name="test_mod",
        uuid="abc-123",
        version=[1, 0, 0],
        description="Test mod",
    )
    
    block = BlockDef(
        name="custom_block",
        properties={"material": "stone"},
        event_handlers=[
            EventHandler(
                java_event="@SubscribeEvent",
                bedrock_event="onPlayerInteract",
                callback_params=["player", "block"],
                body_statements=["player.sendMessage('Used block!')"],
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
    
    ir = create_pivot_ir(
        manifest=manifest,
        blocks={"custom_block": block},
        raw_java="// Java source here",
    )
    ir.total_entities = 1
    ir.translated_entities = 1
    ir.total_events = 1
    ir.translated_events = 1
    ir.total_api_calls = 1
    ir.translated_api_calls = 1
    
    print(ir_to_text_summary(ir))
    print("\n" + "=" * 50)
    print("Dict serialization test:")
    d = pivot_ir_to_dict(ir)
    print(f"Serialized keys: {list(d.keys())}")
    
    ir2 = dict_to_pivot_ir(d)
    print(f"Deserialized blocks: {list(ir2.blocks.keys())}")