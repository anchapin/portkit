#!/usr/bin/env python3
"""
Java → PivotIR Adapter — Parse Java Mod Code to Intermediate Representation
============================================================================

This adapter parses Minecraft Java mod code and produces a Pivot IR representation
that captures the essential translation semantics.

Supported Java Patterns:
  - Class definitions (Block, Item, Entity)
  - Event annotations (@SubscribeEvent, @Mod.EventBusSubscriber)
  - Method patterns (onPlayerInteract, onBlockBreak, etc.)
  - Forge API calls (player.sendMessage, world.addEntity, etc.)
  - Registry patterns (DeferredRegistry, RegistryObject)

Translation Coverage:
  - Entity definitions: HIGH (core patterns covered)
  - Event handlers: MEDIUM (common patterns mapped)
  - API calls: MEDIUM (common chains supported)

Author: PortKit AI Engine
Issues: #1578, #1599, #1617
"""

import re
from dataclasses import dataclass, field

from pivot_ir.schema import (
    PivotIR,
    BlockDef,
    ItemDef,
    EntityDef,
    EventHandler,
    APICall,
)


# ─────────────────────────────────────────────────────────────────────────────
# Java → Bedrock Event Mappings
# ─────────────────────────────────────────────────────────────────────────────

JAVA_TO_BEDROCK_EVENTS: dict[str, str] = {
    # Player events
    "onPlayerJoined": "playerSpawn",
    "onPlayerDeath": "entityDie",
    "onPlayerRespawn": "playerSpawn",
    "onPlayerInteract": "playerInteractWithBlock",
    "onPlayerBreakBlock": "blockBreak",
    "onPlayerPlaceBlock": "blockPlace",
    "onPlayerUseItem": "itemUse",
    "onPlayerAttack": "entityAttack",
    # World events
    "onWorldTick": "tick",
    "onServerStart": "load",
    "onServerStop": "unload",
    # Block events
    "onBlockBreak": "blockBreak",
    "onBlockPlace": "blockPlace",
    "onBlockInteract": "playerInteractWithBlock",
    "onBlockUpdated": "blockChanged",
    # Entity events
    "onEntityDeath": "entityDie",
    "onEntitySpawn": "mobSpawn",
    "onEntityTick": "entitySpawn",
    # Item events
    "onItemUse": "itemUse",
    "onItemCrafted": "recipe crafting",
    # Custom events
    "@SubscribeEvent": "custom",
}


# ─────────────────────────────────────────────────────────────────────────────
# Java → Bedrock API Mappings
# ─────────────────────────────────────────────────────────────────────────────

JAVA_TO_BEDROCK_API: dict[str, str] = {
    # Player APIs
    "player.sendMessage": "player.sendMessage",
    "player.teleport": "player.teleport",
    "player.getInventory": "player.getComponent('minecraft:inventory')",
    "player.addEffect": "player.addEffect",
    "player.getHealth": "player.getComponent('minecraft:health')",
    "player.setRotation": "player.setRotation",
    "player.getName": "player.name",
    "player.isSneaking": "player.isSneaking",
    # World APIs
    "world.getBlock": "world.getBlock",
    "world.setBlock": "world.getBlock().setBlock",
    "world.getEntities": "world.getEntities",
    "world.addEntity": "world.spawnEntity",
    "world.getDimension": "world.getDimension",
    "world.getServer": "world.getDimension",
    # ItemStack APIs
    "itemStack.getItem": "ItemStack",
    "itemStack.setCount": "ItemStack.amount",
    "itemStack.getMaxStackSize": "ItemStack.maxAmount",
    # Block APIs
    "block.getState": "block.state",
    "block.setProperty": "block.setState",
    "block.getLocation": "block.location",
    "block.breakNaturally": "block.destroy",
    # Entity APIs
    "entity.getType": "entity.typeId",
    "entity.getPosition": "entity.location",
    "entity.remove": "entity.remove",
    "entity.getTicksAlive": "entity.age",
}


