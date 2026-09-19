"""
Direct Gameplay Comparison Agent

This agent implements Mode 1 of the AI-Powered Validation & Comparison system.
It launches Minecraft (Java and Bedrock) locally, runs automated test scripts,
captures screenshots, and compares visual/functional differences between the
original Java mod and converted Bedrock addon.

Issue: #494 (Phase 4a)

Moved into agents/modpack/ subpackage per issue #1729.
"""

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GameTestScript:
    """Represents a test script to run in Minecraft."""

    name: str
    commands: List[str]
    expected_results: List[str]
    timeout_seconds: int = 60


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    path: str
    timestamp: datetime
    game_version: str
    test_name: str
    hash: str
    edition: Optional[str] = None  # Explicit game edition (e.g. "java", "bedrock")


@dataclass
class GameplayComparisonResult:
    """Results from comparing gameplay between Java and Bedrock."""

    conversion_id: str
    java_screenshots: List[Screenshot]
    bedrock_screenshots: List[Screenshot]
    visual_diffs: List[Dict[str, Any]]
    functional_tests: List[Dict[str, Any]]
    overall_score: float
    missing_features: List[str]
    recommendations: List[str]


class MinecraftLauncher:
    """Handles launching Minecraft instances."""

    def __init__(self, java_path: Optional[str] = None, bedrock_path: Optional[str] = None):
        self.java_path = java_path or os.environ.get(
            "MINECRAFT_JAVA_PATH", "/opt/minecraft-launcher"
        )
        self.bedrock_path = bedrock_path or os.environ.get(
            "MINECRAFT_BEDROCK_PATH", "/opt/minecraft-bedrock"
        )
        self.running_instances: Dict[str, Optional[subprocess.Popen[Any]]] = {}

    def is_java_installed(self) -> bool:
        """Check if Java Minecraft is available."""
        return os.path.exists(self.java_path) or self._check_java_command()

    def is_bedrock_installed(self) -> bool:
        """Check if Bedrock Minecraft is available."""
        return os.path.exists(self.bedrock_path)

    def _check_java_command(self) -> bool:
        """Check if Minecraft launcher command is available."""
        try:
            result = subprocess.run(["which", "minecraft-launcher"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def launch_java(self, version: str = "1.20.4", username: str = "TestBot") -> bool:
        """Launch Java Edition Minecraft."""
        print(f"Launching Minecraft Java Edition {version} as {username}...")
        # In production, this would use the Minecraft Launcher API or launch directly
        # For now, we simulate the launch
        try:
            # Placeholder for actual launch logic
            print(f"[MOCK] Java Edition launched at {datetime.now()}")
            self.running_instances["java"] = None  # type: ignore[assignment]
            return True
        except Exception as e:
            print(f"Failed to launch Java Edition: {e}")
            return False

    def launch_bedrock(self, version: str = "1.20.60") -> bool:
        """Launch Bedrock Edition Minecraft."""
        print(f"Launching Minecraft Bedrock Edition {version}...")
        try:
            # Placeholder for actual launch logic
            print(f"[MOCK] Bedrock Edition launched at {datetime.now()}")
            self.running_instances["bedrock"] = None  # type: ignore[assignment]
            return True
        except Exception as e:
            print(f"Failed to launch Bedrock Edition: {e}")
            return False

    def stop_instance(self, edition: str) -> None:
        """Stop a running Minecraft instance."""
        if edition in self.running_instances:
            print(f"Stopping Minecraft {edition}...")
            # In production, would terminate the process
            del self.running_instances[edition]

    def close_all(self) -> None:
        """Close all running instances."""
        for edition in list(self.running_instances.keys()):
            self.stop_instance(edition)


class GameplayTestRunner:
    """Runs automated test scripts in Minecraft."""

    def __init__(self, screenshot_dir: str = "/tmp/minecraft_screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots: List[Screenshot] = []

    def run_test_script(
        self, game_edition: str, script: GameTestScript, game_version: str
    ) -> Dict[str, Any]:
        """Execute a test script and capture results."""
        print(f"Running test '{script.name}' on {game_edition}...")

        results: Dict[str, Any] = {
            "test_name": script.name,
            "game_edition": game_edition,
            "commands_executed": [],
            "commands_succeeded": [],
            "commands_failed": [],
            "screenshots_captured": [],
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "success": False,
        }

        for command in script.commands:
            results["commands_executed"].append(command)

            # In production, would send command via RCON or in-game chat
            # Simulating command execution
            try:
                # Mock command execution
                time.sleep(0.5)  # Simulate command processing time
                results["commands_succeeded"].append(command)
                print(f"  ✓ Executed: {command}")
            except Exception as e:
                results["commands_failed"].append({"command": command, "error": str(e)})
                print(f"  ✗ Failed: {command} - {e}")

        # Capture screenshot after test
        screenshot = self._capture_screenshot(game_edition, script.name, game_version)
        if screenshot:
            results["screenshots_captured"].append(screenshot.path)
            self.screenshots.append(screenshot)

        results["end_time"] = datetime.now().isoformat()
        results["success"] = len(results["commands_failed"]) == 0

        return results

    def _capture_screenshot(
        self, game_edition: str, test_name: str, game_version: str
    ) -> Optional[Screenshot]:
        """Capture a screenshot from the game."""
        timestamp = datetime.now()
        filename = f"{game_edition}_{test_name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
        filepath = self.screenshot_dir / filename

        # In production, would trigger in-game screenshot or use screen capture
        # For now, create a placeholder file
        placeholder_content = f"Screenshot: {game_edition} - {test_name}"

        try:
            # Create a placeholder (in production, actual screenshot)
            with open(filepath, "w") as f:
                f.write(placeholder_content)

            # Calculate hash
            with open(filepath, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            screenshot = Screenshot(
                path=str(filepath),
                timestamp=timestamp,
                game_version=game_version,
                test_name=test_name,
                hash=file_hash,
                edition=game_edition,
            )
            print(f"  📸 Screenshot captured: {filename}")
            return screenshot
        except Exception as e:
            print(f"  ⚠ Failed to capture screenshot: {e}")
            return None

    def get_screenshots(self, game_edition: Optional[str] = None) -> List[Screenshot]:
        """Get all captured screenshots, optionally filtered by game edition."""
        if game_edition is None:
            return self.screenshots

        # Filter on the structured edition field instead of doing substring matches on the path
        return [s for s in self.screenshots if s.edition == game_edition]


class ScreenshotComparator:
    """Compares screenshots to detect visual differences."""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def compare_screenshots(
        self, java_screenshot: Screenshot, bedrock_screenshot: Screenshot
    ) -> Dict:
        """Compare two screenshots and return difference metrics."""
        print(f"Comparing screenshots: {java_screenshot.path} vs {bedrock_screenshot.path}")

        # In production, would use image comparison algorithms
        # For now, use hash comparison
        hashes_match = java_screenshot.hash == bedrock_screenshot.hash

        # Calculate similarity (mock)
        similarity = 1.0 if hashes_match else 0.65  # Mock value

        return {
            "java_screenshot": java_screenshot.path,
            "bedrock_screenshot": bedrock_screenshot.path,
            "hashes_match": hashes_match,
            "similarity_score": similarity,
            "similar": similarity >= self.similarity_threshold,
            "differences_detected": not (similarity >= self.similarity_threshold),
            "timestamp_diff_seconds": abs(
                (java_screenshot.timestamp - bedrock_screenshot.timestamp).total_seconds()
            ),
        }

    def generate_visual_diff(
        self, java_screenshot: Screenshot, bedrock_screenshot: Screenshot
    ) -> bytes:
        """Generate a visual diff image between two screenshots."""
        # In production, would generate actual diff image
        # For now, return a placeholder
        return b"MOCK_VISUAL_DIFF"

    def compare_all_pairs(
        self, java_screenshots: List[Screenshot], bedrock_screenshots: List[Screenshot]
    ) -> List[Dict]:
        """Compare all possible pairs of screenshots."""
        comparisons = []

        for java_ss in java_screenshots:
            for bedrock_ss in bedrock_screenshots:
                if java_ss.test_name == bedrock_ss.test_name:
                    comparison = self.compare_screenshots(java_ss, bedrock_ss)
                    comparisons.append(comparison)

        return comparisons


class GameplayComparisonAgent:
    """
    Main agent for direct gameplay comparison between Java and Bedrock.

    This agent:
    1. Launches both Minecraft editions
    2. Runs automated test scripts
    3. Captures and compares screenshots
    4. Generates validation reports
    """

    def __init__(
        self,
        java_minecraft_path: Optional[str] = None,
        bedrock_minecraft_path: Optional[str] = None,
        screenshot_dir: str = "/tmp/minecraft_screenshots",
    ):
        self.launcher = MinecraftLauncher(java_minecraft_path, bedrock_minecraft_path)
        self.test_runner = GameplayTestRunner(screenshot_dir)
        self.comparator = ScreenshotComparator()
        self.results: List[GameplayComparisonResult] = []

        # Default test scripts
        self.default_tests = self._create_default_test_scripts()

    def _create_default_test_scripts(self) -> List[GameTestScript]:
        """Create default test scripts for validation."""
        return [
            GameTestScript(
                name="block_placement",
                commands=[
                    "/give TestBot minecraft:stone 64",
                    "/setblock ~ ~ ~ minecraft:stone",
                    "/fill ~ ~ ~ ~10 ~10 ~10 minecraft:stone",
                ],
                expected_results=["Item received", "Block placed", "Area filled"],
                timeout_seconds=30,
            ),
            GameTestScript(
                name="item_crafting",
                commands=[
                    "/give TestBot minecraft:oak_planks 4",
                    "/recipe take *",
                    "/give TestBot minecraft:stick",
                ],
                expected_results=["Planks received", "Recipes unlocked", "Stick crafted"],
                timeout_seconds=30,
            ),
            GameTestScript(
                name="entity_spawn",
                commands=["/summon minecraft:cow", "/summon minecraft:pig", "/kill @e[type=cow]"],
                expected_results=["Cow spawned", "Pig spawned", "Entity killed"],
                timeout_seconds=30,
            ),
            GameTestScript(
                name="custom_block_interaction",
                commands=[
                    "/setblock ~ ~ ~ minecraft:redstone_block",
                    "/testforblock ~ ~ ~ minecraft:redstone_block",
                    "/setblock ~ ~ ~ minecraft:air",
                ],
                expected_results=["Redstone block placed", "Block detected", "Block removed"],
                timeout_seconds=30,
            ),
        ]

    def validate_prerequisites(self) -> Dict[str, bool]:
        """Check if all prerequisites are met."""
        print("Validating prerequisites...")

        checks = {
            "java_installed": self.launcher.is_java_installed(),
            "bedrock_installed": self.launcher.is_bedrock_installed(),
            "screenshot_dir_writable": os.access(self.test_runner.screenshot_dir, os.W_OK),
        }

        all_passed = all(checks.values())
        print(f"Prerequisites validation: {'PASSED' if all_passed else 'FAILED'}")
        for check, result in checks.items():
            status = "✓" if result else "✗"
            print(f"  {status} {check}: {result}")

        return checks

    def run_comparison(
        self,
        conversion_id: str,
        java_mod_path: str,
        bedrock_addon_path: str,
        custom_tests: Optional[List[GameTestScript]] = None,
    ) -> GameplayComparisonResult:
        """
        Run a complete gameplay comparison between Java mod and Bedrock addon.

        Args:
            conversion_id: ID of the conversion to validate
            java_mod_path: Path to the Java mod files
            bedrock_addon_path: Path to the Bedrock addon files
            custom_tests: Optional custom test scripts

        Returns:
            GameplayComparisonResult with all comparison data
        """
        print(f"\n{'=' * 60}")
        print(f"Starting Gameplay Comparison for conversion: {conversion_id}")
        print(f"Java mod path: {java_mod_path}")
        print(f"Bedrock addon path: {bedrock_addon_path}")
        print(f"{'=' * 60}\n")

        # Validate prerequisites
        prereqs = self.validate_prerequisites()
        if not all(prereqs.values()):
            return self._create_error_result(
                conversion_id, "Prerequisites not met: " + str(prereqs)
            )

        tests = custom_tests or self.default_tests
        java_version = "1.20.4"  # Would be determined from mod
        bedrock_version = "1.20.60"  # Would be determined from addon

        # Run tests on Java Edition
        print("\n--- Running tests on Java Edition ---")
        java_results = self._run_test_suite("java", tests, java_version)

        # Run tests on Bedrock Edition
        print("\n--- Running tests on Bedrock Edition ---")
        bedrock_results = self._run_test_suite("bedrock", tests, bedrock_version)

        # Compare results
        print("\n--- Comparing results ---")
        visual_diffs = self._compare_results(java_results, bedrock_results)

        # Generate final report
        result = self._generate_report(conversion_id, java_results, bedrock_results, visual_diffs)

        self.results.append(result)

        # Cleanup
        self.launcher.close_all()

        print(f"\n{'=' * 60}")
        print(f"Comparison complete! Score: {result.overall_score}/100")
        print(f"{'=' * 60}\n")

        return result

    def _run_test_suite(
        self, edition: str, tests: List[GameTestScript], version: str
    ) -> List[Dict]:
        """Run a suite of tests on a specific game edition."""
        results = []

        for test in tests:
            result = self.test_runner.run_test_script(edition, test, version)
            results.append(result)

        return results

    def _compare_results(self, java_results: List[Dict], bedrock_results: List[Dict]) -> List[Dict]:
        """Compare test results between editions."""
        comparisons = []

        java_tests = {r["test_name"]: r for r in java_results}
        bedrock_tests = {r["test_name"]: r for r in bedrock_results}

        for test_name in java_tests:
            if test_name in bedrock_tests:
                java_test = java_tests[test_name]
                bedrock_test = bedrock_tests[test_name]

                comparison = {
                    "test_name": test_name,
                    "java_success": java_test["success"],
                    "bedrock_success": bedrock_test["success"],
                    "java_commands": len(java_test["commands_succeeded"]),
                    "bedrock_commands": len(bedrock_test["commands_succeeded"]),
                    "commands_match": (
                        len(java_test["commands_succeeded"])
                        == len(bedrock_test["commands_succeeded"])
                    ),
                    "java_screenshots": java_test["screenshots_captured"],
                    "bedrock_screenshots": bedrock_test["screenshots_captured"],
                }

                comparisons.append(comparison)

        # Compare screenshots
        java_screenshots = self.test_runner.get_screenshots("java")
        bedrock_screenshots = self.test_runner.get_screenshots("bedrock")

        screenshot_comparisons = self.comparator.compare_all_pairs(
            java_screenshots, bedrock_screenshots
        )

        comparisons.extend(screenshot_comparisons)

        return comparisons

    def _generate_report(
        self,
        conversion_id: str,
        java_results: List[Dict],
        bedrock_results: List[Dict],
        visual_diffs: List[Dict],
    ) -> GameplayComparisonResult:
        """Generate the final comparison report."""

        # Calculate overall score
        java_success_rate = self._calculate_success_rate(java_results)
        bedrock_success_rate = self._calculate_success_rate(bedrock_results)

        # Visual similarity
        visual_similarities = [
            d.get("similarity_score", 0) for d in visual_diffs if "similarity_score" in d
        ]
        avg_visual_similarity = (
            sum(visual_similarities) / len(visual_similarities) if visual_similarities else 0
        )

        # Overall score (weighted average)
        overall_score = (
            (java_success_rate * 0.2) + (bedrock_success_rate * 0.3) + (avg_visual_similarity * 0.5)
        ) * 100

        # Identify missing features
        missing_features = self._identify_missing_features(java_results, bedrock_results)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            java_results, bedrock_results, visual_diffs, overall_score
        )

        return GameplayComparisonResult(
            conversion_id=conversion_id,
            java_screenshots=self.test_runner.get_screenshots("java"),
            bedrock_screenshots=self.test_runner.get_screenshots("bedrock"),
            visual_diffs=visual_diffs,
            functional_tests=visual_diffs,
            overall_score=round(overall_score, 2),
            missing_features=missing_features,
            recommendations=recommendations,
        )

    def _calculate_success_rate(self, results: List[Dict]) -> float:
        """Calculate success rate from test results."""
        if not results:
            return 0.0
        successful = sum(1 for r in results if r.get("success", False))
        return successful / len(results)

    def _identify_missing_features(
        self, java_results: List[Dict], bedrock_results: List[Dict]
    ) -> List[str]:
        """Identify features that work in Java but not Bedrock."""
        missing = []

        java_tests = {r["test_name"]: r for r in java_results}
        bedrock_tests = {r["test_name"]: r for r in bedrock_results}

        for test_name, java_result in java_tests.items():
            bedrock_result = bedrock_tests.get(test_name)

            if not bedrock_result:
                missing.append(f"Test '{test_name}' not run on Bedrock")
            elif java_result.get("success") and not bedrock_result.get("success"):
                failed_cmds = bedrock_result.get("commands_failed", [])
                if failed_cmds:
                    missing.append(
                        f"Test '{test_name}': Failed commands - "
                        + str([c.get("command") for c in failed_cmds])
                    )

        return missing

    def _generate_recommendations(
        self,
        java_results: List[Dict],
        bedrock_results: List[Dict],
        visual_diffs: List[Dict],
        score: float,
    ) -> List[str]:
        """Generate recommendations based on comparison results."""
        recommendations = []

        if score < 50:
            recommendations.append("Critical: Conversion quality is low. Review all features.")
        elif score < 75:
            recommendations.append(
                "Warning: Some features may not work correctly. Manual testing recommended."
            )
        else:
            recommendations.append("Good: Most features appear to work correctly.")

        # Check for specific issues
        java_failures = [r for r in java_results if not r.get("success")]
        bedrock_failures = [r for r in bedrock_results if not r.get("success")]

        if java_failures:
            recommendations.append(f"Java Edition has {len(java_failures)} failing tests")

        if bedrock_failures:
            recommendations.append(
                f"Bedrock Edition has {len(bedrock_failures)} failing tests - "
                + "these may be limitations of the Bedrock platform"
            )

        # Visual diff recommendations
        visual_issues = [d for d in visual_diffs if d.get("differences_detected", False)]
        if visual_issues:
            recommendations.append(f"Visual differences detected in {len(visual_issues)} tests")

        return recommendations

    def _create_error_result(
        self, conversion_id: str, error_message: str
    ) -> GameplayComparisonResult:
        """Create an error result."""
        return GameplayComparisonResult(
            conversion_id=conversion_id,
            java_screenshots=[],
            bedrock_screenshots=[],
            visual_diffs=[],
            functional_tests=[],
            overall_score=0.0,
            missing_features=[error_message],
            recommendations=["Fix prerequisites and retry comparison"],
        )

    def get_result(self, conversion_id: str) -> Optional[GameplayComparisonResult]:
        """Get a previous result by conversion ID."""
        for result in self.results:
            # Would need to store conversion_id in result
            pass
        return None

    def export_report(self, result: GameplayComparisonResult, output_path: str) -> None:
        """Export the comparison report to a file."""
        report_dict = {
            "overall_score": result.overall_score,
            "java_screenshots": [
                {"path": s.path, "timestamp": s.timestamp.isoformat(), "hash": s.hash}
                for s in result.java_screenshots
            ],
            "bedrock_screenshots": [
                {"path": s.path, "timestamp": s.timestamp.isoformat(), "hash": s.hash}
                for s in result.bedrock_screenshots
            ],
            "visual_diffs": result.visual_diffs,
            "functional_tests": result.functional_tests,
            "missing_features": result.missing_features,
            "recommendations": result.recommendations,
        }

        with open(output_path, "w") as f:
            json.dump(report_dict, f, indent=2)

        print(f"Report exported to: {output_path}")


if __name__ == "__main__":
    # Demo usage
    print("Initializing Gameplay Comparison Agent...")

    agent = GameplayComparisonAgent()

    # Check prerequisites
    prereqs = agent.validate_prerequisites()

    # Note: In production, would need actual Minecraft installations
    # For demo, we'll create mock results

    print("\n" + "=" * 60)
    print("Demo: Run comparison (mock)")
    print("=" * 60)

    # This would fail without actual Minecraft, but shows the API
    # result = agent.run_comparison(
    #     conversion_id="conv_001",
    #     java_mod_path="/path/to/java/mod",
    #     bedrock_addon_path="/path/to/bedrock/addon"
    # )

    # Create a mock result for demonstration
    mock_result = GameplayComparisonResult(
        conversion_id="demo_conv",
        java_screenshots=[],
        bedrock_screenshots=[],
        visual_diffs=[],
        functional_tests=[],
        overall_score=85.5,
        missing_features=[],
        recommendations=[
            "Gameplay comparison requires Minecraft installations",
            "Install Java and Bedrock editions to run actual tests",
        ],
    )

    print(f"\nMock Overall Score: {mock_result.overall_score}/100")
    print(f"Recommendations: {mock_result.recommendations}")
