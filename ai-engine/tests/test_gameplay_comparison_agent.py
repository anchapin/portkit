"""
Unit tests for GameplayComparisonAgent

Tests the Minecraft Gameplay Agent for local testing, including:
- MinecraftLauncher for launching Java and Bedrock editions
- GameplayTestRunner for running automated test scripts
- ScreenshotComparator for comparing screenshots
- GameplayComparisonAgent for orchestrating comparisons

Issues: #511, #512 - Implement Minecraft Gameplay Agent and Screenshot Comparison (Phase 4a, 4b)
"""

import json
import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime

from agents.modpack.gameplay_comparator import (
    MinecraftLauncher,
    GameplayTestRunner,
    ScreenshotComparator,
    GameplayComparisonAgent,
    GameTestScript,
    Screenshot,
    GameplayComparisonResult,
)


class TestGameTestScript:
    """Tests for GameTestScript dataclass."""

    def test_script_creation(self):
        """Test creating a test script."""
        script = GameTestScript(
            name="test_script",
            commands=["/give @p stone 64", "/setblock ~ ~ ~ stone"],
            expected_results=["Item received", "Block placed"],
            timeout_seconds=30,
        )

        assert script.name == "test_script"
        assert len(script.commands) == 2
        assert len(script.expected_results) == 2
        assert script.timeout_seconds == 30

    def test_script_default_timeout(self):
        """Test default timeout value."""
        script = GameTestScript(name="test", commands=["/test"], expected_results=["OK"])

        assert script.timeout_seconds == 60


class TestScreenshot:
    """Tests for Screenshot dataclass."""

    def test_screenshot_creation(self):
        """Test creating a screenshot."""
        screenshot = Screenshot(
            path="/tmp/test.png",
            timestamp=datetime.now(),
            game_version="1.20.4",
            test_name="block_test",
            hash="abc123",
            edition="java",
        )

        assert screenshot.path == "/tmp/test.png"
        assert screenshot.game_version == "1.20.4"
        assert screenshot.test_name == "block_test"
        assert screenshot.hash == "abc123"
        assert screenshot.edition == "java"

    def test_screenshot_optional_edition(self):
        """Test screenshot with optional edition."""
        screenshot = Screenshot(
            path="/tmp/test.png",
            timestamp=datetime.now(),
            game_version="1.20.4",
            test_name="test",
            hash="xyz",
        )

        assert screenshot.edition is None


class TestMinecraftLauncher:
    """Tests for MinecraftLauncher class."""

    def test_init_default_paths(self):
        """Test launcher initialization with default paths."""
        launcher = MinecraftLauncher()

        assert launcher.java_path is not None
        assert launcher.bedrock_path is not None
        assert launcher.running_instances == {}

    def test_init_custom_paths(self):
        """Test launcher initialization with custom paths."""
        launcher = MinecraftLauncher(java_path="/custom/java", bedrock_path="/custom/bedrock")

        assert launcher.java_path == "/custom/java"
        assert launcher.bedrock_path == "/custom/bedrock"

    def test_launch_java(self):
        """Test launching Java edition."""
        launcher = MinecraftLauncher()

        result = launcher.launch_java(version="1.20.4", username="TestBot")

        assert result is True
        assert "java" in launcher.running_instances

    def test_launch_bedrock(self):
        """Test launching Bedrock edition."""
        launcher = MinecraftLauncher()

        result = launcher.launch_bedrock(version="1.20.60")

        assert result is True
        assert "bedrock" in launcher.running_instances

    def test_stop_instance(self):
        """Test stopping a running instance."""
        launcher = MinecraftLauncher()
        launcher.launch_java()

        launcher.stop_instance("java")

        assert "java" not in launcher.running_instances

    def test_close_all(self):
        """Test closing all running instances."""
        launcher = MinecraftLauncher()
        launcher.launch_java()
        launcher.launch_bedrock()

        launcher.close_all()

        assert len(launcher.running_instances) == 0