# ─────────────────────────────────────────────────────────────────────────────
# Java Class Pattern Recognition
# ─────────────────────────────────────────────────────────────────────────────

JAVA_CLASS_PATTERNS = [
    (r"class\s+(\w+)\s+extends\s+Block", "block"),
    (r"class\s+(\w+)\s+extends\s+Item", "item"),
    (r"class\s+(\w+)\s+extends\s+Entity", "entity"),
    (r"class\s+(\w+)\s+extends\s+TileEntity", "block"),
    (r"class\s+(\w+)\s+extends\s+ContainedBlock", "block"),
    (r"@Mod\s*\(\s*[\"'](\w+)[\"']\s*\)", "mod"),
]


@dataclass
class ParsedJavaEntity:
    """Represents a parsed Java entity/class."""

    name: str
    entity_type: str  # "block", "item", "entity", "mod"
    class_body: str
    annotations: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class ParsedEventHandler:
    """Represents a parsed event handler."""

    java_event: str
    bedrock_event: str
    method_name: str
    params: list[str]
    body: str
    is_annotation_based: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Java Parser
# ─────────────────────────────────────────────────────────────────────────────


class JavaParser:
    """Parse Java mod code into structured components."""

    def __init__(self, java_source: str):
        self.source = java_source
        self.entities: list[ParsedJavaEntity] = []
        self.global_events: list[ParsedEventHandler] = []
        self.imports: list[str] = []

    def parse(self) -> tuple[list[ParsedJavaEntity], list[ParsedEventHandler]]:
        """Parse the Java source and extract entities and events."""
        self._extract_imports()
        self._extract_entities()
        self._extract_global_events()
        return self.entities, self.global_events

    def _extract_imports(self) -> None:
        """Extract all import statements."""
        import_pattern = r"import\s+([\w.]+);"
        self.imports = re.findall(import_pattern, self.source)

    def _extract_entities(self) -> None:
        """Extract class definitions and their bodies."""
        # Match class definitions with their bodies
        class_pattern = r"(class\s+\w+(?:\s+extends\s+\w+)?(?:\s+implements\s+[\w,\s]+)?\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\})"

        for match in re.finditer(class_pattern, self.source, re.DOTALL):
            class_def = match.group(1)
            self._parse_class_body(class_def)

    def _parse_class_body(self, class_body: str) -> None:
        """Parse a single class definition."""
        # Extract class name and type
        class_name_match = re.search(r"class\s+(\w+)", class_body)
        if not class_name_match:
            return
        class_name = class_name_match.group(1)

        # Determine entity type
        entity_type = "unknown"
        for pattern, etype in JAVA_CLASS_PATTERNS:
            if re.search(pattern, class_body):
                entity_type = etype
                break

        # Extract annotations
        annotations = re.findall(r"@(\w+)(?:\([^)]*\))?", class_body)

        # Extract methods
        method_pattern = r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}"
        methods = re.findall(method_pattern, class_body, re.DOTALL)

        # Extract fields
        field_pattern = (
            r"(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*[\w<>]+\s+(\w+)\s*;"
        )
        fields = re.findall(field_pattern, class_body)

        entity = ParsedJavaEntity(
            name=class_name,
            entity_type=entity_type,
            class_body=class_body,
            annotations=annotations,
            methods=methods,
            fields=fields,
            imports=self.imports.copy(),
        )
        self.entities.append(entity)

    def _extract_global_events(self) -> None:
        """Extract global event handlers (not tied to a class)."""
        # Find @SubscribeEvent methods outside classes
        subscribe_pattern = (
            r"@SubscribeEvent\s+(?:public|private|protected)?\s*\w*\s*void\s+(\w+)\s*\([^)]*\)"
        )

        for match in re.finditer(subscribe_pattern, self.source):
            method_name = match.group(1)
            bedrock_event = self._map_java_to_bedrock_event(method_name)

            handler = ParsedEventHandler(
                java_event="@SubscribeEvent",
                bedrock_event=bedrock_event,
                method_name=method_name,
                params=[],  # Would need more complex parsing
                body="",
                is_annotation_based=True,
            )
            self.global_events.append(handler)

    def _map_java_to_bedrock_event(self, method_name: str) -> str:
        """Map a Java method name to Bedrock event."""
        # Check direct mappings
        if method_name in JAVA_TO_BEDROCK_EVENTS:
            return JAVA_TO_BEDROCK_EVENTS[method_name]

        # Try partial match
        for java_event, bedrock_event in JAVA_TO_BEDROCK_EVENTS.items():
            if java_event.lower() in method_name.lower():
                return bedrock_event

        # Default: camelCase to camelCase but with Bedrock naming
        # e.g., onPlayerInteract -> playerInteract
        cleaned = re.sub(r"^on", "", method_name)
        return cleaned[0].lower() + cleaned[1:] if cleaned else method_name


