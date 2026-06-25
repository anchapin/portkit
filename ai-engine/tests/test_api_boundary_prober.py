"""
Tests for the BedrockAPIBoundaryProber (Issue #1724).

Tests cover:
- Demand-side Java code analysis
- Supply-side KB querying for Bedrock APIs
- Context snippet generation for prompt injection
- Post-generation hallucination validation
- Integration scenarios where converter previously hallucinated
"""

import pytest


try:
    from conversion.api_boundary_prober import (
        BedrockAPIBoundaryProber,
        DemandGuidedContext,
        HallucinationValidationResult,
        JavaConstruct,
    )

    IMPORTS_AVAILABLE = True
    IMPORT_ERROR = None
except ImportError as e:
    IMPORTS_AVAILABLE = False
    IMPORT_ERROR = str(e)


pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE, reason=f"Required imports unavailable: {IMPORT_ERROR}"
)


JAVA_CODE_BLOCK_PLACED = """
public class MyBlock extends Block {
    public MyBlock() {
        super(Properties.of(Material.STONE));
    }

    @Override
    public void onPlaced(World world, BlockPos pos, BlockState state) {
        world.playSound(pos, SoundEvents.BLOCK_STONE_PLACE, SoundSource.BLOCKS, 1.0F, 1.0F);
    }

    @Override
    public void onBroken(World world, BlockPos pos, BlockState state) {
        world.setBlock(pos, Blocks.AIR);
    }
}
"""

JAVA_CODE_ENTITY_DEATH = """
public class MyEntity extends Entity {
    @Override
    public void onDeath(DamageSource source) {
        this.world.playSound(this.getPos(), SoundEvents.ENTITY_GENERIC_DEATH, SoundSource.HOSTILE, 1.0F, 1.0F);
    }
}
"""

JAVA_CODE_TILE_ENTITY = """
public class MyTileEntity extends TileEntity {
    private int tickCount = 0;

    @Override
    public void tick() {
        tickCount++;
        if (tickCount > 100) {
            world.setBlock(this.pos, Blocks.AIR);
        }
    }
}
"""

BEDROCK_CODE_VALID = """
import { world, system } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    const block = event.block;
    if (block.typeId === "mod:my_block") {
        world.playSound("block.stone.place", block.location);
    }
});

world.afterEvents.playerBreakBlock.subscribe((event) => {
    const block = event.block;
    if (block.typeId === "mod:my_block") {
        block.dimension.setBlock(block.location, "minecraft:air");
    }
});
"""

BEDROCK_CODE_HALLUCINATED_SEND_MESSAGE = """
import { world, player } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    player.sendMessage("Block placed!");
});
"""

BEDROCK_CODE_HALLUCINATED_GET_INVENTORY = """
import { world, player } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    const inventory = player.getInventory();
    inventory.addItem("minecraft:diamond");
});
"""

BEDROCK_CODE_HALLUCINATED_BLOCK_ENTITY = """
import { world, Block } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    const block = event.block;
    const tileEntity = block.getBlockEntity();
});
"""


