"""
Unit tests for ModpackOrchestrator

Tests the ModpackOrchestrator class for coordinating modpack conversion workflow.
Integrates CurseForge parser, Modrinth parser, dependency analyzer, and conflict detector.

Issue: #515 - Implement Modpack Conversion Orchestrator (Phase 5e)
"""

import json
import pytest
import tempfile
import zipfile
from pathlib import Path

from agents.modpack.orchestrator import (
    ModpackOrchestrator,
    ModpackConversionCrew,
    ModpackInfo,
    ModpackAnalysisResult,
    PackFormat,
    modpack_orchestrator,
)


# Sample CurseForge manifest for testing
SAMPLE_CURSEFORGE_MANIFEST = {
    "manifestType": "minecraftModpack",
    "manifestVersion": 1,
    "name": "Test Modpack",
    "version": "1.0.0",
    "author": "TestAuthor",
    "description": "A test modpack for orchestrator testing",
    "minecraft": {"version": "1.20.1", "modLoaders": [{"id": "forge-47.0.0", "primary": True}]},
    "overrides": "overrides",
    "files": [
        {
            "projectID": 123456,
            "fileID": 987654,
            "name": "TestMod",
            "version": "1.0.0",
            "filename": "testmod-1.0.0.jar",
            "required": True,
            "dependencies": [{"projectID": 654321, "fileID": 111111}],
        },
        {
            "projectID": 654321,
            "fileID": 111111,
            "name": "DependencyMod",
            "version": "2.0.0",
            "filename": "depmod-2.0.0.jar",
            "required": True,
            "dependencies": [],
        },
    ],
}


# Sample Modrinth pack for testing
SAMPLE_MODRINTH_INDEX = {
    "format_version": 1,
    "game": "minecraft",
    "version_id": "1.0.0",
    "name": "Test Modrinth Pack",
    "pack": {
        "name": "Test Modrinth Pack",
        "version": "1.0.0",
        "description": "A test Modrinth modpack",
    },
    "dependencies": {"minecraft": "1.20.1", "fabric-loader": "0.14.0"},
    "files": [
        {
            "path": "mods/testmod.jar",
            "hashes": {"sha1": "abc123", "sha512": "def456"},
            "env": {"client": "required", "server": "required"},
            "downloads": ["https://example.com/testmod.jar"],
            "fileSize": 1024,
        }
    ],
}


class TestPackFormat:
    """Tests for PackFormat enum."""

    def test_pack_format_values(self):
        """Test PackFormat enum values."""
        assert PackFormat.CURSEFORGE.value == "curseforge"
        assert PackFormat.MODRINTH.value == "modrinth"
        assert PackFormat.UNKNOWN.value == "unknown"


class TestModpackInfo:
    """Tests for ModpackInfo dataclass."""

    def test_modpack_info_creation(self):
        """Test creating ModpackInfo."""
        info = ModpackInfo(
            name="Test Pack",
            version="1.0.0",
            author="TestAuthor",
            description="Test description",
            format=PackFormat.CURSEFORGE,
            minecraft_version="1.20.1",
            mod_count=10,
        )

        assert info.name == "Test Pack"
        assert info.version == "1.0.0"
        assert info.author == "TestAuthor"
        assert info.format == PackFormat.CURSEFORGE
        assert info.minecraft_version == "1.20.1"
        assert info.mod_count == 10

    def test_modpack_info_with_mods(self):
        """Test ModpackInfo with mods list."""
        mods = [{"name": "mod1"}, {"name": "mod2"}]
        info = ModpackInfo(
            name="Test",
            version="1.0",
            author="Author",
            description="Desc",
            format=PackFormat.MODRINTH,
            minecraft_version="1.20.0",
            mod_count=2,
            mods=mods,
        )

        assert len(info.mods) == 2


class TestModpackAnalysisResult:
    """Tests for ModpackAnalysisResult dataclass."""

    def test_default_result(self):
        """Test default ModpackAnalysisResult."""
        result = ModpackAnalysisResult()

        assert result.success is False
        assert result.error_message is None
        assert result.modpack_info is None
        assert result.dependency_result is None
        assert result.conflict_result is None
        assert result.recommended_load_order == []
        assert result.warnings == []
        assert result.recommendations == []

    def test_result_with_error(self):
        """Test ModpackAnalysisResult with error."""
        result = ModpackAnalysisResult(success=False, error_message="Test error")

        assert result.success is False
        assert result.error_message == "Test error"