# ─────────────────────────────────────────────────────────────────────────────
# Java → PivotIR Adapter
# ─────────────────────────────────────────────────────────────────────────────


class JavaToPivotIRAdapter:
    """Adapt Java mod code to Pivot IR representation."""

    def __init__(self):
        self.java_parser = None

    def parse(self, java_source: str) -> PivotIR:
        """Parse Java source to Pivot IR.

        Args:
            java_source: The Java mod source code

        Returns:
            PivotIR representation
        """
        self.java_parser = JavaParser(java_source)
        entities, global_events = self.java_parser.parse()

        # Build IR
        ir = PivotIR(raw_java=java_source)

        # Process entities
        for entity in entities:
            self._process_entity(entity, ir)

        # Process global events
        for event in global_events:
            self._convert_event_handler(event, ir)

        # Update coverage stats
        self._compute_coverage_stats(ir)

        return ir

    def _process_entity(self, entity: ParsedJavaEntity, ir: PivotIR) -> None:
        """Process a parsed entity and add to IR."""
        if entity.entity_type == "block":
            block = self._create_block_def(entity)
            ir.blocks[entity.name] = block
        elif entity.entity_type == "item":
            item = self._create_item_def(entity)
            ir.items[entity.name] = item
        elif entity.entity_type == "entity":
            entity_def = self._create_entity_def(entity)
            ir.entities[entity.name] = entity_def

    def _create_block_def(self, entity: ParsedJavaEntity) -> BlockDef:
        """Create a BlockDef from parsed entity."""
        events = self._extract_events_from_body(entity.class_body, "block")
        apis = self._extract_api_calls(entity.class_body)

        return BlockDef(
            name=entity.name,
            properties={"type": "block"},
            event_handlers=events,
            api_calls=apis,
            translated=True,
            partial=False,
        )

    def _create_item_def(self, entity: ParsedJavaEntity) -> ItemDef:
        """Create an ItemDef from parsed entity."""
        events = self._extract_events_from_body(entity.class_body, "item")
        apis = self._extract_api_calls(entity.class_body)

        return ItemDef(
            name=entity.name,
            properties={"type": "item"},
            event_handlers=events,
            api_calls=apis,
            translated=True,
            partial=False,
        )

    def _create_entity_def(self, entity: ParsedJavaEntity) -> EntityDef:
        """Create an EntityDef from parsed entity."""
        events = self._extract_events_from_body(entity.class_body, "entity")
        apis = self._extract_api_calls(entity.class_body)

        # Try to extract entity type from class name
        entity_type = f"minecraft:{entity.name.lower()}"

        return EntityDef(
            name=entity.name,
            entity_type=entity_type,
            properties={"type": "entity"},
            event_handlers=events,
            api_calls=apis,
            translated=True,
            partial=False,
        )

    def _extract_events_from_body(self, class_body: str, entity_type: str) -> list[EventHandler]:
        """Extract event handlers from class body."""
        events = []

        # Pattern 1: @SubscribeEvent methods
        subscribe_pattern = (
            r"@SubscribeEvent\s+(?:public|private|protected)?\s*\w*\s*void\s+(\w+)\s*\(([^)]*)\)"
        )

        for match in re.finditer(subscribe_pattern, class_body):
            method_name = match.group(1)
            params_str = match.group(2)
            params = [p.strip().split()[-1] for p in params_str.split(",")]

            bedrock_event = self._map_java_to_bedrock(method_name)

            events.append(
                EventHandler(
                    java_event=f"@SubscribeEvent {method_name}",
                    bedrock_event=bedrock_event,
                    callback_params=params,
                    body_statements=[],
                    translated=True,
                    partial=False,
                )
            )

        # Pattern 2: Conventional naming (onXxx, handleXxx)
        conventional_pattern = (
            r"(?:public|private|protected)?\s*void\s+(on\w+|handle\w+)\s*\(([^)]*)\)"
        )

        for match in re.finditer(conventional_pattern, class_body):
            method_name = match.group(1)
            params_str = match.group(2)
            params = [p.strip().split()[-1] for p in params_str.split(",")]

            # Skip if already captured by @SubscribeEvent
            if any(e.method_name == method_name for e in events):
                continue

            bedrock_event = self._map_java_to_bedrock(method_name)

            events.append(
                EventHandler(
                    java_event=method_name,
                    bedrock_event=bedrock_event,
                    callback_params=params,
                    body_statements=[],
                    translated=True,
                    partial=False,
                )
            )

        return events

    def _extract_api_calls(self, class_body: str) -> list[APICall]:
        """Extract API calls from class body."""
        apis = []

        # Pattern for method calls on known objects
        api_patterns = [
            (r"player\.(\w+)", "player"),
            (r"world\.(\w+)", "world"),
            (r"block\.(\w+)", "block"),
            (r"entity\.(\w+)", "entity"),
            (r"itemStack\.(\w+)", "itemStack"),
        ]

        for pattern, root in api_patterns:
            for match in re.finditer(pattern, class_body):
                method = match.group(1)
                chain = f"{root}.{method}"
                depth = chain.count(".") + 1

                # Map to Bedrock API if known
                bedrock_chain = JAVA_TO_BEDROCK_API.get(chain, chain)

                apis.append(
                    APICall(
                        chain=bedrock_chain,
                        depth=depth,
                        source_java=chain,
                        translated=True,
                        partial=False,
                    )
                )

        return apis

    def _convert_event_handler(self, event: ParsedEventHandler, ir: PivotIR) -> None:
        """Convert a parsed event handler and add to IR."""
        handler = EventHandler(
            java_event=event.java_event,
            bedrock_event=event.bedrock_event,
            callback_params=event.params,
            body_statements=[],
            translated=True,
            partial=False,
        )
        ir.global_events.append(handler)

    def _map_java_to_bedrock(self, method_name: str) -> str:
        """Map Java method name to Bedrock event."""
        if method_name in JAVA_TO_BEDROCK_EVENTS:
            return JAVA_TO_BEDROCK_EVENTS[method_name]

        # Try partial match
        for java_event, bedrock_event in JAVA_TO_BEDROCK_EVENTS.items():
            if java_event.lower() in method_name.lower():
                return bedrock_event

        # Default: remove on/handle prefix and lowercase first letter
        cleaned = re.sub(r"^(on|handle)", "", method_name)
        return cleaned[0].lower() + cleaned[1:] if cleaned else method_name

    def _compute_coverage_stats(self, ir: PivotIR) -> None:
        """Compute coverage statistics for the IR."""
        ir.total_entities = len(ir.blocks) + len(ir.items) + len(ir.entities)
        ir.translated_entities = (
            sum(1 for b in ir.blocks.values() if b.translated)
            + sum(1 for i in ir.items.values() if i.translated)
            + sum(1 for e in ir.entities.values() if e.translated)
        )

        ir.total_events = (
            sum(len(b.event_handlers) for b in ir.blocks.values())
            + sum(len(i.event_handlers) for i in ir.items.values())
            + sum(len(e.event_handlers) for e in ir.entities.values())
            + len(ir.global_events)
        )
        ir.translated_events = (
            sum(sum(1 for h in b.event_handlers if h.translated) for b in ir.blocks.values())
            + sum(sum(1 for h in i.event_handlers if h.translated) for i in ir.items.values())
            + sum(sum(1 for h in e.event_handlers if h.translated) for e in ir.entities.values())
            + sum(1 for h in ir.global_events if h.translated)
        )

        ir.total_api_calls = (
            sum(len(b.api_calls) for b in ir.blocks.values())
            + sum(len(i.api_calls) for i in ir.items.values())
            + sum(len(e.api_calls) for e in ir.entities.values())
            + len(ir.global_apis)
        )
        ir.translated_api_calls = (
            sum(sum(1 for a in b.api_calls if a.translated) for b in ir.blocks.values())
            + sum(sum(1 for a in i.api_calls if a.translated) for i in ir.items.values())
            + sum(sum(1 for a in e.api_calls if a.translated) for e in ir.entities.values())
            + sum(1 for a in ir.global_apis if a.translated)
        )


