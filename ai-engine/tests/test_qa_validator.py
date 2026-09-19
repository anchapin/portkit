"""
Unit tests for QAValidatorAgent - comprehensive coverage for validation functionality.
"""

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the parent directory to the path to allow imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.qa_validator import QAValidatorAgent, ValidationCache, VALIDATION_RULES
from agents.qa.structure_validator import VALID_BLOCK_COMPONENTS, VALID_SOUND_FORMATS
from agents.qa.report_generator import calculate_overall_score


class TestQAValidatorAgent:
    """Test cases for QAValidatorAgent validation functionality"""

    @pytest.fixture
    def agent(self):
        """Create QAValidatorAgent instance for testing."""
        return QAValidatorAgent.get_instance()

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.fixture
    def mock_mcaddon(self, temp_dir):
        """Create a mock .mcaddon file for testing."""
        addon_path = os.path.join(temp_dir, "test.mcaddon")

        with zipfile.ZipFile(addon_path, "w") as zf:
            # Add manifest.json
            manifest = {
                "format_version": 2,
                "header": {
                    "name": "Test Addon",
                    "description": "Test addon description",
                    "uuid": "12345678-1234-1234-1234-123456789012",
                    "version": [1, 0, 0],
                    "min_engine_version": [1, 19, 0],
                },
                "modules": [
                    {
                        "type": "data",
                        "uuid": "87654321-4321-4321-4321-210987654321",
                        "version": [1, 0, 0],
                    }
                ],
            }
            zf.writestr("manifest.json", json.dumps(manifest))

            # Add block definition
            block_def = {
                "format_version": "1.20.0",
                "minecraft:block": {
                    "description": {"identifier": "test:block"},
                    "components": {"minecraft:block": {}},
                },
            }
            zf.writestr("blocks/test_block.json", json.dumps(block_def))

            # Add item definition
            item_def = {
                "format_version": "1.20.0",
                "minecraft:item": {
                    "description": {"identifier": "test:item"},
                    "components": {"minecraft:max_stack_size": 64},
                },
            }
            zf.writestr("items/test_item.json", json.dumps(item_def))

            # Add texture
            zf.writestr("textures/blocks/test_block.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        return addon_path

    def test_singleton_pattern(self):
        """Test singleton pattern for QAValidatorAgent"""
        agent1 = QAValidatorAgent.get_instance()
        agent2 = QAValidatorAgent.get_instance()
        assert agent1 is agent2

    def test_validation_rules_exist(self):
        """Test that validation rules are defined"""
        assert "manifest" in VALIDATION_RULES
        assert "blocks" in VALIDATION_RULES
        assert "items" in VALIDATION_RULES

    def test_quality_thresholds(self, agent):
        """Test quality thresholds are defined"""
        assert "feature_conversion_rate" in agent.quality_thresholds
        assert "assumption_accuracy" in agent.quality_thresholds
        assert "bedrock_compatibility" in agent.quality_thresholds

    def test_validation_categories(self, agent):
        """Test validation categories are defined"""
        assert "structural" in agent.validation_categories
        assert "asset_validity" in agent.validation_categories
        assert "semantic_accuracy" in agent.validation_categories
        assert "best_practices" in agent.validation_categories

    def test_valid_block_components(self, agent):
        """Test valid block components are defined"""
        assert "minecraft:block" in VALID_BLOCK_COMPONENTS
        assert "minecraft:collision_box" in VALID_BLOCK_COMPONENTS
        assert "minecraft:geometry" in VALID_BLOCK_COMPONENTS

    def test_valid_sound_formats(self, agent):
        """Test valid sound formats are defined"""
        assert ".ogg" in VALID_SOUND_FORMATS
        assert ".wav" in VALID_SOUND_FORMATS

    def test_pass_threshold(self, agent):
        """Test pass threshold default value"""
        assert agent.pass_threshold == 0.70

    def test_validate_mcaddon_tool(self, agent, mock_mcaddon):
        """Test validate_mcaddon_tool"""
        result = agent.validate_mcaddon_tool.invoke({"mcaddon_path": mock_mcaddon})
        result_data = json.loads(result)
        assert result_data.get("success") is True

    def test_validate_mcaddon_tool_invalid_path(self, agent):
        """Test validate_mcaddon_tool with invalid path"""
        result = agent.validate_mcaddon_tool.invoke({"mcaddon_path": "/nonexistent/path/addon.mcaddon"})
        result_data = json.loads(result)
        # Should handle gracefully

    def test_validate_conversion_quality_tool(self, agent):
        """Test validate_conversion_quality_tool"""
        input_data = json.dumps({"mcaddon_path": "/fake/path/addon.mcaddon"})
        result = agent.validate_conversion_quality_tool.invoke({"quality_data": input_data})
        result_data = json.loads(result)

    def test_run_functional_tests_tool(self, agent):
        """Test run_functional_tests_tool"""
        input_data = json.dumps({"mcaddon_path": "/fake/path/addon.mcaddon"})
        result = agent.run_functional_tests_tool.invoke({"test_data": input_data})
        result_data = json.loads(result)

    def test_analyze_bedrock_compatibility_tool(self, agent):
        """Test analyze_bedrock_compatibility_tool"""
        input_data = json.dumps({"mcaddon_path": "/fake/path/addon.mcaddon"})
        result = agent.analyze_bedrock_compatibility_tool.invoke({"compatibility_data": input_data})
        result_data = json.loads(result)

    def test_assess_performance_metrics_tool(self, agent):
        """Test assess_performance_metrics_tool"""
        input_data = json.dumps({"mcaddon_path": "/fake/path/addon.mcaddon"})
        result = agent.assess_performance_metrics_tool.invoke({"performance_data": input_data})
        result_data = json.loads(result)

    def test_generate_qa_report_tool(self, agent, mock_mcaddon):
        """Test generate_qa_report_tool"""
        input_data = json.dumps({"mod_info": {"name": "Test Mod"}, "mcaddon_path": mock_mcaddon})
        result = agent.generate_qa_report_tool.invoke({"report_data": input_data})
        result_data = json.loads(result)
        assert result_data.get("success") is True

    def test_get_tools(self, agent):
        """Test that get_tools returns a list"""
        tools = agent.get_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_validate_mcaddon_method(self, agent, mock_mcaddon):
        """Test validate_mcaddon method directly"""
        result = agent.validate_mcaddon(mock_mcaddon)
        assert result is not None

    def test_validate_conversion_quality_method(self, agent):
        """Test validate_conversion_quality method"""
        input_data = json.dumps({"mcaddon_path": "/fake/path"})
        result = agent.validate_conversion_quality(input_data)
        result_data = json.loads(result)

    def test_run_functional_tests_method(self, agent):
        """Test run_functional_tests method"""
        input_data = json.dumps({"mcaddon_path": "/fake/path"})
        result = agent.run_functional_tests(input_data)
        result_data = json.loads(result)

    def test_analyze_bedrock_compatibility_method(self, agent):
        """Test analyze_bedrock_compatibility method"""
        input_data = json.dumps({"mcaddon_path": "/fake/path"})
        result = agent.analyze_bedrock_compatibility(input_data)
        result_data = json.loads(result)

    def test_assess_performance_metrics_method(self, agent):
        """Test assess_performance_metrics method"""
        input_data = json.dumps({"mcaddon_path": "/fake/path"})
        result = agent.assess_performance_metrics(input_data)
        result_data = json.loads(result)

    def test_generate_qa_report_method(self, agent):
        """Test generate_qa_report method"""
        input_data = json.dumps({"validation_results": {"overall_score": 85, "checks": []}})
        result = agent.generate_qa_report(input_data)
        result_data = json.loads(result)


class TestValidationCache:
    """Test cases for ValidationCache"""

    def test_cache_set_and_get(self):
        """Test cache set and get operations"""
        cache = ValidationCache()
        cache.set("test_key", {"data": "test_value"})

        result = cache.get("test_key")
        assert result is not None
        assert result["data"] == "test_value"

    def test_cache_get_miss(self):
        """Test cache get with missing key"""
        cache = ValidationCache()
        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_clear(self):
        """Test cache clear operation"""
        cache = ValidationCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration"""
        cache = ValidationCache()
        cache._cache_ttl = 0  # Immediate expiration for testing

        cache.set("test_key", "test_value")
        result = cache.get("test_key")

        # Should be expired
        assert result is None

    def test_generate_key_missing_file(self):
        """Test cache key generation for missing file"""
        cache = ValidationCache()
        key = cache.generate_key(Path("/nonexistent/file.txt"))
        assert key.startswith("missing_")


class TestQAValidatorEdgeCases:
    """Test edge cases and error handling"""

    @pytest.fixture
    def agent(self):
        return QAValidatorAgent.get_instance()

    def test_quality_score_calculation_low_scores(self, agent):
        """Test quality score calculation with low scores"""
        validation_results = {
            "validations": {
                "structural": {"passed": 3, "score": 30, "checks": 10},
                "asset_validity": {"passed": 2, "score": 20, "checks": 10},
                "semantic_accuracy": {"passed": 1, "score": 10, "checks": 10},
                "best_practices": {"passed": 4, "score": 40, "checks": 10},
                "bedrock_compatibility": {"passed": 0, "score": 0, "checks": 10},
            }
        }
        score = calculate_overall_score(validation_results, agent.validation_categories)
        assert score < 50

    def test_quality_score_calculation_high_scores(self, agent):
        """Test quality score calculation with high scores"""
        validation_results = {
            "validations": {
                "structural": {"passed": 9, "score": 95, "checks": 10},
                "asset_validity": {"passed": 9, "score": 90, "checks": 10},
                "semantic_accuracy": {"passed": 8, "score": 88, "checks": 10},
                "best_practices": {"passed": 9, "score": 92, "checks": 10},
                "bedrock_compatibility": {"passed": 10, "score": 100, "checks": 10},
            }
        }
        score = calculate_overall_score(validation_results, agent.validation_categories)
        assert score > 85


class TestQAValidatorIntegration:
    """Integration tests for QAValidatorAgent"""

    @pytest.fixture
    def agent(self):
        return QAValidatorAgent.get_instance()

    def test_full_validation_workflow(self, agent, tmp_path):
        temp_dir = str(tmp_path)
        """Test full validation workflow"""
        # Create a minimal valid addon
        addon_path = os.path.join(temp_dir, "valid_addon.mcaddon")

        with zipfile.ZipFile(addon_path, "w") as zf:
            manifest = {
                "format_version": 2,
                "header": {
                    "name": "Valid Addon",
                    "description": "A valid test addon",
                    "uuid": "12345678-1234-1234-1234-123456789012",
                    "version": [1, 0, 0],
                },
                "modules": [],
            }
            zf.writestr("manifest.json", json.dumps(manifest))

        # Validate the addon
        result = agent.validate_mcaddon(addon_path)

        assert result is not None
        assert "status" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