class TestBedrockAPIBoundaryProber:
    """Tests for BedrockAPIBoundaryProber class."""

    def test_prober_initialization(self):
        """Test prober initializes correctly."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        assert prober.strict_api is True
        assert prober._known_script_api_methods is not None
        assert prober._known_classes is not None

    def test_prober_initialization_non_strict(self):
        """Test prober initializes in non-strict mode."""
        prober = BedrockAPIBoundaryProber(strict_api=False)
        assert prober.strict_api is False

    def test_probe_java_demand_block_placed(self):
        """Test Java demand probing for Block onPlaced pattern."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        constructs = prober.probe_java_demand(JAVA_CODE_BLOCK_PLACED)

        assert len(constructs) > 0
        method_names = [c.name for c in constructs]
        assert "onPlaced" in method_names or "onBroken" in method_names

    def test_probe_java_demand_entity_death(self):
        """Test Java demand probing for Entity onDeath pattern."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        constructs = prober.probe_java_demand(JAVA_CODE_ENTITY_DEATH)

        assert len(constructs) > 0

    def test_probe_java_demand_tile_entity_tick(self):
        """Test Java demand probing for TileEntity tick pattern."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        constructs = prober.probe_java_demand(JAVA_CODE_TILE_ENTITY)

        assert len(constructs) > 0
        construct_types = [c.construct_type for c in constructs]
        assert "method" in construct_types or "event_handler" in construct_types

    def test_probe_kb_supply_returns_surfaces(self):
        """Test KB supply probing returns BedrockAPISurface objects."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        surfaces = prober.probe_kb_supply(["world.afterEvents.blockPlace"])

        assert isinstance(surfaces, list)

    def test_generate_context_snippet_empty_for_no_supply(self):
        """Test context snippet generation with no supply returns empty string."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        snippet = prober.generate_context_snippet([], [])

        assert snippet == ""

    def test_generate_context_snippet_contains_api_section(self):
        """Test context snippet contains 'Available Bedrock APIs' section."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        from conversion.api_boundary_prober import BedrockAPISurface

        surfaces = [
            BedrockAPISurface(
                api_name="world.afterEvents.blockPlace",
                api_type="event",
                description="Subscribe to block placement events",
                source_pattern="bedrock_block_entity",
                relevance_score=0.9,
            )
        ]
        snippet = prober.generate_context_snippet([], surfaces)

        assert "## Available Bedrock APIs for this task:" in snippet
        assert "world.afterEvents.blockPlace" in snippet

    def test_build_demand_guided_context(self):
        """Test full demand-guided context building."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        context = prober.build_demand_guided_context(JAVA_CODE_BLOCK_PLACED)

        assert isinstance(context, DemandGuidedContext)
        assert isinstance(context.java_constructs, list)
        assert isinstance(context.bedrock_api_surfaces, list)
        assert isinstance(context.context_snippet, str)
        assert isinstance(context.api_categories_found, set)

    def test_validate_output_valid_code(self):
        """Test validation of valid Bedrock code passes."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        result = prober.validate_output(BEDROCK_CODE_VALID)

        assert isinstance(result, HallucinationValidationResult)
        assert result.is_valid is True
        assert len(result.hallucinated_apis) == 0

    def test_validate_output_hallucinated_send_message(self):
        """Test validation catches hallucinated player.sendMessage()."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        result = prober.validate_output(BEDROCK_CODE_HALLUCINATED_SEND_MESSAGE)

        assert result.is_valid is False
        assert len(result.hallucinated_apis) > 0
        assert "player.sendMessage()" in result.hallucinated_apis

    def test_validate_output_hallucinated_get_inventory(self):
        """Test validation catches hallucinated player.getInventory()."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        result = prober.validate_output(BEDROCK_CODE_HALLUCINATED_GET_INVENTORY)

        assert result.is_valid is False
        assert len(result.hallucinated_apis) > 0
        assert "player.getInventory()" in result.hallucinated_apis

    def test_validate_output_hallucinated_block_entity(self):
        """Test validation catches hallucinated block.getBlockEntity()."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        result = prober.validate_output(BEDROCK_CODE_HALLUCINATED_BLOCK_ENTITY)

        assert result.is_valid is False
        assert len(result.hallucinated_apis) > 0
        assert "block.getBlockEntity()" in result.hallucinated_apis

    def test_get_injection_prompt_strict_api_enabled(self):
        """Test injection prompt returns content when strict_api is enabled."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        prompt = prober.get_injection_prompt(JAVA_CODE_BLOCK_PLACED)

        assert isinstance(prompt, str)

    def test_get_injection_prompt_strict_api_disabled(self):
        """Test injection prompt returns empty when strict_api is disabled."""
        prober = BedrockAPIBoundaryProber(strict_api=False)
        prompt = prober.get_injection_prompt(JAVA_CODE_BLOCK_PLACED)

        assert prompt == ""

    def test_known_script_api_methods_loaded(self):
        """Test that known Script API methods are loaded from patterns."""
        prober = BedrockAPIBoundaryProber(strict_api=True)

        assert len(prober._known_script_api_methods) > 0
        assert "sendMessage" in prober._known_script_api_methods
        assert "runInterval" in prober._known_script_api_methods

    def test_known_classes_loaded(self):
        """Test that known Bedrock Script API classes are loaded."""
        prober = BedrockAPIBoundaryProber(strict_api=True)

        assert len(prober._known_classes) > 0


class TestHallucinationPreventionScenarios:
    """Test cases for specific hallucination scenarios the prober should prevent."""

    def test_scenario_player_send_message_hallucination(self):
        """Test that hallucinated player.sendMessage() is detected.

        Scenario: Java code has onPlaced event that should play a sound.
        LLM previously generated: player.sendMessage() which doesn't exist.
        With prober: Should detect this hallucination.
        """
        prober = BedrockAPIBoundaryProber(strict_api=True)

        hallucinated_code = """
