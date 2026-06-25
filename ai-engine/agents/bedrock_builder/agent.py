"""
Bedrock Builder Agent — generates Bedrock add-on files from Java mod analysis.

This module holds the :class:`BedrockBuilderAgent` implementation. It was
extracted from the former single-file ``agents/bedrock_builder.py`` module as
part of the ``bedrock_builder/`` subpackage split (Issue #1742).

The public entry point is unchanged::

    from agents.bedrock_builder import BedrockBuilderAgent

The package ``__init__.py`` re-exports this class together with the typed
LangChain tool wrappers that live in :mod:`agents.bedrock_builder.tools`.

Enhanced for MVP functionality as specified in Issue #168.
"""

import json
import logging
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader
from PIL import Image

from models.smart_assumptions import SmartAssumptionEngine
from templates.template_engine import TemplateEngine
from utils.atlas_descriptor_parser import (
    extract_sprites_from_atlas,
    find_atlas_descriptors_in_jar,
    find_atlas_textures_in_jar,
    parse_atlas_descriptor,
)

logger = logging.getLogger(__name__)


class BedrockBuilderAgent:
    """
    Bedrock Builder Agent responsible for generating Bedrock add-on files
    from Java mod analysis results as specified in PRD Feature 2.
    """

    _instance = None

    def __init__(self):
        self.smart_assumption_engine = SmartAssumptionEngine()

        # Initialize enhanced template engine
        templates_dir = Path(__file__).parent.parent.parent / "templates" / "bedrock"
        self.template_engine = TemplateEngine(templates_dir)

        # Keep legacy Jinja2 environment for manifest templates
        self.jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))

        # Bedrock file structure templates
        self.bp_structure = {
            "manifest.json": self._create_bp_manifest,
            "blocks/": self._create_bp_blocks,
        }

        self.rp_structure = {
            "manifest.json": self._create_rp_manifest,
            "blocks/": self._create_rp_blocks,
            "textures/blocks/": self._copy_textures,
        }

    @classmethod
    def get_instance(cls):
        """Get singleton instance of BedrockBuilderAgent"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self) -> List:
        """Get tools available to this agent"""
        return [
            BedrockBuilderAgent.build_bedrock_structure_tool,
            BedrockBuilderAgent.generate_block_definitions_tool,
            BedrockBuilderAgent.convert_assets_tool,
            BedrockBuilderAgent.package_addon_tool,
        ]

    def build_block_addon_mvp(
        self, registry_name: str, texture_path: str, jar_path: str, output_dir: str
    ) -> Dict[str, Any]:
        """
        MVP-focused method to build Bedrock add-on from JavaAnalyzerAgent output.
        Implements requirements for Issue #168.

        Args:
            registry_name: Block registry name (e.g., "simple_copper:polished_copper")
            texture_path: Path to texture in JAR (e.g., "assets/mod/textures/block/texture.png")
            jar_path: Path to source JAR file
            output_dir: Output directory for .mcaddon file

        Returns:
            Dict with success status, file paths, and any errors
        """
        logger.info(f"MVP: Building block add-on for {registry_name}")

        result = {
            "success": False,
            "addon_path": None,
            "bp_files": [],
            "rp_files": [],
            "errors": [],
        }

        try:
            # Parse registry name
            if ":" in registry_name:
                namespace, block_name = registry_name.split(":", 1)
            else:
                namespace = "modporter"
                block_name = registry_name

            # Use provided output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Create behavior_pack and resource_pack directories
            bp_path = output_path / "behavior_pack"
            rp_path = output_path / "resource_pack"
            bp_path.mkdir(parents=True, exist_ok=True)
            rp_path.mkdir(parents=True, exist_ok=True)

            # Generate UUIDs for manifests (deterministic for testing)
            import os

            if os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"):
                # Use deterministic UUIDs during testing for reproducible results
                bp_uuid = "12345678-1234-1234-1234-123456789abc"
                rp_uuid = "87654321-4321-4321-4321-abcdef123456"
            else:
                bp_uuid = str(uuid.uuid4())
                rp_uuid = str(uuid.uuid4())

            # Build behavior pack
            bp_files = self._build_bp_mvp(bp_path, namespace, block_name, bp_uuid)
            result["bp_files"] = bp_files

            # Build resource pack with texture
            rp_files = self._build_rp_mvp(
                rp_path, namespace, block_name, rp_uuid, texture_path, jar_path
            )
            result["rp_files"] = rp_files

            # Bulk texture extraction: extract ALL textures from JAR (Issue #999 fix)
            # This raises texture transfer rate from ~1% to ~25-35%
            bulk_texture_results = self._extract_all_textures_from_jar(jar_path, rp_path, namespace)
            result["bulk_textures_extracted"] = bulk_texture_results.get("extracted_count", 0)
            result["bulk_textures_copied"] = len(bulk_texture_results.get("copied_files", []))
            result["bulk_texture_errors"] = bulk_texture_results.get("errors", [])
            result["bulk_texture_warnings"] = bulk_texture_results.get("warnings", [])

            # Atlas texture extraction: extract sprites from texture atlases (Issue #1104 fix)
            # This handles JEI, JourneyMap, and other mods that use sprite sheet atlases
            atlas_texture_results = self._extract_atlas_textures_from_jar(
                jar_path, rp_path, namespace
            )
            result["atlas_textures_extracted"] = atlas_texture_results.get("extracted_count", 0)
            result["atlases_detected"] = atlas_texture_results.get("atlases_detected", 0)
            result["atlases_processed"] = atlas_texture_results.get("atlases_processed", 0)
            result["atlas_texture_warnings"] = atlas_texture_results.get("warnings", [])

            # Package into .mcaddon file - use namespace:block_name format
            full_registry_name = f"{namespace}:{block_name}"
            safe_registry_name = full_registry_name.replace(":", "_")  # Replace namespace separator
            addon_filename = f"{safe_registry_name}.mcaddon"
            addon_path = Path(output_dir) / addon_filename

            self._package_addon_mvp(output_path, addon_path)

            result["success"] = True
            result["addon_path"] = str(addon_path)
            result["output_dir"] = str(output_path)
            result["registry_name"] = registry_name
            result["behavior_pack_dir"] = str(bp_path)
            result["resource_pack_dir"] = str(rp_path)

            logger.info(f"MVP: Successfully created .mcaddon file: {addon_path}")

        except Exception as e:
            logger.error(f"MVP build failed: {e}")
            result["errors"].append(f"Build failed: {str(e)}")

        return result

    def build_entity_addon_mvp(
        self, entities: list, jar_path: str, output_dir: str
    ) -> Dict[str, Any]:
        """
        MVP method to build Bedrock add-on structure for entity-only mods.

        Creates minimal behavior and resource pack manifests when there are
        no blocks to convert but entities are present.

        Args:
            entities: List of entity definitions from AST analysis
            jar_path: Path to source JAR file
            output_dir: Output directory for pack files

        Returns:
            Dict with success status and file paths
        """
        logger.info(f"MVP: Building entity add-on structure for {len(entities)} entities")

        result = {
            "success": False,
            "bp_files": [],
            "rp_files": [],
            "errors": [],
        }

        try:
            output_path = Path(output_dir)
            bp_path = output_path / "behavior_pack"
            rp_path = output_path / "resource_pack"
            bp_path.mkdir(parents=True, exist_ok=True)
            rp_path.mkdir(parents=True, exist_ok=True)

            # Extract mod name from JAR filename
            jar_name = Path(jar_path).stem
            namespace = jar_name.lower().replace("-", "_").replace(" ", "_")

            # Generate UUIDs for manifests
            import os

            if os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"):
                bp_uuid = "12345678-1234-1234-1234-123456789abc"
                rp_uuid = "87654321-4321-4321-4321-abcdef123456"
            else:
                bp_uuid = str(uuid.uuid4())
                rp_uuid = str(uuid.uuid4())

            # Create behavior pack manifest
            bp_manifest = {
                "format_version": 2,
                "header": {
                    "name": f"{namespace} Behavior Pack",
                    "description": f"Converted entity mod: {namespace}",
                    "uuid": bp_uuid,
                    "version": [1, 0, 0],
                    "min_engine_version": [1, 16, 0],
                },
                "modules": [
                    {
                        "type": "data",
                        "uuid": str(uuid.uuid4())
                        if not (os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"))
                        else "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        "version": [1, 0, 0],
                    }
                ],
            }
            bp_manifest_path = bp_path / "manifest.json"
            with open(bp_manifest_path, "w", encoding="utf-8") as f:
                json.dump(bp_manifest, f, indent=2)
            result["bp_files"].append(str(bp_manifest_path))

            # Create resource pack manifest
            rp_manifest = {
                "format_version": 2,
                "header": {
                    "name": f"{namespace} Resource Pack",
                    "description": f"Converted entity mod resources: {namespace}",
                    "uuid": rp_uuid,
                    "version": [1, 0, 0],
                    "min_engine_version": [1, 16, 0],
                },
                "modules": [
                    {
                        "type": "resources",
                        "uuid": str(uuid.uuid4())
                        if not (os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"))
                        else "ffffffff-gggg-hhhh-iiii-jjjjjjjjjjjj",
                        "version": [1, 0, 0],
                    }
                ],
            }
            rp_manifest_path = rp_path / "manifest.json"
            with open(rp_manifest_path, "w", encoding="utf-8") as f:
                json.dump(rp_manifest, f, indent=2)
            result["rp_files"].append(str(rp_manifest_path))

            result["success"] = True
            result["output_dir"] = str(output_path)
            logger.info(f"MVP: Created entity add-on structure in {output_path}")

        except Exception as e:
            logger.error(f"MVP entity build failed: {e}")
            result["errors"].append(f"Entity build failed: {str(e)}")

        return result

    def _build_bp_mvp(
        self, bp_path: Path, namespace: str, block_name: str, bp_uuid: str
    ) -> List[str]:
        """Build behavior pack for MVP."""
        files_created = []

        # Create manifest.json
        manifest_data = {
            "pack_name": f"ModPorter {block_name.replace('_', ' ').title()}",
            "pack_description": f"Behavior pack for {block_name} block",
            "pack_uuid": bp_uuid,
            "module_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            if (os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"))
            else str(uuid.uuid4()),
            "module_type": "data",
        }

        manifest_template = self.jinja_env.get_template("manifest.json")
        manifest_content = manifest_template.render(**manifest_data)

        manifest_file = bp_path / "manifest.json"
        manifest_file.write_text(manifest_content)
        files_created.append(str(manifest_file))

        # Create blocks directory and block JSON
        blocks_dir = bp_path / "blocks"
        blocks_dir.mkdir(exist_ok=True)

        block_data = {"namespace": namespace, "block_name": block_name, "texture_name": block_name}

        # Use enhanced template engine with smart selection
        # For MVP, we'll use basic_block, but the engine can select more specific templates
        block_content = self.template_engine.render_template(
            feature_type="block",
            properties={},  # In future, this will come from Java analysis
            context=block_data,
        )

        block_file = blocks_dir / f"{block_name}.json"
        block_file.write_text(block_content)
        files_created.append(str(block_file))

        return files_created

    def _build_rp_mvp(
        self,
        rp_path: Path,
        namespace: str,
        block_name: str,
        rp_uuid: str,
        texture_path: str,
        jar_path: str,
    ) -> List[str]:
        """Build resource pack for MVP."""
        files_created = []

        # Create manifest.json
        manifest_data = {
            "pack_name": f"ModPorter {block_name.replace('_', ' ').title()} Resources",
            "pack_description": f"Resource pack for {block_name} block",
            "pack_uuid": rp_uuid,
            "module_uuid": "ffffffff-gggg-hhhh-iiii-jjjjjjjjjjjj"
            if (os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"))
            else str(uuid.uuid4()),
            "module_type": "resources",
        }

        manifest_template = self.jinja_env.get_template("manifest.json")
        manifest_content = manifest_template.render(**manifest_data)

        manifest_file = rp_path / "manifest.json"
        manifest_file.write_text(manifest_content)
        files_created.append(str(manifest_file))

        # Create blocks directory and block JSON
        blocks_dir = rp_path / "blocks"
        blocks_dir.mkdir(exist_ok=True)

        block_data = {"namespace": namespace, "block_name": block_name, "texture_name": block_name}

        # Use enhanced template engine for resource pack blocks
        block_content = self.template_engine.render_template(
            feature_type="block",
            properties={},  # In future, this will come from Java analysis
            context=block_data,
            pack_type="rp",
        )

        block_file = blocks_dir / f"{block_name}.json"
        block_file.write_text(block_content)
        files_created.append(str(block_file))

        # Copy and process texture
        texture_files = self._copy_texture_mvp(rp_path, block_name, texture_path, jar_path)
        files_created.extend(texture_files)

        return files_created

    def _copy_texture_mvp(
        self, rp_path: Path, block_name: str, texture_path: str, jar_path: str
    ) -> List[str]:
        """Copy and resize texture from JAR to resource pack."""
        files_created = []

        try:
            # Create textures directory
            textures_dir = rp_path / "textures" / "blocks"
            textures_dir.mkdir(parents=True, exist_ok=True)

            # Extract texture from JAR
            with zipfile.ZipFile(jar_path, "r") as jar:
                if texture_path in jar.namelist():
                    # Read texture data
                    texture_data = jar.read(texture_path)

                    # Process with Pillow
                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        temp_file.write(texture_data)
                        temp_file.flush()
                        temp_file_path = temp_file.name

                    try:
                        # Open and resize to 16x16 (Bedrock standard)
                        with Image.open(temp_file_path) as img:
                            # Convert to RGBA for consistency
                            img = img.convert("RGBA")

                            # Resize to 16x16 if needed
                            if img.size != (16, 16):
                                img = img.resize((16, 16), Image.Resampling.NEAREST)
                                logger.info(f"Resized texture from {img.size} to 16x16")

                            # Save to resource pack with deterministic settings
                            output_path = textures_dir / f"{block_name}.png"
                            img.save(output_path, "PNG", optimize=False, compress_level=6)
                            files_created.append(str(output_path))

                            logger.info(f"Texture copied: {texture_path} -> {output_path}")
                    except Exception as img_error:
                        logger.warning(f"Failed to process texture {texture_path}: {img_error}")
                        # Create a deterministic fallback 16x16 colored texture
                        fallback_img = Image.new(
                            "RGBA", (16, 16), (139, 69, 19, 255)
                        )  # Brown color
                        output_path = textures_dir / f"{block_name}.png"
                        # Save with consistent PNG settings for deterministic output
                        fallback_img.save(output_path, "PNG", optimize=False, compress_level=6)
                        files_created.append(str(output_path))
                        logger.info(f"Created fallback texture: {output_path}")
                    finally:
                        # Clean up temp file
                        try:
                            os.unlink(temp_file_path)
                        except OSError:
                            pass
                else:
                    logger.warning(f"Texture not found in JAR: {texture_path}")

        except Exception as e:
            logger.error(f"Error copying texture: {e}")
            raise

        return files_created

    def _package_addon_mvp(self, temp_path: Path, addon_path: Path) -> None:
        """Package BP and RP into .mcaddon file."""
        try:
            # Create zip file with .mcaddon extension
            with zipfile.ZipFile(addon_path, "w", zipfile.ZIP_DEFLATED) as addon_zip:
                # Add all files from temp directory
                for root, dirs, files in os.walk(temp_path):
                    for file in files:
                        file_path = Path(root) / file
                        # Calculate relative path from temp_path
                        rel_path = file_path.relative_to(temp_path)
                        addon_zip.write(file_path, rel_path)

            logger.info(f"Packaged add-on: {addon_path} ({addon_path.stat().st_size} bytes)")

        except Exception as e:
            logger.error(f"Error packaging add-on: {e}")
            raise

    def _extract_all_textures_from_jar(
        self, jar_path: str, rp_path: Path, namespace: str
    ) -> Dict[str, Any]:
        """
        Bulk extract all textures from JAR's assets/*/textures/ directories.

        This is the fix for Issue #999 - the pipeline was only extracting textures
        that were explicitly referenced by detected blocks/entities, missing the
        majority of textures in complex mods.

        Also handles non-standard JAR layouts (Issue #1105) by trying alternative
        texture locations when standard patterns yield no results.

        Args:
            jar_path: Path to the source JAR file
            rp_path: Path to the resource pack directory
            namespace: Default namespace if not found in JAR

        Returns:
            Dict with extraction results (extracted_count, copied_files, errors, warnings)
        """
        result = {
            "extracted_count": 0,
            "copied_files": [],
            "errors": [],
            "skipped_count": 0,
            "warnings": [],
            "layout_detected": "standard",
        }

        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                file_list = jar.namelist()

                texture_files = []
                mcmeta_files = set()

                standard_texture_files = [
                    f
                    for f in file_list
                    if f.startswith("assets/") and "/textures/" in f and f.endswith(".png")
                ]

                mcmeta_files = set(
                    f
                    for f in file_list
                    if f.startswith("assets/") and "/textures/" in f and f.endswith(".png.mcmeta")
                )

                if standard_texture_files:
                    texture_files = standard_texture_files
                    result["layout_detected"] = "standard"
                    logger.info(
                        f"Bulk texture extraction: found {len(texture_files)} textures in standard layout"
                    )
                else:
                    alt_patterns = ["textures/", "assets/textures/", "/textures/"]
                    alt_texture_files = [
                        f
                        for f in file_list
                        if any(f.startswith(pattern) for pattern in alt_patterns)
                        and f.endswith(".png")
                    ]

                    if alt_texture_files:
                        texture_files = alt_texture_files
                        result["layout_detected"] = "non-standard"
                        result["warnings"].append(
                            f"Non-standard JAR layout detected (Issue #1105). "
                            f"Found {len(texture_files)} textures in alternative locations. "
                            f"Standard assets/*/textures/ pattern yielded 0 results."
                        )
                        logger.warning(
                            f"Bulk texture extraction: found {len(texture_files)} textures in non-standard layout "
                            f"(alternative patterns). Standard assets/*/textures/ pattern yielded 0 results."
                        )

                        alt_mcmeta_files = [
                            f
                            for f in file_list
                            if any(f.startswith(pattern) for pattern in alt_patterns)
                            and f.endswith(".png.mcmeta")
                        ]
                        mcmeta_files = set(alt_mcmeta_files)
                    else:
                        result["layout_detected"] = "none"
                        result["warnings"].append(
                            "No textures found in JAR. Tried standard assets/*/textures/ and "
                            "alternative patterns (textures/, assets/textures/, /textures/). "
                            "This may indicate a non-standard mod structure or empty asset directory."
                        )
                        logger.warning(
                            "Bulk texture extraction: No textures found in JAR. "
                            "Tried standard assets/*/textures/ and alternative patterns."
                        )

                for texture_file in texture_files:
                    try:
                        texture_data = jar.read(texture_file)

                        bedrock_path = self._map_java_texture_to_bedrock(texture_file)

                        full_output_dir = rp_path / Path(bedrock_path).parent
                        full_output_dir.mkdir(parents=True, exist_ok=True)

                        output_file = rp_path / bedrock_path
                        with open(output_file, "wb") as f:
                            f.write(texture_data)

                        result["copied_files"].append(
                            {
                                "original_path": texture_file,
                                "bedrock_path": bedrock_path,
                                "output_path": str(output_file),
                            }
                        )
                        result["extracted_count"] += 1

                        mcmeta_path = texture_file + ".mcmeta"
                        if mcmeta_path in mcmeta_files:
                            mcmeta_data = jar.read(mcmeta_path)
                            mcmeta_output = output_file.with_suffix(".png.mcmeta")
                            with open(mcmeta_output, "wb") as f:
                                f.write(mcmeta_data)
                            result["copied_files"].append(
                                {
                                    "original_path": mcmeta_path,
                                    "bedrock_path": str(mcmeta_output.relative_to(rp_path)),
                                    "output_path": str(mcmeta_output),
                                    "is_mcmeta": True,
                                }
                            )

                    except Exception as e:
                        result["errors"].append(f"Failed to extract {texture_file}: {str(e)}")
                        result["skipped_count"] += 1

                logger.info(
                    f"Bulk texture extraction complete: {result['extracted_count']} textures, "
                    f"{result['skipped_count']} skipped, {len(result['errors'])} errors, "
                    f"layout={result['layout_detected']}"
                )

        except zipfile.BadZipFile:
            result["errors"].append(f"Invalid JAR file: {jar_path}")
        except Exception as e:
            result["errors"].append(f"Failed to extract textures: {str(e)}")

        return result

    def _extract_atlas_textures_from_jar(
        self,
        jar_path: str,
        rp_path: Path,
        namespace: str,
    ) -> Dict[str, Any]:
        """
        Extract textures from sprite sheet atlases using JSON descriptors.

        This handles mods like JEI and JourneyMap that pack their textures
        into sprite sheet atlases with accompanying JSON descriptor files
        that map sprite names to regions.

        Args:
            jar_path: Path to the source JAR file
            rp_path: Path to the resource pack directory
            namespace: Default namespace if not found in JAR

        Returns:
            Dict with extraction results (extracted_count, copied_files, errors, warnings)
        """
        result = {
            "extracted_count": 0,
            "copied_files": [],
            "errors": [],
            "skipped_count": 0,
            "warnings": [],
            "atlases_detected": 0,
            "atlases_processed": 0,
        }

        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                jar.namelist()

                # Find all potential atlas textures
                atlases = find_atlas_textures_in_jar(jar, namespace)

                if not atlases:
                    return result

                result["atlases_detected"] = len(atlases)
                logger.info(
                    f"Atlas detection: found {len(atlases)} potential atlas textures in JAR"
                )

                for atlas_info in atlases:
                    atlas_path = atlas_info["texture_path"]

                    try:
                        # Look for associated JSON descriptor
                        json_descriptors = find_atlas_descriptors_in_jar(jar, namespace, "gui")
                        descriptor_path = json_descriptors.get(atlas_path)

                        # Read atlas image data
                        atlas_data = jar.read(atlas_path)

                        # Save to temp file for PIL processing
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_atlas:
                            temp_atlas.write(atlas_data)
                            temp_atlas_path = temp_atlas.name

                        sprites = {}

                        if descriptor_path:
                            # Parse the JSON descriptor
                            try:
                                desc_data = jar.read(descriptor_path)
                                json.loads(desc_data.decode("utf-8"))
                                sprites = parse_atlas_descriptor(descriptor_path, atlas_path)
                                logger.info(
                                    f"Found atlas descriptor for {atlas_path}: "
                                    f"{len(sprites)} sprites"
                                )
                            except Exception as e:
                                result["warnings"].append(
                                    f"Failed to parse descriptor {descriptor_path}: {e}"
                                )

                        if not sprites:
                            # No descriptor - log and skip gracefully
                            result["warnings"].append(
                                f"No descriptor for atlas {atlas_path}, skipping "
                                f"(manual extraction needed)"
                            )
                            logger.info(f"Skipping atlas {atlas_path} - no descriptor found")
                            # Clean up temp file
                            Path(temp_atlas_path).unlink(missing_ok=True)
                            continue

                        # Extract sprites using descriptor info
                        extracted = extract_sprites_from_atlas(
                            temp_atlas_path,
                            sprites,
                            str(rp_path / "textures"),
                            naming_pattern="sprite_{name}",
                        )

                        for sprite in extracted:
                            sprite_name = sprite["name"]
                            sprite_path = sprite["path"]

                            # Map to Bedrock path
                            bedrock_path = f"textures/ui/{sprite_name}.png"

                            # Move from temp location to final location
                            final_path = rp_path / bedrock_path
                            final_path.parent.mkdir(parents=True, exist_ok=True)

                            # Read from temp, write to final
                            with open(sprite_path, "rb") as f:
                                sprite_data = f.read()
                            with open(final_path, "wb") as f:
                                f.write(sprite_data)

                            result["copied_files"].append(
                                {
                                    "original_path": atlas_path,
                                    "sprite_name": sprite_name,
                                    "bedrock_path": bedrock_path,
                                    "output_path": str(final_path),
                                    "x": sprite["x"],
                                    "y": sprite["y"],
                                    "width": sprite["width"],
                                    "height": sprite["height"],
                                }
                            )
                            result["extracted_count"] += 1

                        result["atlases_processed"] += 1

                        # Clean up temp file
                        Path(temp_atlas_path).unlink(missing_ok=True)

                    except Exception as e:
                        result["errors"].append(f"Failed to process atlas {atlas_path}: {str(e)}")
                        result["skipped_count"] += 1

                logger.info(
                    f"Atlas extraction complete: {result['extracted_count']} sprites, "
                    f"{result['atlases_processed']}/{result['atlases_detected']} atlases processed"
                )

        except zipfile.BadZipFile:
            result["errors"].append(f"Invalid JAR file: {jar_path}")
        except Exception as e:
            result["errors"].append(f"Failed to extract atlas textures: {str(e)}")

        return result

    def _map_java_texture_to_bedrock(self, java_path: str) -> str:
        """
        Map Java mod texture path to Bedrock resource pack texture path.

        Java (standard): assets/<namespace>/textures/<type>/<name>.png
        Java (non-standard): textures/<type>/<name>.png or assets/textures/<type>/<name>.png
        Bedrock: textures/<type>s/<name>.png (e.g., textures/blocks/name.png)

        Handles non-standard layouts (Issue #1105) where textures may be at:
        - textures/<type>/<name>.png (without assets/namespace/ prefix)
        - assets/textures/<type>/<name>.png (without namespace)

        Args:
            java_path: Java mod texture path

        Returns:
            Bedrock texture path
        """
        parts = java_path.replace("\\", "/").split("/")

        if len(parts) >= 5 and parts[0] == "assets" and parts[2] == "textures":
            texture_type = parts[3]
            texture_name = parts[4]
            bedrock_type = self._map_texture_type_to_bedrock(texture_type)
            return f"textures/{bedrock_type}/{texture_name}"

        if len(parts) >= 3 and parts[0] == "textures":
            texture_type = parts[1]
            texture_name = parts[2] if len(parts) >= 3 else Path(java_path).name
            bedrock_type = self._map_texture_type_to_bedrock(texture_type)
            return f"textures/{bedrock_type}/{texture_name}"

        if len(parts) >= 4 and parts[0] == "assets" and parts[1] == "textures":
            texture_type = parts[2]
            texture_name = parts[3] if len(parts) >= 4 else Path(java_path).name
            bedrock_type = self._map_texture_type_to_bedrock(texture_type)
            return f"textures/{bedrock_type}/{texture_name}"

        return f"textures/misc/{Path(java_path).name}"

    def _map_texture_type_to_bedrock(self, java_type: str) -> str:
        """
        Map Java texture type to Bedrock texture type (plural form).

        Args:
            java_type: Java texture type (block, item, entity, etc.)

        Returns:
            Bedrock texture type (blocks, items, entity, etc.)
        """
        type_mapping = {
            "block": "blocks",
            "item": "items",
            "entity": "entity",
            "blockentity": "entity",
            "particle": "particle",
            "armor": "armor",
            "misc": "misc",
            "environment": "environment",
            "gui": "ui",
            "painting": "painting",
        }
        return type_mapping.get(java_type.lower(), "misc")

    # Legacy methods for compatibility with existing code
    def _create_bp_manifest(self, analysis_data):
        """Legacy method for compatibility."""
        return {}

    def _create_bp_blocks(self, analysis_data):
        """Legacy method for compatibility."""
        return {}

    def _create_rp_manifest(self, analysis_data):
        """Legacy method for compatibility."""
        return {}

    def _create_rp_blocks(self, analysis_data):
        """Legacy method for compatibility."""
        return {}

    def _copy_textures(self, analysis_data):
        """Legacy method for compatibility."""
        return []

    # ------------------------------------------------------------------
    # Static implementations (used by typed BaseTool subclasses below).
    #
    # These were previously decorated with @tool @staticmethod; the
    # @tool decorator has been removed and each method renamed with a
    # leading underscore so it does not collide with the class-attribute
    # binding of the typed BaseTool instance below.
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bedrock_structure(structure_data: str) -> str:
        """Build basic Bedrock addon structure."""
        # Implementation placeholder
        return json.dumps({"success": True, "message": "Structure created"})

    @staticmethod
    def _generate_block_definitions(block_data: str) -> str:
        """Generate Bedrock block definition files."""
        # Implementation placeholder
        return json.dumps({"success": True, "message": "Block definitions generated"})

    @staticmethod
    def _convert_assets(asset_data: str) -> str:
        """Convert assets to Bedrock format."""
        # Implementation placeholder
        return json.dumps({"success": True, "message": "Assets converted"})

    @staticmethod
    def _package_addon(package_data: str) -> str:
        """Package addon into .mcaddon file."""
        # Implementation placeholder
        return json.dumps({"success": True, "message": "Addon packaged"})
