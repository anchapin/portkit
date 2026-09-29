"""
Unit tests for the vendor translation formalism (ai-engine/conversion/vendor_formalism.py).

Tests cover:
- Canonical IR construct extraction from Java source
- Bedrock code generation from canonical IR
- Formal mapping table completeness
- Semantic delta documentation for no-equivalent constructs
- Round-trip: Java → Canonical IR → Bedrock
"""

import pytest

from conversion.vendor_formalism import (
    BedrockDialectGenerator,
    BlockBreak,
    BlockInteraction,
    ConstructCategory,
    EntitySpawn,
    EventHandler,
    FormalMappingTable,
    JavaDialectParser,
    MappingDelta,
    MappingEntry,
    SemanticEquivalence,
    TickFunction,
    VendorFormalism,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def java_player_interact() -> str:
    return """
package com.example;

import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

public class BlockInteraction {
    @SubscribeEvent
    public static void onPlayerInteract(PlayerInteractEvent.RightClickBlock event) {
        Level level = event.getLevel();
        BlockPos pos = event.getPos();
        Player player = event.getEntity();
        ItemStack stack = event.getItemStack();

        if (!level.isClientSide && stack.is(Items.DIAMOND)) {
            level.setBlockAndUpdate(pos, Blocks.GOLD_BLOCK.defaultBlockState());
            event.setCanceled(true);
        }
    }
}
"""


@pytest.fixture
def java_ticking_tile() -> str:
    return """
package com.example;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;

public class CustomTickingTileEntity extends BlockEntity {
    private int tickCounter = 0;

    public CustomTickingTileEntity(BlockPos pos, BlockState state) {
        super(ModTileEntities.CUSTOM_TICKING_TILE.get(), pos, state);
    }

    public static void tick(Level level, BlockPos pos, BlockState state, CustomTickingTileEntity blockEntity) {
        if (!level.isClientSide) {
            blockEntity.tickCounter++;
            if (blockEntity.tickCounter % 20 == 0) {
                level.playSound(null, pos, SoundTypes.EXPERIENCE_ORB_PICKUP, SoundSource.BLOCKS, 1.0f, 1.0f);
            }
        }
    }
}
"""


@pytest.fixture
def java_block_break() -> str:
    return """
package com.example;

import net.minecraftforge.event.entity.player.PlayerDestroyBlockEvent;

public class BlockBreakHandler {
    @SubscribeEvent
    public static void onBlockBreak(PlayerDestroyBlockEvent event) {
        Level level = event.getLevel();
        BlockPos pos = event.getPos();
        Player player = event.getPlayer();

        if (!level.isClientSide && level.getBlockState(pos).is(Blocks.DIAMOND_BLOCK)) {
            player.sendSystemMessage(Component.literal("You broke a diamond block!"));
            event.setExpToDrop(100);
        }
    }
}
"""


@pytest.fixture
def java_entity_join() -> str:
    return """
package com.example;

import net.minecraftforge.event.entity.EntityJoinLevelEvent;

public class EntitySpawnHandler {
    @SubscribeEvent
    public static void onEntityJoin(EntityJoinLevelEvent event) {
        if (event.getLevel().isClientSide) return;
        // Handle entity spawn
    }
}
"""


@pytest.fixture
def java_mixed() -> str:
    return """
package com.example;

import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

public class MixedHandlers {
    @SubscribeEvent
    public void onPlayerInteract(PlayerInteractEvent.RightClickBlock event) {
        // handle interact
    }
}
"""


# ---------------------------------------------------------------------------
# Tests — Canonical IR Construct Definitions
# ---------------------------------------------------------------------------


class TestEventHandlerIR:
    def test_event_handler_creation(self):
        eh = EventHandler(
            canonical_name="player_interact",
            category=ConstructCategory.EVENT,
            event_type="player_interact_block",
            subscribe_lambda_body="const x = 1;",
            is_after=True,
            semantic_equivalence=SemanticEquivalence.DIRECT,
        )
        assert eh.canonical_name == "player_interact"
        assert eh.event_type == "player_interact_block"
        assert eh.is_after is True
        assert eh.semantic_equivalence == SemanticEquivalence.DIRECT

    def test_event_handler_semantic_summary(self):
        eh = EventHandler(
            canonical_name="player_interact",
            category=ConstructCategory.EVENT,
            event_type="player_interact_block",
            subscribe_lambda_body="player.sendMessage('hi');",
        )
        summary = eh.semantic_summary()
        assert "player_interact_block" in summary
        assert "player.sendMessage" in summary

    def test_event_handler_to_dict(self):
        eh = EventHandler(
            canonical_name="player_interact",
            category=ConstructCategory.EVENT,
            event_type="player_interact_block",
            subscribe_lambda_body="x++;",
        )
        d = eh.to_dict()
        assert d["canonical_name"] == "player_interact"
        assert d["construct_type"] == "EventHandler"
        assert d["event_type"] == "player_interact_block"
        assert d["semantic_equivalence"] == "DIRECT"


class TestTickFunctionIR:
    def test_tick_function_creation(self):
        tf = TickFunction(
            canonical_name="block_tick",
            category=ConstructCategory.TICK,
            interval_ticks=20,
            tick_body="dimension.playSound('foo');",
            semantic_equivalence=SemanticEquivalence.APPROXIMATE,
        )
        assert tf.interval_ticks == 20
        assert tf.semantic_equivalence == SemanticEquivalence.APPROXIMATE

    def test_tick_function_semantic_summary_hz(self):
        tf = TickFunction(
            canonical_name="block_tick",
            category=ConstructCategory.TICK,
            interval_ticks=20,
            tick_body="foo",
        )
        summary = tf.semantic_summary()
        assert "20 tick" in summary
        assert "1.0 Hz" in summary


class TestBlockInteractionIR:
    def test_block_interaction_defaults(self):
        bi = BlockInteraction(
            canonical_name="block_right_click",
            category=ConstructCategory.BLOCK_INTERACTION,
        )
        assert bi.trigger_item is None
        assert bi.target_block is None
        assert bi.cancelable is True

    def test_block_interaction_to_dict(self):
        bi = BlockInteraction(
            canonical_name="block_right_click",
            category=ConstructCategory.BLOCK_INTERACTION,
            trigger_item="minecraft:diamond",
            target_block="minecraft:gold_block",
            interaction_body="block.setType('iron');",
        )
        d = bi.to_dict()
        assert d["trigger_item"] == "minecraft:diamond"
        assert d["target_block"] == "minecraft:gold_block"
        assert "iron" in d["interaction_body"]


class TestBlockBreakIR:
    def test_block_break_with_xp(self):
        bb = BlockBreak(
            canonical_name="block_break",
            category=ConstructCategory.BLOCK_BREAK,
            block_type="minecraft:diamond_block",
            drop_xp=True,
            break_body="player.giveExperience(100);",
        )
        assert bb.block_type == "minecraft:diamond_block"
        assert bb.drop_xp is True


# ---------------------------------------------------------------------------
# Tests — Java Dialect Parser
# ---------------------------------------------------------------------------


class TestJavaDialectParser:
    def test_parse_player_interact(self, java_player_interact):
        parser = JavaDialectParser()
        constructs = parser.parse(java_player_interact)
        assert len(constructs) >= 1
        event_handlers = [c for c in constructs if isinstance(c, EventHandler)]
        assert len(event_handlers) >= 1

    def test_parse_ticking_tile(self, java_ticking_tile):
        parser = JavaDialectParser()
        constructs = parser.parse(java_ticking_tile)
        tick_funcs = [c for c in constructs if isinstance(c, TickFunction)]
        assert len(tick_funcs) >= 1
        tf = tick_funcs[0]
        assert tf.category == ConstructCategory.TICK
        assert tf.interval_ticks == 1
        assert tf.semantic_equivalence == SemanticEquivalence.APPROXIMATE

    def test_parse_block_break(self, java_block_break):
        parser = JavaDialectParser()
        constructs = parser.parse(java_block_break)
        breaks = [c for c in constructs if isinstance(c, BlockBreak)]
        assert len(breaks) >= 1
        bb = breaks[0]
        assert bb.drop_xp is True

    def test_parse_entity_join(self, java_entity_join):
        parser = JavaDialectParser()
        constructs = parser.parse(java_entity_join)
        spawns = [c for c in constructs if isinstance(c, EntitySpawn)]
        assert len(spawns) >= 1

    def test_parse_mixed(self, java_mixed):
        parser = JavaDialectParser()
        constructs = parser.parse(java_mixed)
        assert len(constructs) >= 1


# ---------------------------------------------------------------------------
# Tests — Bedrock Dialect Generator
# ---------------------------------------------------------------------------


class TestBedrockDialectGenerator:
    def test_generate_event_handler(self):
        generator = BedrockDialectGenerator()
        eh = EventHandler(
            canonical_name="player_interact",
            category=ConstructCategory.EVENT,
            event_type="player_interact_block",
            subscribe_lambda_body="const x = 1;",
        )
        code = generator.generate(eh)
        assert "world.afterEvents.playerInteractWithBlock" in code
        assert "subscribe" in code
        assert "const x = 1;" in code

    def test_generate_event_handler_entity_join(self):
        generator = BedrockDialectGenerator()
        es = EntitySpawn(
            canonical_name="entity_spawn",
            category=ConstructCategory.ENTITY_SPAWN,
            entity_type="minecraft:pig",
            spawn_body="entity.applyDamage(1);",
        )
        code = generator.generate(es)
        assert "world.afterEvents.entitySpawn" in code
        assert "subscribe" in code
        assert "minecraft:pig" in code

    def test_generate_tick_function(self):
        generator = BedrockDialectGenerator()
        tf = TickFunction(
            canonical_name="block_tick",
            category=ConstructCategory.TICK,
            interval_ticks=20,
            tick_body="dimension.playSound('foo');",
            semantic_equivalence=SemanticEquivalence.APPROXIMATE,
        )
        code = generator.generate(tf)
        assert "system.runInterval" in code
        assert "20" in code
        assert "dimension.playSound" in code

    def test_generate_block_interaction_with_filters(self):
        generator = BedrockDialectGenerator()
        bi = BlockInteraction(
            canonical_name="block_right_click",
            category=ConstructCategory.BLOCK_INTERACTION,
            trigger_item="minecraft:diamond",
            target_block="minecraft:gold_block",
            interaction_body="block.setType('iron');",
        )
        code = generator.generate(bi)
        assert "minecraft:diamond" in code
        assert "minecraft:gold_block" in code
        assert "subscribe" in code

    def test_generate_block_break(self):
        generator = BedrockDialectGenerator()
        bb = BlockBreak(
            canonical_name="block_break",
            category=ConstructCategory.BLOCK_BREAK,
            block_type="minecraft:diamond_block",
            drop_xp=True,
            break_body="player.sendMessage('broken!');",
        )
        code = generator.generate(bb)
        assert "world.afterEvents.blockBreak" in code
        assert "subscribe" in code
        assert "minecraft:diamond_block" in code


# ---------------------------------------------------------------------------
# Tests — Formal Mapping Table
# ---------------------------------------------------------------------------


class TestFormalMappingTable:
    def test_table_has_expected_mappings(self):
        table = FormalMappingTable()
        assert table.get("java_player_interact") is not None
        assert table.get("java_ticking_tile") is not None
        assert table.get("java_block_break") is not None
        assert table.get("java_entity_join") is not None

    def test_ticking_tile_has_approximate_equivalence(self):
        table = FormalMappingTable()
        entry = table.get("java_ticking_tile")
        assert entry is not None
        assert entry.equivalence == SemanticEquivalence.APPROXIMATE
        assert len(entry.deltas) >= 1

    def test_event_handler_has_direct_equivalence(self):
        table = FormalMappingTable()
        entry = table.get("java_player_interact")
        assert entry is not None
        assert entry.equivalence == SemanticEquivalence.DIRECT

    def test_block_break_has_xp_delta(self):
        table = FormalMappingTable()
        entry = table.get("java_block_break")
        assert entry is not None
        delta_types = [d.delta_type for d in entry.deltas]
        assert "XP_DROPS" in delta_types

    def test_coverage_report(self):
        table = FormalMappingTable()
        report = table.coverage_report()
        assert report["total_mappings"] >= 5
        assert report["avg_confidence"] > 0.0
        assert report["avg_confidence"] <= 1.0
        assert ConstructCategory.TICK.name in report["categories"]

    def test_get_by_category(self):
        table = FormalMappingTable()
        event_entries = table.get_by_category(ConstructCategory.EVENT)
        assert len(event_entries) >= 1
        tick_entries = table.get_by_category(ConstructCategory.TICK)
        assert len(tick_entries) >= 1


# ---------------------------------------------------------------------------
# Tests — VendorFormalism Orchestrator
# ---------------------------------------------------------------------------


class TestVendorFormalism:
    def test_full_translation_pipeline(self, java_player_interact):
        vf = VendorFormalism()
        results = vf.translate_java_to_bedrock(java_player_interact)
        assert len(results) >= 1
        r = results[0]
        assert "world.afterEvents" in r["bedrock_code"]
        assert r["canonical_ir"]["construct_type"] == "EventHandler"

    def test_ticking_tile_roundtrip(self, java_ticking_tile):
        vf = VendorFormalism()
        results = vf.translate_java_to_bedrock(java_ticking_tile)
        assert len(results) >= 1
        r = results[0]
        assert "system.runInterval" in r["bedrock_code"]
        assert r["confidence"] is not None

    def test_block_break_roundtrip(self, java_block_break):
        vf = VendorFormalism()
        results = vf.translate_java_to_bedrock(java_block_break)
        assert len(results) >= 1
        r = results[0]
        assert "world.afterEvents.blockBreak" in r["bedrock_code"]
        assert r["confidence"] is not None

    def test_entity_join_roundtrip(self, java_entity_join):
        vf = VendorFormalism()
        results = vf.translate_java_to_bedrock(java_entity_join)
        assert len(results) >= 1
        r = results[0]
        assert "world.afterEvents.entitySpawn" in r["bedrock_code"]

    def test_coverage_report_via_formalism(self):
        vf = VendorFormalism()
        report = vf.coverage_report()
        assert report["total_mappings"] >= 5
        assert report["requires_manual_review"] >= 1


# ---------------------------------------------------------------------------
# Tests — Semantic Equivalence Classification
# ---------------------------------------------------------------------------


class TestSemanticEquivalenceClassification:
    def test_direct_equivalence_for_event(self):
        table = FormalMappingTable()
        entry = table.get("java_player_interact")
        assert entry is not None
        assert entry.equivalence == SemanticEquivalence.DIRECT
        assert entry.confidence >= 0.8

    def test_approximate_equivalence_for_tick(self):
        table = FormalMappingTable()
        entry = table.get("java_ticking_tile")
        assert entry is not None
        assert entry.equivalence == SemanticEquivalence.APPROXIMATE
        assert 0.5 <= entry.confidence < 0.9

    def test_delta_has_mmstag(self):
        table = FormalMappingTable()
        entry = table.get("java_ticking_tile")
        assert entry is not None
        for delta in entry.deltas:
            assert delta.mmd_tag != ""
            assert "TICK" in delta.mmd_tag


# ---------------------------------------------------------------------------
# Tests — MappingDelta
# ---------------------------------------------------------------------------


class TestMappingDelta:
    def test_delta_creation(self):
        delta = MappingDelta(
            delta_type="EXECUTION_MODEL",
            java_behavior="Synchronous tick per block",
            bedrock_behavior="Best-effort global timer",
            workaround="Use ticking component",
            mmd_tag="TICK_ORDERING_NON_DETERMINISTIC",
        )
        d = delta.to_dict()
        assert d["delta_type"] == "EXECUTION_MODEL"
        assert d["mmd_tag"] == "TICK_ORDERING_NON_DETERMINISTIC"

    def test_delta_in_entry(self):
        entry = MappingEntry(
            java_construct_id="test_construct",
            canonical_construct=EventHandler(
                canonical_name="test",
                category=ConstructCategory.EVENT,
                event_type="test",
                subscribe_lambda_body="x",
            ),
            bedrock_js_pattern="world.afterEvents.test.subscribe(() => {});",
            confidence=0.7,
            equivalence=SemanticEquivalence.APPROXIMATE,
            deltas=[
                MappingDelta(
                    delta_type="BEHAVIOR",
                    java_behavior="A",
                    bedrock_behavior="B",
                    workaround="C",
                    mmd_tag="TEST_DELTA",
                )
            ],
        )
        assert len(entry.deltas) == 1
        assert entry.deltas[0].mmd_tag == "TEST_DELTA"