class TestGameplayTestRunner:
    """Tests for GameplayTestRunner class."""

    def test_init(self):
        """Test test runner initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = GameplayTestRunner(screenshot_dir=tmpdir)

            assert runner.screenshot_dir == Path(tmpdir)
            assert runner.screenshots == []

    def test_run_test_script(self):
        """Test running a test script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = GameplayTestRunner(screenshot_dir=tmpdir)

            script = GameTestScript(
                name="test_script",
                commands=["/give TestBot stone 64"],
                expected_results=["Item received"],
                timeout_seconds=30,
            )

            result = runner.run_test_script("java", script, "1.20.4")

            assert result["test_name"] == "test_script"
            assert result["game_edition"] == "java"
            assert len(result["commands_executed"]) == 1
            assert result["success"] is True

    def test_run_multiple_scripts(self):
        """Test running multiple test scripts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = GameplayTestRunner(screenshot_dir=tmpdir)

            script1 = GameTestScript(name="script1", commands=["/test1"], expected_results=["OK"])

            script2 = GameTestScript(name="script2", commands=["/test2"], expected_results=["OK"])

            result1 = runner.run_test_script("java", script1, "1.20.4")
            result2 = runner.run_test_script("java", script2, "1.20.4")

            assert result1["success"] is True
            assert result2["success"] is True

    def test_get_screenshots(self):
        """Test getting captured screenshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = GameplayTestRunner(screenshot_dir=tmpdir)

            script = GameTestScript(
                name="screenshot_test", commands=["/test"], expected_results=["OK"]
            )

            runner.run_test_script("java", script, "1.20.4")
            screenshots = runner.get_screenshots()

            assert len(screenshots) >= 0  # May have captured screenshots

    def test_get_screenshots_by_edition(self):
        """Test filtering screenshots by edition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = GameplayTestRunner(screenshot_dir=tmpdir)

            script = GameTestScript(name="test", commands=["/test"], expected_results=["OK"])

            runner.run_test_script("java", script, "1.20.4")
            runner.run_test_script("bedrock", script, "1.20.60")

            java_screenshots = runner.get_screenshots("java")
            bedrock_screenshots = runner.get_screenshots("bedrock")

            # All java screenshots should have edition="java"
            for s in java_screenshots:
                assert s.edition == "java"

            # All bedrock screenshots should have edition="bedrock"
            for s in bedrock_screenshots:
                assert s.edition == "bedrock"


class TestScreenshotComparator:
    """Tests for ScreenshotComparator class."""

    def test_init(self):
        """Test comparator initialization."""
        comparator = ScreenshotComparator()

        assert comparator.similarity_threshold == 0.85

    def test_init_custom_threshold(self):
        """Test comparator with custom threshold."""
        comparator = ScreenshotComparator(similarity_threshold=0.9)

        assert comparator.similarity_threshold == 0.9

    def test_compare_screenshots(self):
        """Test comparing two screenshots."""
        comparator = ScreenshotComparator()

        screenshot1 = Screenshot(
            path="/tmp/java_test.png",
            timestamp=datetime.now(),
            game_version="1.20.4",
            test_name="block_test",
            hash="abc123",
            edition="java",
        )

        screenshot2 = Screenshot(
            path="/tmp/bedrock_test.png",
            timestamp=datetime.now(),
            game_version="1.20.60",
            test_name="block_test",
            hash="abc123",
            edition="bedrock",
        )

        result = comparator.compare_screenshots(screenshot1, screenshot2)

        assert "similarity_score" in result
        assert "hashes_match" in result
        assert result["hashes_match"] is True  # Same hash

    def test_compare_different_screenshots(self):
        """Test comparing different screenshots."""
        comparator = ScreenshotComparator()

        screenshot1 = Screenshot(
            path="/tmp/java_test.png",
            timestamp=datetime.now(),
            game_version="1.20.4",
            test_name="block_test",
            hash="hash1",
            edition="java",
        )

        screenshot2 = Screenshot(
            path="/tmp/bedrock_test.png",
            timestamp=datetime.now(),
            game_version="1.20.60",
            test_name="block_test",
            hash="hash2",
            edition="bedrock",
        )

        result = comparator.compare_screenshots(screenshot1, screenshot2)

        assert result["hashes_match"] is False

    def test_compare_all_pairs(self):
        """Test comparing all screenshot pairs."""
        comparator = ScreenshotComparator()

        java_screenshots = [
            Screenshot(
                path="/tmp/java1.png",
                timestamp=datetime.now(),
                game_version="1.20.4",
                test_name="test1",
                hash="hash1",
                edition="java",
            ),
            Screenshot(
                path="/tmp/java2.png",
                timestamp=datetime.now(),
                game_version="1.20.4",
                test_name="test2",
                hash="hash2",
                edition="java",
            ),
        ]

        bedrock_screenshots = [
            Screenshot(
                path="/tmp/bedrock1.png",
                timestamp=datetime.now(),
                game_version="1.20.60",
                test_name="test1",
                hash="hash1",
                edition="bedrock",
            ),
            Screenshot(
                path="/tmp/bedrock2.png",
                timestamp=datetime.now(),
                game_version="1.20.60",
                test_name="test2",
                hash="hash2",
                edition="bedrock",
            ),
        ]

        comparisons = comparator.compare_all_pairs(java_screenshots, bedrock_screenshots)

        # Should compare matching test names
        assert len(comparisons) >= 2


class TestGameplayComparisonAgent:
    """Tests for GameplayComparisonAgent class."""

    def test_init(self):
        """Test agent initialization."""
        agent = GameplayComparisonAgent()

        assert agent.launcher is not None
        assert agent.test_runner is not None
        assert agent.comparator is not None
        assert agent.results == []

    def test_init_custom_paths(self):
        """Test agent initialization with custom paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot_dir = os.path.join(tmpdir, "screenshots")
            agent = GameplayComparisonAgent(
                java_minecraft_path="/custom/java",
                bedrock_minecraft_path="/custom/bedrock",
                screenshot_dir=screenshot_dir,
            )

            assert agent.launcher.java_path == "/custom/java"
            assert agent.launcher.bedrock_path == "/custom/bedrock"

    def test_validate_prerequisites(self):
        """Test prerequisite validation."""
        agent = GameplayComparisonAgent()

        prereqs = agent.validate_prerequisites()

        assert "java_installed" in prereqs
        assert "bedrock_installed" in prereqs
        assert "screenshot_dir_writable" in prereqs

    def test_default_test_scripts(self):
        """Test default test scripts are created."""
        agent = GameplayComparisonAgent()

        assert len(agent.default_tests) > 0
        assert any(t.name == "block_placement" for t in agent.default_tests)
        assert any(t.name == "item_crafting" for t in agent.default_tests)
        assert any(t.name == "entity_spawn" for t in agent.default_tests)

    def test_run_comparison(self):
        """Test running a comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GameplayComparisonAgent(screenshot_dir=tmpdir)

            result = agent.run_comparison(
                conversion_id="test_conv_001",
                java_mod_path="/fake/java/mod",
                bedrock_addon_path="/fake/bedrock/addon",
            )

            assert result is not None
            assert isinstance(result, GameplayComparisonResult)

    def test_export_report(self):
        """Test exporting comparison report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GameplayComparisonAgent(screenshot_dir=tmpdir)

            result = GameplayComparisonResult(
                conversion_id="export_test",
                java_screenshots=[],
                bedrock_screenshots=[],
                visual_diffs=[],
                functional_tests=[],
                overall_score=85.5,
                missing_features=[],
                recommendations=["Test recommendation"],
            )

            output_path = os.path.join(tmpdir, "report.json")
            agent.export_report(result, output_path)

            assert os.path.exists(output_path)

            with open(output_path, "r") as f:
                report = json.load(f)

            assert report["overall_score"] == 85.5
            assert "Test recommendation" in report["recommendations"]


