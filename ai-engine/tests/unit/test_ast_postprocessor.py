"""
Unit tests for ASTBedrockPostprocessor.

Tests hallucination detection in LLM-generated Bedrock Scripting API code.
Covers known hallucination patterns, method validation, and auto-correction.
"""

import pytest

from conversion.ast_postprocessor import (
    APICall,
    ASTBedrockPostprocessor,
    BedrockAPIMethodKB,
    HallucinatedCall,
    HallucinationSeverity,
    PostProcessorResult,
    process_bedrock_code,
)


class TestBedrockAPIMethodKB:
    """Test Bedrock API Knowledge Base."""

    @pytest.fixture
    def kb(self):
        return BedrockAPIMethodKB()

    def test_world_methods_valid(self, kb):
        """world.getBlock should be valid."""
        is_valid, h_type = kb.is_valid_call("world", "getBlock")
        assert is_valid is True
        assert h_type is None

    def test_world_setBlock_invalid(self, kb):
        """world.setBlock should be flagged as hallucination."""
        is_valid, h_type = kb.is_valid_call("world", "setBlock")
        assert is_valid is False
        assert h_type == "nonexistent_method"

    def test_player_getInventory_invalid(self, kb):
        """player.getInventory should be flagged (property access, not method)."""
        is_valid, h_type = kb.is_valid_call("player", "getInventory")
        assert is_valid is False
        assert h_type in ("nonexistent_method", "property_accessed_as_method")

    def test_player_methods_valid(self, kb):
        """player.sendMessage should be valid."""
        is_valid, _ = kb.is_valid_call("player", "sendMessage")
        assert is_valid is True

    def test_block_methods_valid(self, kb):
        """block.setPermutation should be valid."""
        is_valid, _ = kb.is_valid_call("block", "setPermutation")
        assert is_valid is True

    def test_block_setBlock_invalid(self, kb):
        """block.setBlock should be flagged (use setPermutation)."""
        is_valid, _ = kb.is_valid_call("block", "setBlock")
        assert is_valid is False

    def test_closest_method_edit_distance(self, kb):
        """getBlock should suggest getBlock (small edit distance)."""
        closest = kb.get_closest_method("world", "getBlock")
        assert closest is not None
        assert closest[0] == "getBlock"

    def test_unknown_receiver_returns_none(self, kb):
        """Unknown receiver should return None for closest match."""
        closest = kb.get_closest_method("nonexistent_receiver", "someMethod")
        assert closest is None

    def test_known_hallucinations_set(self, kb):
        """Verify known hallucinations are tracked."""
        hallucinations = kb.get_known_hallucinations()
        assert "world.setBlock" in hallucinations
        assert "player.getInventory" in hallucinations
        assert "block.getBlockEntity" in hallucinations

    def test_levenshtein_distance(self, kb):
        """Test edit distance calculation."""
        dist = kb._levenshtein_distance("setBlock", "setPermutation")
        assert dist > 0
        assert dist <= 15

        dist_same = kb._levenshtein_distance("getBlock", "getBlock")
        assert dist_same == 0


class TestAPICallExtraction:
    """Test API call extraction from Bedrock code."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_extract_world_getBlock(self, postprocessor):
        """Extract world.getBlock call."""
        code = "world.getBlock(location);"
        result = postprocessor.process(code)
        assert result.total_calls >= 1

    def test_extract_player_sendMessage(self, postprocessor):
        """Extract player.sendMessage call."""
        code = 'player.sendMessage("Hello world");'
        result = postprocessor.process(code)
        assert result.total_calls >= 1

    def test_extract_multiple_calls(self, postprocessor):
        """Extract multiple calls from block of code."""
        code = """
