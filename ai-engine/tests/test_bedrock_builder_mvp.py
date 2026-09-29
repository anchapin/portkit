"""
Unit tests for BedrockBuilderAgent MVP functionality.
Implements tests for Issue #168: Emit Bedrock JSON & copy texture in BedrockBuilderAgent
"""

import pytest
import tempfile
import zipfile
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

from agents.bedrock_builder import BedrockBuilderAgent


class TestBedrockBuilderMVP:
    """Test BedrockBuilderAgent MVP-specific functionality."""

    @pytest.fixture
    def builder(self):
        """Create BedrockBuilderAgent instance for testing."""
        return BedrockBuilderAgent()

    @pytest.fixture
    def test_jar_with_texture(self):
        """Create a test JAR with a real texture for testing."""
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
            with zipfile.ZipFile(jar_file.name, "w") as zf:
                # Create a real 16x16 PNG texture using Pillow
                from PIL import Image
                import io

                # Create a simple 16x16 RGBA image
                img = Image.new("RGBA", (16, 16), (200, 100, 50, 255))  # Orange-ish color
                png_buffer = io.BytesIO()
                img.save(png_buffer, format="PNG")
                png_data = png_buffer.getvalue()

                # Add the real PNG texture to JAR
                zf.writestr("assets/simple_copper/textures/block/polished_copper.png", png_data)

            yield jar_file.name

        os.unlink(jar_file.name)

    @pytest.fixture
    def output_dir(self):
        """Create temporary output directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_build_block_addon_mvp_success(self, builder, test_jar_with_texture, output_dir):
        """Test successful MVP block addon creation."""
        registry_name = "simple_copper:polished_copper"
        texture_path = "assets/simple_copper/textures/block/polished_copper.png"

        result = builder.build_block_addon_mvp(
            registry_name=registry_name,
            texture_path=texture_path,
            jar_path=test_jar_with_texture,
            output_dir=output_dir,
        )

        assert result["success"] is True
        assert result["addon_path"] is not None
        assert Path(result["addon_path"]).exists()
        assert len(result["bp_files"]) > 0
        assert len(result["rp_files"]) > 0
        assert len(result["errors"]) == 0

        # Verify bulk texture extraction (Issue #999 fix)
        # The test JAR has 1 texture, bulk extraction should find and copy it
        assert "bulk_textures_extracted" in result
        assert result["bulk_textures_extracted"] >= 1, (
            "Bulk texture extraction should find textures"
        )

    def test_bulk_texture_extraction_issue_999(self, builder, output_dir):
        """Test bulk texture extraction fix for Issue #999.

        Before the fix, only ~1% of textures were extracted because extraction
        was limited to explicitly referenced textures. The bulk extraction should
        find and copy ALL textures from assets/*/textures/.
        """
        # Create JAR with multiple textures of different types
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
            with zipfile.ZipFile(jar_file.name, "w") as zf:
                from PIL import Image
                import io

                # Create textures of different types
                textures = [
                    ("assets/test_mod/textures/block/stone.png", (128, 128, 128, 255)),
                    ("assets/test_mod/textures/block/dirt.png", (139, 69, 19, 255)),
                    ("assets/test_mod/textures/item/iron_sword.png", (200, 200, 200, 255)),
                    ("assets/test_mod/textures/entity/chicken.png", (255, 255, 0, 255)),
                    ("assets/test_mod/textures/particle/flame.png", (255, 100, 0, 255)),
                ]

                for texture_path, color in textures:
                    img = Image.new("RGBA", (16, 16), color)
                    png_buffer = io.BytesIO()
                    img.save(png_buffer, format="PNG")
                    zf.writestr(texture_path, png_buffer.getvalue())

                # Also add an animated texture with .mcmeta
                animated_texture = Image.new("RGBA", (16, 16), (0, 255, 0, 255))
                png_buffer = io.BytesIO()
                animated_texture.save(png_buffer, format="PNG")
                zf.writestr(
                    "assets/test_mod/textures/block/animated_block.png", png_buffer.getvalue()
                )
                zf.writestr(
                    "assets/test_mod/textures/block/animated_block.png.mcmeta",
                    b'{"animation": {"frametime": 2}}',
                )

            try:
                result = builder.build_block_addon_mvp(
                    registry_name="test_mod:bulk_test",
                    texture_path="assets/test_mod/textures/block/stone.png",
                    jar_path=jar_file.name,
                    output_dir=output_dir,
                )

                assert result["success"] is True

                # Bulk extraction should have found all 5 textures (6 entries total if mcmeta counted)
                # Note: mcmeta files are also tracked, so we may see 6 copied entries
                assert result["bulk_textures_extracted"] >= 5, (
                    f"Expected at least 5 textures, got {result['bulk_textures_extracted']}"
                )
                assert result["bulk_textures_copied"] >= 5

                # Verify the resource pack contains all texture subdirectories
                rp_path = Path(output_dir) / "resource_pack"
                assert (rp_path / "textures" / "blocks").exists(), "blocks texture dir should exist"
                assert (rp_path / "textures" / "items").exists(), "items texture dir should exist"
                assert (rp_path / "textures" / "entity").exists(), "entity texture dir should exist"
                assert (rp_path / "textures" / "particle").exists(), (
                    "particle texture dir should exist"
                )

                # Verify animated texture mcmeta was copied
                assert (rp_path / "textures" / "blocks" / "animated_block.png.mcmeta").exists(), (
                    "Animated texture mcmeta should be copied"
                )

            finally:
                os.unlink(jar_file.name)

    def test_build_block_addon_mvp_registry_parsing(
        self, builder, test_jar_with_texture, output_dir
    ):
        """Test registry name parsing."""
        # Test with namespace
        result = builder.build_block_addon_mvp(
            registry_name="test_mod:custom_block",
            texture_path="assets/simple_copper/textures/block/polished_copper.png",
            jar_path=test_jar_with_texture,
            output_dir=output_dir,
        )

        assert result["success"] is True
        assert "test_mod_custom_block.mcaddon" in result["addon_path"]

        # Test without namespace (should default to modporter)
        result2 = builder.build_block_addon_mvp(
            registry_name="just_block_name",
            texture_path="assets/simple_copper/textures/block/polished_copper.png",
            jar_path=test_jar_with_texture,
            output_dir=output_dir,
        )

        assert result2["success"] is True
        assert "modporter_just_block_name.mcaddon" in result2["addon_path"]

    def test_build_bp_mvp(self, builder, output_dir):
        """Test behavior pack creation."""
        bp_path = Path(output_dir) / "BP"
        bp_path.mkdir()

        files_created = builder._build_bp_mvp(
            bp_path=bp_path, namespace="test_mod", block_name="test_block", bp_uuid="test-uuid-bp"
        )

        assert len(files_created) >= 2  # manifest + block file

        # Check manifest exists
        manifest_file = bp_path / "manifest.json"
        assert manifest_file.exists()

        # Check manifest content
        manifest_data = json.loads(manifest_file.read_text())
        assert manifest_data["header"]["name"] == "ModPorter Test Block"
        assert manifest_data["header"]["uuid"] == "test-uuid-bp"

        # Check block file exists
        block_file = bp_path / "blocks" / "test_block.json"
        assert block_file.exists()

        # Check block content
        block_data = json.loads(block_file.read_text())
        assert block_data["minecraft:block"]["description"]["identifier"] == "test_mod:test_block"

    def test_build_rp_mvp(self, builder, test_jar_with_texture, output_dir):
        """Test resource pack creation."""
        rp_path = Path(output_dir) / "RP"
        rp_path.mkdir()

        files_created = builder._build_rp_mvp(
            rp_path=rp_path,
            namespace="simple_copper",
            block_name="polished_copper",
            rp_uuid="test-uuid-rp",
            texture_path="assets/simple_copper/textures/block/polished_copper.png",
            jar_path=test_jar_with_texture,
        )

        assert len(files_created) >= 3  # manifest + block + texture

        # Check manifest exists
        manifest_file = rp_path / "manifest.json"
        assert manifest_file.exists()

        # Check manifest content
        manifest_data = json.loads(manifest_file.read_text())
        assert "Resources" in manifest_data["header"]["name"]
        assert manifest_data["header"]["uuid"] == "test-uuid-rp"

        # Check block file exists
        block_file = rp_path / "blocks" / "polished_copper.json"
        assert block_file.exists()

        # Check texture file exists
        texture_file = rp_path / "textures" / "blocks" / "polished_copper.png"
        assert texture_file.exists()

    def test_copy_texture_mvp(self, builder, test_jar_with_texture, output_dir):
        """Test texture copying and processing."""
        rp_path = Path(output_dir) / "RP"
        rp_path.mkdir()

        # Mock Pillow Image processing since we have fake PNG data
        with patch("agents.bedrock_builder.agent.Image") as mock_image:
            mock_img = Mock()
            mock_img.size = (32, 32)
            mock_img.convert.return_value = mock_img
            mock_img.resize.return_value = mock_img
            mock_image.open.return_value.__enter__.return_value = mock_img

            files_created = builder._copy_texture_mvp(
                rp_path=rp_path,
                block_name="test_block",
                texture_path="assets/simple_copper/textures/block/polished_copper.png",
                jar_path=test_jar_with_texture,
            )

            # Should have created texture file
            assert len(files_created) == 1

            # Check texture directory was created
            textures_dir = rp_path / "textures" / "blocks"
            assert textures_dir.exists()

            # Verify Image processing was called
            mock_img.convert.assert_called_with("RGBA")
            mock_img.resize.assert_called_with((16, 16), mock_image.Resampling.NEAREST)

    def test_copy_texture_missing_texture(self, builder, output_dir):
        """Test handling of missing texture in JAR."""
        # Create JAR without the expected texture
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
            with zipfile.ZipFile(jar_file.name, "w") as zf:
                zf.writestr("some_other_file.txt", b"not a texture")

        try:
            rp_path = Path(output_dir) / "RP"
            rp_path.mkdir()

            # Should not raise an exception, but should log warning
            files_created = builder._copy_texture_mvp(
                rp_path=rp_path,
                block_name="test_block",
                texture_path="assets/missing/texture.png",
                jar_path=jar_file.name,
            )

            # Should create no files when texture is missing
            assert len(files_created) == 0

        finally:
            os.unlink(jar_file.name)

    def test_package_addon_mvp(self, builder, output_dir):
        """Test addon packaging into .mcaddon file."""
        # Create temporary pack structure
        temp_path = Path(output_dir) / "temp"
        temp_path.mkdir()

        # Create some test files
        bp_path = temp_path / "BP"
        rp_path = temp_path / "RP"
        bp_path.mkdir()
        rp_path.mkdir()

        (bp_path / "manifest.json").write_text('{"test": "bp"}')
        (rp_path / "manifest.json").write_text('{"test": "rp"}')

        addon_path = Path(output_dir) / "test_addon.mcaddon"

        # Package the addon
        builder._package_addon_mvp(temp_path, addon_path)

        # Verify addon file was created
        assert addon_path.exists()
        assert addon_path.suffix == ".mcaddon"

        # Verify contents
        with zipfile.ZipFile(addon_path, "r") as addon_zip:
            files = addon_zip.namelist()
            assert "BP/manifest.json" in files
            assert "RP/manifest.json" in files

    def test_invalid_jar_file(self, builder, output_dir):
        """Test handling of invalid JAR files."""
        # Create invalid JAR file
        jar_file_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
                jar_file_path = jar_file.name
                jar_file.write(b"not a valid jar file")
                jar_file.flush()

            result = builder.build_block_addon_mvp(
                registry_name="test:block",
                texture_path="assets/test/texture.png",
                jar_path=jar_file_path,
                output_dir=output_dir,
            )

            assert result["success"] is False
            assert len(result["errors"]) > 0
            assert "Build failed" in result["errors"][0]

        finally:
            if jar_file_path and os.path.exists(jar_file_path):
                os.unlink(jar_file_path)

    def test_nonexistent_jar_file(self, builder, output_dir):
        """Test handling of nonexistent JAR files."""
        result = builder.build_block_addon_mvp(
            registry_name="test:block",
            texture_path="assets/test/texture.png",
            jar_path="/nonexistent/path/to/file.jar",
            output_dir=output_dir,
        )

        assert result["success"] is False
        assert len(result["errors"]) > 0

    @patch("agents.bedrock_builder.agent.logger")
    def test_logging_behavior(self, mock_logger, builder, test_jar_with_texture, output_dir):
        """Test that appropriate logging occurs during build."""
        builder.build_block_addon_mvp(
            registry_name="simple_copper:polished_copper",
            texture_path="assets/simple_copper/textures/block/polished_copper.png",
            jar_path=test_jar_with_texture,
            output_dir=output_dir,
        )

        # Verify info logs were called
        mock_logger.info.assert_called()

        # Check that specific log messages were made
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("MVP: Building block add-on" in msg for msg in info_calls)
        assert any("MVP: Successfully created" in msg for msg in info_calls)

    def test_non_standard_layout_textures_at_root(self, builder, output_dir):
        """Test extraction from non-standard JAR layout with textures at root (Issue #1105).

        Some mods have textures at 'textures/block/name.png' instead of
        'assets/modid/textures/block/name.png'. This test verifies that the
        fallback mechanism properly detects and extracts these textures.
        """
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
            with zipfile.ZipFile(jar_file.name, "w") as zf:
                from PIL import Image
                import io

                textures = [
                    ("textures/block/stone.png", (128, 128, 128, 255)),
                    ("textures/block/dirt.png", (139, 69, 19, 255)),
                    ("textures/item/iron_sword.png", (200, 200, 200, 255)),
                ]

                for texture_path, color in textures:
                    img = Image.new("RGBA", (16, 16), color)
                    png_buffer = io.BytesIO()
                    img.save(png_buffer, format="PNG")
                    zf.writestr(texture_path, png_buffer.getvalue())

            try:
                result = builder.build_block_addon_mvp(
                    registry_name="test_mod:nonstandard_block",
                    texture_path="textures/block/stone.png",
                    jar_path=jar_file.name,
                    output_dir=output_dir,
                )

                assert result["success"] is True
                assert "bulk_texture_warnings" in result or len(result.get("errors", [])) == 0
                assert result["bulk_textures_extracted"] >= 3, (
                    f"Expected at least 3 textures from non-standard layout, got {result['bulk_textures_extracted']}"
                )

                rp_path = Path(output_dir) / "resource_pack"
                assert (rp_path / "textures" / "blocks").exists(), (
                    "blocks texture dir should exist for non-standard layout"
                )

            finally:
                os.unlink(jar_file.name)

    def test_non_standard_layout_assets_textures_without_namespace(self, builder, output_dir):
        """Test extraction from non-standard JAR layout with assets/textures/ (Issue #1105).

        Some mods have textures at 'assets/textures/block/name.png' instead of
        'assets/modid/textures/block/name.png'.
        """
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
            with zipfile.ZipFile(jar_file.name, "w") as zf:
                from PIL import Image
                import io

                textures = [
                    ("assets/textures/block/stone.png", (128, 128, 128, 255)),
                    ("assets/textures/block/dirt.png", (139, 69, 19, 255)),
                ]

                for texture_path, color in textures:
                    img = Image.new("RGBA", (16, 16), color)
                    png_buffer = io.BytesIO()
                    img.save(png_buffer, format="PNG")
                    zf.writestr(texture_path, png_buffer.getvalue())

            try:
                result = builder.build_block_addon_mvp(
                    registry_name="test_mod:alt_layout_block",
                    texture_path="assets/textures/block/stone.png",
                    jar_path=jar_file.name,
                    output_dir=output_dir,
                )

                assert result["success"] is True
                assert result["bulk_textures_extracted"] >= 2, (
                    f"Expected at least 2 textures from assets/textures layout, got {result['bulk_textures_extracted']}"
                )

            finally:
                os.unlink(jar_file.name)

    def test_empty_jar_no_textures(self, builder, output_dir):
        """Test handling of JAR with no textures (Issue #1105).

        When a JAR contains no textures, appropriate warnings should be surfaced.
        """
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as jar_file:
            with zipfile.ZipFile(jar_file.name, "w") as zf:
                zf.writestr("README.txt", b"This mod has no textures")
                zf.writestr(
                    "data/modid/recipes/example.json", b'{"type":"minecraft:crafting_shaped"}'
                )

            try:
                result = builder.build_block_addon_mvp(
                    registry_name="test_mod:empty_block",
                    texture_path="assets/test/textures/block/stone.png",
                    jar_path=jar_file.name,
                    output_dir=output_dir,
                )

                assert result["bulk_textures_extracted"] == 0, (
                    "Should report 0 textures extracted for empty JAR"
                )
                assert result.get("bulk_texture_warnings") or len(result.get("errors", [])) > 0, (
                    "Should have warnings or errors for empty texture extraction"
                )

            finally:
                os.unlink(jar_file.name)

    def test_map_java_texture_to_bedrock_nonstandard_path(self, builder):
        """Test _map_java_texture_to_bedrock handles non-standard paths (Issue #1105)."""
        standard_path = "assets/modid/textures/block/stone.png"
        root_path = "textures/block/stone.png"
        assets_textures_path = "assets/textures/block/stone.png"

        standard_result = builder._map_java_texture_to_bedrock(standard_path)
        assert standard_result == "textures/blocks/stone.png"

        root_result = builder._map_java_texture_to_bedrock(root_path)
        assert root_result == "textures/blocks/stone.png"

        assets_textures_result = builder._map_java_texture_to_bedrock(assets_textures_path)
        assert assets_textures_result == "textures/blocks/stone.png"


if __name__ == "__main__":
    pytest.main([__file__])