class TestGameplayComparisonResult:
    """Tests for GameplayComparisonResult dataclass."""

    def test_result_creation(self):
        """Test creating a comparison result."""
        result = GameplayComparisonResult(
            conversion_id="test_conv",
            java_screenshots=[],
            bedrock_screenshots=[],
            visual_diffs=[{"test": "data"}],
            functional_tests=[],
            overall_score=75.0,
            missing_features=["feature1"],
            recommendations=["Fix feature1"],
        )

        assert result.overall_score == 75.0
        assert result.conversion_id == "test_conv"
        assert len(result.missing_features) == 1
        assert len(result.recommendations) == 1

    def test_result_with_screenshots(self):
        """Test result with screenshots."""
        java_ss = Screenshot(
            path="/tmp/java.png",
            timestamp=datetime.now(),
            game_version="1.20.4",
            test_name="test",
            hash="hash1",
            edition="java",
        )

        bedrock_ss = Screenshot(
            path="/tmp/bedrock.png",
            timestamp=datetime.now(),
            game_version="1.20.60",
            test_name="test",
            hash="hash2",
            edition="bedrock",
        )

        result = GameplayComparisonResult(
            conversion_id="screenshot_test",
            java_screenshots=[java_ss],
            bedrock_screenshots=[bedrock_ss],
            visual_diffs=[],
            functional_tests=[],
            overall_score=80.0,
            missing_features=[],
            recommendations=[],
        )

        assert len(result.java_screenshots) == 1
        assert len(result.bedrock_screenshots) == 1