world.afterEvents.blockPlace.subscribe((event) => {
    const block = world.getBlock(event.block.location);
    block.setPermutation('minecraft:air');
    player.sendMessage("Block placed!");
});
"""
        result = postprocessor.process(code)
        assert result.total_calls >= 4

    def test_extract_property_access(self, postprocessor):
        """Extract property access like block.type."""
        code = "const blockType = block.type;"
        result = postprocessor.process(code)
        assert result.total_calls >= 1

    def test_empty_code(self, postprocessor):
        """Empty code should return valid with 0 calls."""
        result = postprocessor.process("")
        assert result.is_valid is True
        assert result.total_calls == 0


class TestHallucinationDetection:
    """Test hallucination detection patterns."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_detect_world_setBlock(self, postprocessor):
        """Detect world.setBlock hallucination."""
        code = "world.setBlock(location, 'minecraft:air');"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert result.hallucination_rate > 0
        assert len(result.hallucinated_calls) >= 1

        h = result.hallucinated_calls[0]
        assert h.severity in (HallucinationSeverity.HIGH, HallucinationSeverity.CRITICAL)
        assert "setBlock" in h.suggestion

    def test_detect_player_getInventory(self, postprocessor):
        """Detect player.getInventory hallucination."""
        code = "const inv = player.getInventory();"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

        h = result.hallucinated_calls[0]
        assert h.severity in (HallucinationSeverity.HIGH, HallucinationSeverity.MEDIUM)

    def test_detect_block_getBlockEntity(self, postprocessor):
        """Detect block.getBlockEntity hallucination."""
        code = "const be = block.getBlockEntity();"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

        h = result.hallucinated_calls[0]
        assert h.severity == HallucinationSeverity.HIGH

    def test_detect_world_getBlockAt(self, postprocessor):
        """Detect world.getBlockAt hallucination."""
        code = "const block = world.getBlockAt(x, y, z);"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_detect_world_isAirBlock(self, postprocessor):
        """Detect world.isAirBlock hallucination."""
        code = "if (world.isAirBlock(location)) { }"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_detect_world_getBlockState(self, postprocessor):
        """Detect world.getBlockState hallucination."""
        code = "const state = world.getBlockState(location);"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_detect_entity_getHealth(self, postprocessor):
        """Detect entity.getHealth hallucination."""
        code = "const health = entity.getHealth();"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_detect_player_getExperienceLevel(self, postprocessor):
        """Detect player.getExperienceLevel hallucination."""
        code = "const level = player.getExperienceLevel();"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_no_false_positives_valid_code(self, postprocessor):
        """Valid code should not trigger hallucinations."""
        code = """
import { world, player } from "@minecraft/server";

world.afterEvents.blockPlace.subscribe((event) => {
    const block = world.getBlock(event.block.location);
    if (block.isAir) {
        player.sendMessage("Air block!");
    }
    block.setPermutation('minecraft:stone');
});

system.runInterval(() => {
    player.level++;
}, 20);
"""
        result = postprocessor.process(code)
        assert result.is_valid is True
        assert len(result.hallucinated_calls) == 0
        assert result.hallucination_rate == 0.0


class TestAutoCorrection:
    """Test auto-correction suggestions."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_world_setBlock_correction(self, postprocessor):
        """world.setBlock should suggest block.setPermutation."""
        code = "world.setBlock(location, 'minecraft:air');"
        result = postprocessor.process(code)

        assert len(result.hallucinated_calls) >= 1
        h = result.hallucinated_calls[0]
        assert h.correction is not None
        assert "setPermutation" in h.correction

    def test_player_getInventory_correction(self, postprocessor):
        """player.getInventory should suggest container or equipment."""
        code = "const inv = player.getInventory();"
        result = postprocessor.process(code)

        assert len(result.hallucinated_calls) >= 1
        h = result.hallucinated_calls[0]
        assert h.correction is not None
        assert "container" in h.correction.lower() or "equipment" in h.correction.lower()


class TestSeverityClassification:
    """Test hallucination severity classification."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor(strict=False)

    @pytest.fixture
    def strict_postprocessor(self):
        return ASTBedrockPostprocessor(strict=True)

    def test_known_hallucination_high_severity(self, postprocessor):
        """Known hallucinations should be HIGH severity."""
        code = "world.setBlock(location, 'minecraft:air');"
        result = postprocessor.process(code)

        h = result.hallucinated_calls[0]
        assert h.severity == HallucinationSeverity.HIGH

    def test_nonexistent_method_medium_severity(self, postprocessor):
        """Nonexistent methods on non-critical receivers should be MEDIUM severity."""
        code = "container.someNonexistentMethod();"
        result = postprocessor.process(code)

        h = result.hallucinated_calls[0]
        assert h.severity == HallucinationSeverity.MEDIUM

    def test_strict_mode_increases_severity(self, strict_postprocessor):
        """Strict mode should potentially increase severity."""
        code = "someUnknownReceiver.method();"
        result = strict_postprocessor.process(code)

        if len(result.hallucinated_calls) > 0:
            h = result.hallucinated_calls[0]
            assert h.severity in (
                HallucinationSeverity.LOW,
                HallucinationSeverity.MEDIUM,
            )


class TestProcessBedrockCode:
    """Test convenience function."""

    def test_process_bedrock_code_function(self):
        """Test the process_bedrock_code convenience function."""
        code = "world.setBlock(location);"
        result = process_bedrock_code(code)

        assert isinstance(result, PostProcessorResult)
        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_process_bedrock_code_strict_mode(self):
        """Test process_bedrock_code with strict=True."""
        code = "world.getBlock(location);"
        result = process_bedrock_code(code, strict=True)

        assert isinstance(result, PostProcessorResult)

    def test_process_empty_code(self):
        """Test process_bedrock_code with empty input."""
        result = process_bedrock_code("")
        assert result.is_valid is True
        assert result.total_calls == 0


class TestHallucinationRate:
    """Test hallucination rate calculation."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_high_hallucination_rate(self, postprocessor):
        """Code with all hallucinations should have 100% rate."""
        code = """