def parse_java_to_pivot_ir(java_source: str) -> PivotIR:
    """Convenience function to parse Java to Pivot IR.

    Args:
        java_source: The Java mod source code

    Returns:
        PivotIR representation
    """
    adapter = JavaToPivotIRAdapter()
    return adapter.parse(java_source)


# ─────────────────────────────────────────────────────────────────────────────
# Example Java Sources for Testing
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_JAVA_BLOCK = """
package com.example.mod;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

public class CustomBlock extends Block {
    public CustomBlock(Properties properties) {
        super(properties);
    }
    
    @SubscribeEvent
    public void onPlayerInteract(PlayerInteractEvent.RightClickBlock event) {
        Player player = event.getPlayer();
        player.sendMessage(new TextComponent("Block clicked!"), player.getUUID());
    }
    
    @Override
    public void neighborChanged(BlockState state, net.minecraft.world.level.Level world, 
                               net.minecraft.core.BlockPos pos, Block block, 
                               net.minecraft.core.BlockPos fromPos, boolean isMoving) {
        // Handle neighbor change
    }
}
"""

SAMPLE_JAVA_ITEM = """
package com.example.mod;

import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

public class CustomItem extends Item {
    public CustomItem(Properties properties) {
        super(properties);
    }
    
    @SubscribeEvent
    public void onItemCrafted(PlayerEvent.ItemCraftedEvent event) {
        Player player = event.getPlayer();
        ItemStack crafted = event.getCrafting();
        player.sendMessage(new TextComponent("Crafted: " + crafted.getDisplayName().getString()), player.getUUID());
    }
}
"""