class TestModpackOrchestrator:
    """Tests for ModpackOrchestrator class."""

    def test_init(self):
        """Test orchestrator initialization."""
        orchestrator = ModpackOrchestrator()

        assert orchestrator.curseforge_parser is not None
        assert orchestrator.modrinth_parser is not None
        assert orchestrator.dependency_analyzer is not None
        assert orchestrator.conflict_detector is not None

    def test_detect_format_curseforge(self):
        """Test detecting CurseForge format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            orchestrator = ModpackOrchestrator()
            detected = orchestrator.detect_format(pack_path)

            assert detected == PackFormat.CURSEFORGE

    def test_detect_format_modrinth(self):
        """Test detecting Modrinth format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            index_path = pack_path / "modrinth.index.json"
            index_path.write_text(json.dumps(SAMPLE_MODRINTH_INDEX))

            orchestrator = ModpackOrchestrator()
            detected = orchestrator.detect_format(pack_path)

            assert detected == PackFormat.MODRINTH

    def test_detect_format_unknown(self):
        """Test detecting unknown format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)

            orchestrator = ModpackOrchestrator()
            detected = orchestrator.detect_format(pack_path)

            assert detected == PackFormat.UNKNOWN

    def test_detect_format_curseforge_zip(self):
        """Test detecting CurseForge format from zip file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "test.zip"

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("manifest.json", json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            orchestrator = ModpackOrchestrator()
            detected = orchestrator.detect_format(zip_path)

            assert detected == PackFormat.CURSEFORGE

    def test_detect_format_modrinth_mrpack(self):
        """Test detecting Modrinth format from mrpack file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mrpack_path = Path(tmpdir) / "test.mrpack"

            with zipfile.ZipFile(mrpack_path, "w") as zf:
                zf.writestr("modrinth.index.json", json.dumps(SAMPLE_MODRINTH_INDEX))

            orchestrator = ModpackOrchestrator()
            detected = orchestrator.detect_format(mrpack_path)

            assert detected == PackFormat.MODRINTH

    def test_parse_curseforge_modpack(self):
        """Test parsing CurseForge modpack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            orchestrator = ModpackOrchestrator()
            result = orchestrator.parse_modpack(pack_path, PackFormat.CURSEFORGE)

            assert result is not None
            assert result["metadata"]["name"] == "Test Modpack"
            assert result["mod_count"] == 2

    def test_parse_modrinth_modpack(self):
        """Test parsing Modrinth modpack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            index_path = pack_path / "modrinth.index.json"
            index_path.write_text(json.dumps(SAMPLE_MODRINTH_INDEX))

            orchestrator = ModpackOrchestrator()
            result = orchestrator.parse_modpack(pack_path, PackFormat.MODRINTH)

            assert result is not None
            assert result["metadata"]["name"] == "Test Modrinth Pack"
            assert result["file_count"] == 1

    def test_parse_unknown_format_raises(self):
        """Test parsing unknown format raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)

            orchestrator = ModpackOrchestrator()

            with pytest.raises(ValueError, match="Unknown modpack format"):
                orchestrator.parse_modpack(pack_path, PackFormat.UNKNOWN)

    def test_analyze_modpack_curseforge(self):
        """Test analyzing CurseForge modpack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            orchestrator = ModpackOrchestrator()
            result = orchestrator.analyze_modpack(pack_path)

            assert result.success is True
            assert result.modpack_info is not None
            assert result.modpack_info.name == "Test Modpack"
            assert result.modpack_info.format == PackFormat.CURSEFORGE
            assert result.dependency_result is not None
            assert result.conflict_result is not None

    def test_analyze_modpack_modrinth(self):
        """Test analyzing Modrinth modpack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            index_path = pack_path / "modrinth.index.json"
            index_path.write_text(json.dumps(SAMPLE_MODRINTH_INDEX))

            orchestrator = ModpackOrchestrator()
            result = orchestrator.analyze_modpack(pack_path)

            assert result.success is True
            assert result.modpack_info is not None
            assert result.modpack_info.format == PackFormat.MODRINTH

    def test_analyze_modpack_unknown_format(self):
        """Test analyzing modpack with unknown format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)

            orchestrator = ModpackOrchestrator()
            result = orchestrator.analyze_modpack(pack_path)

            assert result.success is False
            assert "Could not detect modpack format" in result.error_message

    def test_generate_report(self):
        """Test generating analysis report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            orchestrator = ModpackOrchestrator()
            analysis_result = orchestrator.analyze_modpack(pack_path)
            report = orchestrator.generate_report(analysis_result)

            assert report["success"] is True
            assert "modpack" in report
            assert report["modpack"]["name"] == "Test Modpack"
            assert "load_order" in report
            assert "recommendations" in report

    def test_generate_report_with_error(self):
        """Test generating report with error."""
        orchestrator = ModpackOrchestrator()
        result = ModpackAnalysisResult(success=False, error_message="Test error")

        report = orchestrator.generate_report(result)

        assert report["success"] is False
        assert report["error"] == "Test error"

    def test_singleton_instance(self):
        """Test that singleton instance is available."""
        assert modpack_orchestrator is not None
        assert isinstance(modpack_orchestrator, ModpackOrchestrator)