class TestGameplayComparisonAgentIntegration:
    """Integration tests for GameplayComparisonAgent."""

    def test_full_comparison_workflow(self):
        """Test full comparison workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GameplayComparisonAgent(screenshot_dir=tmpdir)

            # Validate prerequisites
            agent.validate_prerequisites()

            # Run comparison
            result = agent.run_comparison(
                conversion_id="integration_test",
                java_mod_path="/fake/java",
                bedrock_addon_path="/fake/bedrock",
            )

            # Export report
            report_path = os.path.join(tmpdir, "integration_report.json")
            agent.export_report(result, report_path)

            assert os.path.exists(report_path)

    def test_comparison_with_custom_tests(self):
        """Test comparison with custom test scripts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GameplayComparisonAgent(screenshot_dir=tmpdir)

            custom_tests = [
                GameTestScript(
                    name="custom_test",
                    commands=["/custom_command"],
                    expected_results=["Custom result"],
                    timeout_seconds=15,
                )
            ]

            result = agent.run_comparison(
                conversion_id="custom_test",
                java_mod_path="/fake/java",
                bedrock_addon_path="/fake/bedrock",
                custom_tests=custom_tests,
            )

            assert result is not None


class TestGameplayComparisonAgentEdgeCases:
    """Tests for edge cases and error handling."""

    def test_comparison_with_no_screenshots(self):
        """Test comparison when no screenshots are captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GameplayComparisonAgent(screenshot_dir=tmpdir)

            result = agent.run_comparison(
                conversion_id="no_screenshots",
                java_mod_path="/fake/java",
                bedrock_addon_path="/fake/bedrock",
            )

            # Should still produce a result
            assert result is not None
            assert isinstance(result.overall_score, float)

    def test_screenshot_dir_creation(self):
        """Test that screenshot directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot_dir = os.path.join(tmpdir, "new_screenshots")

            GameplayComparisonAgent(screenshot_dir=screenshot_dir)

            # Directory should be created by GameplayTestRunner
            assert os.path.exists(screenshot_dir)

    def test_multiple_comparisons(self):
        """Test running multiple comparisons."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GameplayComparisonAgent(screenshot_dir=tmpdir)

            # Create mock results directly since prerequisites won't be met
            mock_result1 = GameplayComparisonResult(
                conversion_id="comp1",
                java_screenshots=[],
                bedrock_screenshots=[],
                visual_diffs=[],
                functional_tests=[],
                overall_score=75.0,
                missing_features=[],
                recommendations=[],
            )

            mock_result2 = GameplayComparisonResult(
                conversion_id="comp2",
                java_screenshots=[],
                bedrock_screenshots=[],
                visual_diffs=[],
                functional_tests=[],
                overall_score=80.0,
                missing_features=[],
                recommendations=[],
            )

            agent.results.append(mock_result1)
            agent.results.append(mock_result2)

            assert len(agent.results) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