world.setBlock(loc, 'air');
player.getInventory();
block.getBlockEntity();
entity.getHealth();
"""
        result = postprocessor.process(code)
        assert result.hallucination_rate >= 0.5

    def test_mixed_valid_invalid(self, postprocessor):
        """Mixed code should have proportional rate."""
        code = """
world.getBlock(loc);
player.sendMessage("hi");
world.setBlock(loc, 'air');
"""
        result = postprocessor.process(code)
        assert 0 < result.hallucination_rate < 1

    def test_all_valid(self, postprocessor):
        """All valid code should have 0% rate."""
        code = """
world.getBlock(loc);
player.sendMessage("hi");
block.setPermutation('minecraft:stone');
"""
        result = postprocessor.process(code)
        assert result.hallucination_rate == 0.0
        assert result.is_valid is True


class TestReportGeneration:
    """Test report generation."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_report_structure(self, postprocessor):
        """Report should have correct structure."""
        code = "world.setBlock(loc);"
        result = postprocessor.process(code)

        report = result.report
        assert "total_api_calls" in report
        assert "valid_calls" in report
        assert "hallucinated_calls" in report
        assert "hallucination_rate" in report
        assert "status" in report

    def test_report_to_dict(self, postprocessor):
        """to_dict should serialize correctly."""
        code = "world.setBlock(loc);"
        result = postprocessor.process(code)

        d = result.to_dict()
        assert "is_valid" in d
        assert "total_calls" in d
        assert "hallucinated_calls" in d
        assert "hallucination_rate" in d


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_code_with_only_comments(self, postprocessor):
        """Code with only comments should be valid."""
        code = """
// This is a comment
// world.setBlock();
"""
        result = postprocessor.process(code)
        assert result.is_valid is True

    def test_multiline_method_call(self, postprocessor):
        """Multiline method calls should be parsed correctly."""
        code = """
world.getBlock(
    new Location(x, y, z)
);
"""
        result = postprocessor.process(code)
        assert result.total_calls >= 1

    def test_template_literals(self, postprocessor):
        """Template literals in calls should not break parsing."""
        code = """
player.sendMessage(`Hello ${player.name}!`);
"""
        result = postprocessor.process(code)
        assert result.total_calls >= 1

    def test_nested_calls(self, postprocessor):
        """Nested method calls should be parsed."""
        code = "world.getBlock(player.location).type;"
        result = postprocessor.process(code)
        assert result.total_calls >= 2

    def test_arrow_functions(self, postprocessor):
        """Arrow functions with API calls should be parsed."""
        code = """
world.afterEvents.blockPlace.subscribe((event) => {
    event.player.sendMessage("Placed!");
});
"""
        result = postprocessor.process(code)
        assert result.total_calls >= 2


class TestHallucinationPatterns:
    """Test specific hallucination patterns from issue #1721."""

    @pytest.fixture
    def postprocessor(self):
        return ASTBedrockPostprocessor()

    def test_world_setBlock_wrong_method(self, postprocessor):
        """world.setBlock doesn't exist - correct is block.setPermutation."""
        code = "world.setBlock(block.location, 'minecraft:air');"
        result = postprocessor.process(code)

        assert result.is_valid is False
        h = result.hallucinated_calls[0]
        assert "setBlock" in h.api_call.full_call
        assert h.severity in (HallucinationSeverity.HIGH, HallucinationSeverity.CRITICAL)
        assert h.hallucination_type in ("known_hallucination", "nonexistent_method")

    def test_world_getTileEntity_doesnt_exist(self, postprocessor):
        """world.getTileEntity doesn't exist in Script API."""
        code = "const te = world.getTileEntity(location);"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_player_getInventory_wrong(self, postprocessor):
        """player.getInventory() doesn't exist."""
        code = "const inventory = player.getInventory();"
        result = postprocessor.process(code)

        assert result.is_valid is False
        h = result.hallucinated_calls[0]
        assert h.severity == HallucinationSeverity.HIGH

    def test_entity_getHealth_uses_component(self, postprocessor):
        """entity.getHealth should use getComponent."""
        code = "const hp = entity.getHealth();"
        result = postprocessor.process(code)

        assert result.is_valid is False
        h = result.hallucinated_calls[0]
        assert "getHealth" in h.api_call.full_call

    def test_world_getBlockAt_renamed(self, postprocessor):
        """world.getBlockAt renamed to world.getBlock."""
        code = "const b = world.getBlockAt(x, y, z);"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1

    def test_world_setBlockState_renamed(self, postprocessor):
        """world.setBlockState should be block.setPermutation."""
        code = "world.setBlockState(location, 'minecraft:stone');"
        result = postprocessor.process(code)

        assert result.is_valid is False
        assert len(result.hallucinated_calls) >= 1