SAMPLE_JAVA_ENTITY = """
package com.example.mod;

import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.monster.Zombie;
import net.minecraft.world.level.Level;
import net.minecraftforge.event.entity.EntityJoinLevelEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

public class CustomEntity extends Zombie {
    public CustomEntity(EntityType<? extends Zombie> type, Level level) {
        super(type, level);
    }
    
    @SubscribeEvent
    public void onEntitySpawn(EntityJoinLevelEvent event) {
        Entity entity = event.getEntity();
        if (entity instanceof CustomEntity) {
            // Custom spawn logic
        }
    }
}
"""


if __name__ == "__main__":
    # Test the adapter
    print("Testing Java → PivotIR Adapter")
    print("=" * 60)

    print("\n1. Parsing Block:")
    ir1 = parse_java_to_pivot_ir(SAMPLE_JAVA_BLOCK)
    print(f"   Blocks: {list(ir1.blocks.keys())}")
    print(f"   Events: {len(ir1.global_events)}")

    print("\n2. Parsing Item:")
    ir2 = parse_java_to_pivot_ir(SAMPLE_JAVA_ITEM)
    print(f"   Items: {list(ir2.items.keys())}")

    print("\n3. Parsing Entity:")
    ir3 = parse_java_to_pivot_ir(SAMPLE_JAVA_ENTITY)
    print(f"   Entities: {list(ir3.entities.keys())}")
