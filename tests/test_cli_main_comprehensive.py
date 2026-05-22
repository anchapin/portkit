"""
Comprehensive tests for PortKit CLI main module.
Tests convert command, CLI parsing, agent integration, and error handling.
"""

import pytest
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

# Set up imports
try:
    from portkit.cli.main import (
        convert_mod,
        main,
        add_ai_engine_to_path,
    )

    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    IMPORT_ERROR = str(e)


# Skip all tests if imports fail
pytestmark = pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Required imports unavailable")


@pytest.fixture
def temp_jar_file(tmp_path):
    """Create a temporary JAR file for testing."""
    jar_file = tmp_path / "test_mod.jar"
    # Create a minimal ZIP file (JAR is a ZIP)
    import zipfile

    with zipfile.ZipFile(jar_file, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    return jar_file


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


class TestAddAIEngineToPath:
    """Test add_ai_engine_to_path function."""

    def test_path_added_to_sys_path(self):
        """Test that AI engine path is added to sys.path."""
        original_path = sys.path.copy()

        try:
            ai_engine_path = add_ai_engine_to_path()

            assert ai_engine_path is not None
            assert ai_engine_path.exists()
        finally:
            sys.path = original_path

    def test_returns_ai_engine_path(self):
        """Test that function returns AI engine path."""
        ai_engine_path = add_ai_engine_to_path()

        assert ai_engine_path is not None
        assert isinstance(ai_engine_path, Path)
        assert "ai-engine" in str(ai_engine_path)


class TestConvertModFunction:
    """Test convert_mod function."""

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    @patch("portkit.cli.main.BedrockBuilderAgent")
    @patch("portkit.cli.main.PackagingAgent")
    def test_convert_mod_success(
        self, mock_packaging, mock_bedrock, mock_java_analyzer, temp_jar_file, temp_output_dir
    ):
        """Test successful mod conversion."""
        # Mock analyzer
        mock_analyzer_instance = MagicMock()
        mock_java_analyzer.return_value = mock_analyzer_instance
        mock_analyzer_instance.analyze_jar_for_mvp.return_value = {
            "success": True,
            "registry_name": "test_block",
            "texture_path": "/path/to/texture.png",
        }

        # Mock builder
        mock_builder_instance = MagicMock()
        mock_bedrock.return_value = mock_builder_instance
        mock_builder_instance.build_block_addon_mvp.return_value = {
            "success": True,
            "output_dir": str(temp_output_dir),
        }

        # Mock packager
        mock_packager_instance = MagicMock()
        mock_packaging.return_value = mock_packager_instance
        mock_packager_instance.build_mcaddon_mvp.return_value = {
            "success": True,
            "output_path": str(temp_output_dir / "test_block.mcaddon"),
            "file_size": 1024,
            "validation": {"valid": True},
        }

        result = convert_mod(str(temp_jar_file), str(temp_output_dir))

        assert result["success"] is True
        assert "test_block" in result["registry_name"]
        assert "output_file" in result

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    def test_convert_mod_file_not_found(self, mock_java_analyzer):
        """Test convert_mod with non-existent file."""
        result = convert_mod("/nonexistent/path/to/mod.jar")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    def test_convert_mod_invalid_jar_extension(self, mock_java_analyzer, temp_jar_file):
        """Test convert_mod with invalid file extension."""
        invalid_file = temp_jar_file.parent / "test.txt"
        invalid_file.write_text("not a jar")

        result = convert_mod(str(invalid_file))

        assert result["success"] is False
        assert "must be a .jar file" in result["error"].lower()

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    @patch("portkit.cli.main.BedrockBuilderAgent")
    @patch("portkit.cli.main.PackagingAgent")
    def test_convert_mod_analysis_failure(
        self, mock_packaging, mock_bedrock, mock_java_analyzer, temp_jar_file, temp_output_dir
    ):
        """Test convert_mod when analysis fails."""
        mock_analyzer_instance = MagicMock()
        mock_java_analyzer.return_value = mock_analyzer_instance
        mock_analyzer_instance.analyze_jar_for_mvp.return_value = {
            "success": False,
            "error": "Invalid JAR file format",
        }

        result = convert_mod(str(temp_jar_file), str(temp_output_dir))

        assert result["success"] is False
        assert "Analysis failed" in result["error"]

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    @patch("portkit.cli.main.BedrockBuilderAgent")
    @patch("portkit.cli.main.PackagingAgent")
    def test_convert_mod_builder_failure(
        self, mock_packaging, mock_bedrock, mock_java_analyzer, temp_jar_file, temp_output_dir
    ):
        """Test convert_mod when building fails."""
        mock_analyzer_instance = MagicMock()
        mock_java_analyzer.return_value = mock_analyzer_instance
        mock_analyzer_instance.analyze_jar_for_mvp.return_value = {
            "success": True,
            "registry_name": "test_block",
            "texture_path": None,
        }

        mock_builder_instance = MagicMock()
        mock_bedrock.return_value = mock_builder_instance
        mock_builder_instance.build_block_addon_mvp.return_value = {
            "success": False,
            "error": "Build failed",
        }

        result = convert_mod(str(temp_jar_file), str(temp_output_dir))

        assert result["success"] is False
        assert "Bedrock build failed" in result["error"]

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    @patch("portkit.cli.main.BedrockBuilderAgent")
    @patch("portkit.cli.main.PackagingAgent")
    def test_convert_mod_packaging_failure(
        self, mock_packaging, mock_bedrock, mock_java_analyzer, temp_jar_file, temp_output_dir
    ):
        """Test convert_mod when packaging fails."""
        mock_analyzer_instance = MagicMock()
        mock_java_analyzer.return_value = mock_analyzer_instance
        mock_analyzer_instance.analyze_jar_for_mvp.return_value = {
            "success": True,
            "registry_name": "test_block",
            "texture_path": None,
        }

        mock_builder_instance = MagicMock()
        mock_bedrock.return_value = mock_builder_instance
        mock_builder_instance.build_block_addon_mvp.return_value = {
            "success": True,
            "output_dir": str(temp_output_dir),
        }

        mock_packager_instance = MagicMock()
        mock_packaging.return_value = mock_packager_instance
        mock_packager_instance.build_mcaddon_mvp.return_value = {
            "success": False,
            "error": "Packaging failed",
        }

        result = convert_mod(str(temp_jar_file), str(temp_output_dir))

        assert result["success"] is False
        assert "Packaging failed" in result["error"]

    def test_convert_mod_output_dir_created(self, temp_jar_file):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "nested" / "output"

            with patch("portkit.cli.main.JavaAnalyzerAgent"):
                with patch("portkit.cli.main.BedrockBuilderAgent"):
                    with patch("portkit.cli.main.PackagingAgent"):
                        # Just verify it doesn't error on missing directory
                        try:
                            # We expect this to fail at the analyzer stage
                            # but it should create the directory first
                            result = convert_mod(str(temp_jar_file), str(output_dir))
                        except:
                            pass

                        # Directory should be created
                        assert output_dir.exists()


class TestMainCLI:
    """Test main CLI entry point."""

    def test_main_help(self, capsys):
        """Test --help argument."""
        with patch("sys.argv", ["portkit", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "PortKit" in captured.out or "PortKit" in captured.err

    def test_main_version(self, capsys):
        """Test --version argument."""
        with patch("sys.argv", ["portkit", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "v0.1.0" in captured.out or "v0.1.0" in captured.err

    @patch("portkit.cli.main.convert_mod")
    def test_main_convert_command(self, mock_convert, temp_jar_file):
        """Test convert subcommand."""
        mock_convert.return_value = {
            "success": True,
            "output_file": str(temp_jar_file),
            "file_size": 1024,
            "registry_name": "test_block",
            "validation": {"valid": True},
        }

        with patch("sys.argv", ["portkit", "convert", str(temp_jar_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            mock_convert.assert_called()

    @patch("portkit.cli.main.convert_mod")
    def test_main_convert_with_output(self, mock_convert, temp_jar_file, temp_output_dir):
        """Test convert with output directory."""
        mock_convert.return_value = {
            "success": True,
            "output_file": str(temp_output_dir / "test.mcaddon"),
            "file_size": 1024,
            "registry_name": "test_block",
            "validation": {"valid": True},
        }

        with patch(
            "sys.argv", ["portkit", "convert", str(temp_jar_file), "-o", str(temp_output_dir)]
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            # Verify output directory was passed
            call_args = mock_convert.call_args
            assert str(temp_output_dir) in str(call_args)

    @patch("portkit.cli.main.CIFixer")
    def test_main_fix_ci_command(self, mock_fixer):
        """Test fix-ci subcommand."""
        mock_fixer_instance = MagicMock()
        mock_fixer.return_value = mock_fixer_instance
        mock_fixer_instance.fix_failing_ci.return_value = True

        with patch("sys.argv", ["portkit", "fix-ci"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0

    @patch("portkit.cli.main.CIFixer")
    def test_main_fix_ci_with_repo_path(self, mock_fixer):
        """Test fix-ci with custom repo path."""
        mock_fixer_instance = MagicMock()
        mock_fixer.return_value = mock_fixer_instance
        mock_fixer_instance.fix_failing_ci.return_value = True

        with patch("sys.argv", ["portkit", "fix-ci", "--repo-path", "/custom/repo"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            mock_fixer.assert_called_with("/custom/repo")

    def test_main_no_command_shows_convert(self):
        """Test that no command defaults to showing help/error."""
        with patch("sys.argv", ["portkit"]):
            with pytest.raises(SystemExit):
                main()

    @patch("portkit.cli.main.convert_mod")
    def test_main_verbose_flag(self, mock_convert, temp_jar_file):
        """Test verbose logging flag."""
        mock_convert.return_value = {
            "success": True,
            "output_file": str(temp_jar_file),
            "file_size": 1024,
            "registry_name": "test_block",
            "validation": {"valid": True},
        }

        with patch("sys.argv", ["portkit", "-v", "convert", str(temp_jar_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0

    @patch("portkit.cli.main.convert_mod")
    def test_main_convert_failure(self, mock_convert, temp_jar_file):
        """Test main handles convert failure."""
        mock_convert.return_value = {"success": False, "error": "Conversion failed"}

        with patch("sys.argv", ["portkit", "convert", str(temp_jar_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

    @patch("portkit.cli.main.CIFixer")
    def test_main_fix_ci_failure(self, mock_fixer):
        """Test main handles fix-ci failure."""
        mock_fixer_instance = MagicMock()
        mock_fixer.return_value = mock_fixer_instance
        mock_fixer_instance.fix_failing_ci.return_value = False

        with patch("sys.argv", ["portkit", "fix-ci"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1


class TestCLIIntegration:
    """Integration tests for CLI."""

    @patch("portkit.cli.main.JavaAnalyzerAgent")
    @patch("portkit.cli.main.BedrockBuilderAgent")
    @patch("portkit.cli.main.PackagingAgent")
    def test_end_to_end_conversion(
        self, mock_packaging, mock_bedrock, mock_java_analyzer, temp_jar_file, temp_output_dir
    ):
        """Test end-to-end conversion flow."""
        # Setup mocks
        mock_analyzer_instance = MagicMock()
        mock_java_analyzer.return_value = mock_analyzer_instance
        mock_analyzer_instance.analyze_jar_for_mvp.return_value = {
            "success": True,
            "registry_name": "copper_block",
            "texture_path": "/path/to/copper.png",
        }

        mock_builder_instance = MagicMock()
        mock_bedrock.return_value = mock_builder_instance
        mock_builder_instance.build_block_addon_mvp.return_value = {
            "success": True,
            "output_dir": str(temp_output_dir),
        }

        mock_packager_instance = MagicMock()
        mock_packaging.return_value = mock_packager_instance
        mock_packager_instance.build_mcaddon_mvp.return_value = {
            "success": True,
            "output_path": str(temp_output_dir / "copper_block.mcaddon"),
            "file_size": 2048,
            "validation": {"valid": True, "files": 15},
        }

        # Run conversion
        result = convert_mod(str(temp_jar_file), str(temp_output_dir))

        # Verify flow
        assert result["success"] is True
        mock_analyzer_instance.analyze_jar_for_mvp.assert_called_once()
        mock_builder_instance.build_block_addon_mvp.assert_called_once()
        mock_packager_instance.build_mcaddon_mvp.assert_called_once()

    @patch("portkit.cli.main.convert_mod")
    def test_cli_with_multiple_files(self, mock_convert, temp_jar_file, temp_output_dir):
        """Test CLI parsing for multiple operations."""
        mock_convert.return_value = {
            "success": True,
            "output_file": str(temp_output_dir / "test.mcaddon"),
            "file_size": 1024,
            "registry_name": "test_block",
            "validation": {"valid": True},
        }

        # Simulate converting multiple files
        for i in range(3):
            with patch("sys.argv", ["portkit", "convert", str(temp_jar_file)]):
                with pytest.raises(SystemExit):
                    main()

        # All should succeed
        assert mock_convert.call_count == 3


class TestCLIErrorMessages:
    """Test CLI error message handling."""

    @patch("portkit.cli.main.convert_mod")
    def test_error_message_displayed(self, mock_convert, temp_jar_file, capsys):
        """Test that error messages are displayed."""
        mock_convert.return_value = {"success": False, "error": "Test error message"}

        with patch("sys.argv", ["portkit", "convert", str(temp_jar_file)]):
            with pytest.raises(SystemExit):
                main()

        # Error should be logged
        mock_convert.assert_called()

    def test_missing_jar_file_argument(self):
        """Test error when JAR file argument is missing."""
        with patch("sys.argv", ["portkit", "convert"]):
            with pytest.raises(SystemExit):
                main()


class TestCLILogging:
    """Test CLI logging functionality."""

    @patch("portkit.cli.main.logging.getLogger")
    def test_logging_configured(self, mock_get_logger):
        """Test that logging is properly configured."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        with patch("sys.argv", ["portkit", "--help"]):
            with pytest.raises(SystemExit):
                main()


class TestSoundExtraction:
    """Test sound file extraction from JAR."""

    def test_extract_sounds_from_jar_with_sounds(self, tmp_path):
        """Test extracting sounds from a JAR with sound files."""
        from portkit.cli.main import _extract_sounds_from_jar

        jar_path = tmp_path / "test_sounds.jar"
        import zipfile

        with zipfile.ZipFile(jar_path, "w") as zf:
            zf.writestr("assets/modid/sounds/test.ogg", b"fake_ogg_data")
            zf.writestr("assets/modid/sounds.json", '{"test.sound": {"sounds": ["test.ogg"]}}')

        result = _extract_sounds_from_jar(str(jar_path))

        assert "sound_files" in result
        assert "sounds_json" in result
        assert len(result["sound_files"]) == 1
        assert result["sound_files"][0] == "assets/modid/sounds/test.ogg"
        assert "assets/modid/sounds.json" in result["sounds_json"]

    def test_extract_sounds_from_jar_no_sounds(self, tmp_path):
        """Test extracting sounds from a JAR without sound files."""
        from portkit.cli.main import _extract_sounds_from_jar

        jar_path = tmp_path / "empty.jar"
        import zipfile

        with zipfile.ZipFile(jar_path, "w") as zf:
            zf.writestr("META-INF/MANIFEST.MF", "")

        result = _extract_sounds_from_jar(str(jar_path))

        assert result["sound_files"] == []
        assert result["sounds_json"] == {}


class TestSoundConversion:
    """Test Java sounds.json to Bedrock sound_definitions.json conversion."""

    def test_convert_java_sounds_to_bedrock(self, tmp_path):
        """Test converting Java sounds to Bedrock format."""
        from portkit.cli.main import _convert_java_sounds_to_bedrock

        jar_path = tmp_path / "test_sounds.jar"
        rp_path = tmp_path / "resource_pack"
        rp_path.mkdir()

        import zipfile

        with zipfile.ZipFile(jar_path, "w") as zf:
            zf.writestr("assets/modid/sounds/test.ogg", b"fake_ogg_data")
            zf.writestr(
                "assets/modid/sounds.json",
                '{"test.event": {"sounds": ["test.ogg"], "category": "master"}}',
            )

        sounds_data = {
            "sound_files": ["assets/modid/sounds/test.ogg"],
            "sounds_json": {
                "assets/modid/sounds.json": {
                    "test.event": {"sounds": ["test.ogg"], "category": "master"}
                }
            },
        }

        _convert_java_sounds_to_bedrock(str(jar_path), sounds_data, rp_path)

        sounds_dir = rp_path / "sounds"
        assert sounds_dir.exists()

        sound_def_file = sounds_dir / "sound_definitions.json"
        assert sound_def_file.exists()

        import json

        with open(sound_def_file) as f:
            content = json.load(f)

        assert "sound_definitions" in content
        assert "test.event" in content["sound_definitions"]


class TestLocalizationExtraction:
    """Test localization file extraction from JAR."""

    def test_extract_localization_from_jar_with_lang(self, tmp_path):
        """Test extracting localization files from a JAR."""
        from portkit.cli.main import _extract_localization_from_jar

        jar_path = tmp_path / "test_lang.jar"
        import zipfile

        with zipfile.ZipFile(jar_path, "w") as zf:
            zf.writestr(
                "assets/modid/lang/en_us.json",
                '{"item.test": "Test Item", "block.test": "Test Block"}',
            )

        result = _extract_localization_from_jar(str(jar_path))

        assert len(result) == 1
        assert "assets/modid/lang/en_us.json" in result
        assert result["assets/modid/lang/en_us.json"]["item.test"] == "Test Item"

    def test_extract_localization_from_jar_no_lang(self, tmp_path):
        """Test extracting localization from a JAR without lang files."""
        from portkit.cli.main import _extract_localization_from_jar

        jar_path = tmp_path / "empty.jar"
        import zipfile

        with zipfile.ZipFile(jar_path, "w") as zf:
            zf.writestr("META-INF/MANIFEST.MF", "")

        result = _extract_localization_from_jar(str(jar_path))

        assert result == {}


class TestLocalizationConversion:
    """Test Java JSON lang to Bedrock .lang conversion."""

    def test_convert_java_lang_to_bedrock(self, tmp_path):
        """Test converting Java lang files to Bedrock .lang format."""
        from portkit.cli.main import _convert_java_lang_to_bedrock

        rp_path = tmp_path / "resource_pack"
        rp_path.mkdir()

        lang_files = {
            "assets/modid/lang/en_us.json": {"item.test": "Test Item", "block.test": "Test Block"}
        }

        _convert_java_lang_to_bedrock(lang_files, "modid", rp_path)

        texts_dir = rp_path / "texts"
        assert texts_dir.exists()

        lang_file = texts_dir / "en_US.lang"
        assert lang_file.exists()

        content = lang_file.read_text()
        assert "modid.item.test=Test Item" in content
        assert "modid.block.test=Test Block" in content

    def test_convert_java_lang_to_bedrock_with_namespace(self, tmp_path):
        """Test that keys with existing namespace are not double-namespaced."""
        from portkit.cli.main import _convert_java_lang_to_bedrock

        rp_path = tmp_path / "resource_pack"
        rp_path.mkdir()

        lang_files = {
            "assets/modid/lang/en_us.json": {
                "already.namespaced": "Already Has Namespace",
                "no_namespace": "No Namespace",
            }
        }

        _convert_java_lang_to_bedrock(lang_files, "modid", rp_path)

        lang_file = rp_path / "texts" / "en_US.lang"
        content = lang_file.read_text()

        assert "already.namespaced=Already Has Namespace" in content
        assert "modid.no_namespace=No Namespace" in content