class TestModpackConversionCrew:
    """Tests for ModpackConversionCrew class."""

    def test_init(self):
        """Test crew initialization."""
        crew = ModpackConversionCrew()

        assert crew.orchestrator is not None
        assert crew.tools == []

    def test_process_modpack(self):
        """Test processing modpack through crew."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            crew = ModpackConversionCrew()
            result = crew.process_modpack(pack_path)

            assert result.success is True
            assert result.modpack_info is not None

    def test_generate_report(self):
        """Test generating report through crew."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(SAMPLE_CURSEFORGE_MANIFEST))

            crew = ModpackConversionCrew()
            analysis_result = crew.process_modpack(pack_path)
            report = crew.generate_report(analysis_result)

            assert report["success"] is True


class TestModpackOrchestratorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_missing_curseforge_manifest(self):
        """Test parsing with missing CurseForge manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)

            orchestrator = ModpackOrchestrator()

            with pytest.raises(FileNotFoundError):
                orchestrator.parse_modpack(pack_path, PackFormat.CURSEFORGE)

    def test_parse_missing_modrinth_index(self):
        """Test parsing with missing Modrinth index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)

            orchestrator = ModpackOrchestrator()

            with pytest.raises(FileNotFoundError):
                orchestrator.parse_modpack(pack_path, PackFormat.MODRINTH)

    def test_analyze_empty_modpack(self):
        """Test analyzing empty modpack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            empty_manifest = {
                "manifestType": "minecraftModpack",
                "manifestVersion": 1,
                "name": "Empty Pack",
                "version": "1.0.0",
                "minecraft": {"version": "1.20.1"},
                "files": [],
            }
            manifest_path.write_text(json.dumps(empty_manifest))

            orchestrator = ModpackOrchestrator()
            result = orchestrator.analyze_modpack(pack_path)

            assert result.success is True
            assert result.modpack_info.mod_count == 0

    def test_analyze_modpack_with_conflicts(self):
        """Test analyzing modpack with conflicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"

            # Create manifest with mods that might conflict
            conflict_manifest = SAMPLE_CURSEFORGE_MANIFEST.copy()
            conflict_manifest["files"].append(
                {
                    "projectID": 999999,
                    "fileID": 888888,
                    "name": "ConflictingMod",
                    "version": "1.0.0",
                    "required": True,
                    "dependencies": [],
                }
            )
            manifest_path.write_text(json.dumps(conflict_manifest))

            orchestrator = ModpackOrchestrator()
            result = orchestrator.analyze_modpack(pack_path)

            assert result.success is True
            # Conflict detection should have run
            assert result.conflict_result is not None


class TestModpackOrchestratorIntegration:
    """Integration tests for ModpackOrchestrator."""

    def test_full_workflow_curseforge(self):
        """Test full workflow with CurseForge modpack."""
        # Use a fresh manifest to avoid test pollution
        fresh_manifest = {
            "manifestType": "minecraftModpack",
            "manifestVersion": 1,
            "name": "Integration Test Pack",
            "version": "1.0.0",
            "author": "TestAuthor",
            "description": "Integration test modpack",
            "minecraft": {
                "version": "1.20.1",
                "modLoaders": [{"id": "forge-47.0.0", "primary": True}],
            },
            "files": [
                {
                    "projectID": 111111,
                    "fileID": 222222,
                    "name": "TestMod1",
                    "required": True,
                    "dependencies": [],
                },
                {
                    "projectID": 333333,
                    "fileID": 444444,
                    "name": "TestMod2",
                    "required": True,
                    "dependencies": [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            manifest_path = pack_path / "manifest.json"
            manifest_path.write_text(json.dumps(fresh_manifest))

            orchestrator = ModpackOrchestrator()

            # Step 1: Detect format
            detected = orchestrator.detect_format(pack_path)
            assert detected == PackFormat.CURSEFORGE

            # Step 2: Parse modpack
            parsed = orchestrator.parse_modpack(pack_path)
            assert parsed["mod_count"] == 2

            # Step 3: Analyze modpack
            result = orchestrator.analyze_modpack(pack_path)
            assert result.success is True

            # Step 4: Generate report
            report = orchestrator.generate_report(result)
            assert report["success"] is True

            # Verify all components were used
            assert result.dependency_result is not None
            assert result.conflict_result is not None
            assert len(result.recommended_load_order) > 0

    def test_full_workflow_modrinth(self):
        """Test full workflow with Modrinth modpack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            index_path = pack_path / "modrinth.index.json"
            index_path.write_text(json.dumps(SAMPLE_MODRINTH_INDEX))

            orchestrator = ModpackOrchestrator()

            # Step 1: Detect format
            detected = orchestrator.detect_format(pack_path)
            assert detected == PackFormat.MODRINTH

            # Step 2: Parse modpack
            parsed = orchestrator.parse_modpack(pack_path)
            assert parsed["file_count"] == 1

            # Step 3: Analyze modpack
            result = orchestrator.analyze_modpack(pack_path)
            assert result.success is True

            # Step 4: Generate report
            report = orchestrator.generate_report(result)
            assert report["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