import { world, player } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    player.sendMessage("Block placed at " + event.block.location);
});
"""
        result = prober.validate_output(hallucinated_code)

        assert result.is_valid is False
        assert "player.sendMessage()" in result.hallucinated_apis

    def test_scenario_block_entity_hallucination(self):
        """Test that hallucinated block.getBlockEntity() is detected.

        Scenario: Java code has TileEntity that needs data storage.
        LLM previously generated: block.getBlockEntity() which doesn't exist in Bedrock.
        With prober: Should suggest block.setDynamicProperty() instead.
        """
        prober = BedrockAPIBoundaryProber(strict_api=True)

        hallucinated_code = """
import { world, Block } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    const block = event.block;
    const tileEntity = block.getBlockEntity();
    tileEntity.setData("count", 1);
});
"""
        result = prober.validate_output(hallucinated_code)

        assert result.is_valid is False
        assert "block.getBlockEntity()" in result.hallucinated_apis

    def test_scenario_world_set_block_with_block_object(self):
        """Test that hallucinated world.setBlock() with Block object is detected.

        Scenario: Java code sets block to AIR.
        LLM previously generated: world.setBlock(pos, Block.air) which doesn't work.
        With prober: Should suggest dimension.setBlock() with permutation or air string.
        """
        prober = BedrockAPIBoundaryProber(strict_api=True)

        hallucinated_code = """
import { world, Block } from "@minecraft/server";

world.afterEvents.playerBreakBlock.subscribe((event) => {
    const pos = event.block.location;
    world.setBlock(pos, Block.air);
});
"""
        result = prober.validate_output(hallucinated_code)

        assert result.is_valid is False
        assert "world.setBlock" in str(result.hallucinated_apis)


class TestDemandGuidedContextInjection:
    """Tests for demand-guided context injection into converter prompts."""

    def test_demand_guided_context_includes_java_needs(self):
        """Test that context includes Java constructs that need Bedrock APIs."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        context = prober.build_demand_guided_context(JAVA_CODE_BLOCK_PLACED)

        assert len(context.java_constructs) > 0
        assert len(context.bedrock_api_surfaces) > 0

    def test_demand_guided_context_api_rules_included(self):
        """Test that context includes API usage rules."""
        prober = BedrockAPIBoundaryProber(strict_api=True)
        context = prober.build_demand_guided_context(JAVA_CODE_BLOCK_PLACED)

        assert "### API Usage Rules" in context.context_snippet
        assert "player.sendMessage" in context.context_snippet or "world.playSound" in context.context_snippet

    def test_context_snippet_limits_surfaces_per_category(self):
        """Test that context snippet limits surfaces to prevent overflow."""
        prober = BedrockAPIBoundaryProber(strict_api=True)

        from conversion.api_boundary_prober import BedrockAPISurface

        many_surfaces = [
            BedrockAPISurface(
                api_name=f"api_{i}",
                api_type="event",
                description=f"Description {i}",
                source_pattern="test",
                relevance_score=0.5 + (i * 0.01),
            )
            for i in range(20)
        ]
        snippet = prober.generate_context_snippet([], many_surfaces)

        lines = snippet.split("\n")
        api_lines = [l for l in lines if l.startswith("- `api_")]
        assert len(api_lines) <= 10
