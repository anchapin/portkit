"""
Asset Converter Agent - Texture module.

Contains texture-related methods that delegate to texture_converter subpackage.
"""

from pathlib import Path
from typing import Dict, List, Optional

# Import texture functions from the texture_converter subpackage
from agents.texture_converter import (
    convert_textures as _convert_textures,
    detect_texture_atlas,
    extract_texture_atlas,
    parse_atlas_metadata,
    convert_atlas_to_bedrock,
    convert_java_texture_path,
    validate_texture as _validate_texture,
    validate_textures_batch,
    generate_fallback_for_jar,
    extract_textures_from_jar as _extract_textures_from_jar,
    extract_texture_atlas_from_jar,
    convert_jar_textures_to_bedrock,
    _generate_fallback_texture,
    _get_mod_ids_from_jar,
    _extract_textures_from_alt_locations,
    _map_java_texture_to_bedrock,
    _map_texture_type,
    _map_bedrock_texture_to_java,
    _map_bedrock_type_to_java,
    _get_recommended_resolution,
    _generate_conversion_recommendations,
    _assess_conversion_complexity,
    _convert_single_texture as _tc_convert_single_texture,
    _generate_texture_pack_structure as _tc_generate_texture_pack_structure,
)


def convert_textures(agent, texture_list: str, output_path: str) -> str:
    """Convert textures to Bedrock format."""
    return _convert_textures(agent, texture_list, output_path)


def detect_texture_atlas(agent, texture_path: str) -> Dict:
    """Detect if a texture is part of an atlas."""
    return detect_texture_atlas(agent, texture_path)


def extract_texture_atlas(
    agent,
    atlas_path: str,
    output_dir: str,
    tile_size: int = 16,
    naming_pattern: str = "tile_{x}_{y}",
) -> Dict:
    """Extract individual textures from an atlas."""
    return extract_texture_atlas(agent, atlas_path, output_dir, tile_size, naming_pattern)


def parse_atlas_metadata(agent, mcmeta_path: str) -> Dict:
    """Parse atlas metadata from .mcmeta file."""
    return parse_atlas_metadata(agent, mcmeta_path)


def convert_atlas_to_bedrock(
    agent, atlas_path: str, output_dir: str, texture_names: List[str] = None
) -> Dict:
    """Convert a texture atlas to Bedrock format."""
    return convert_atlas_to_bedrock(agent, atlas_path, output_dir, texture_names)


def convert_java_texture_path(agent, java_path: str, bedrock_type: str = "blocks") -> str:
    """Convert a Java texture path to Bedrock format."""
    return convert_java_texture_path(agent, java_path, bedrock_type)


def validate_texture(agent, texture_path: str) -> Dict:
    """Validate a texture for Bedrock compatibility."""
    return _validate_texture(agent, texture_path)


def generate_fallback_for_jar(
    agent, output_path: str, block_name: str, texture_type: str = "blocks"
) -> Dict:
    """Generate a fallback texture for a JAR mod."""
    return generate_fallback_for_jar(agent, output_path, block_name, texture_type)


def _get_recommended_resolution(agent, width: int, height: int) -> str:
    """Get recommended resolution for a texture."""
    return _get_recommended_resolution(agent, width, height)


def _generate_conversion_recommendations(agent, analysis: Dict) -> List[str]:
    """Generate conversion recommendations based on analysis."""
    return _generate_conversion_recommendations(agent, analysis)


def _assess_conversion_complexity(agent, analysis: Dict) -> str:
    """Assess the complexity of texture conversion."""
    return _assess_conversion_complexity(agent, analysis)


def extract_textures_from_jar(
    agent, jar_path: str, output_dir: str, texture_types: Optional[List[str]] = None
) -> Dict:
    """Extract textures from a Java mod JAR file."""
    return _extract_textures_from_jar(agent, jar_path, output_dir, texture_types)


def _map_java_texture_to_bedrock(agent, java_path: str) -> str:
    """Map a Java texture path to Bedrock format."""
    return _map_java_texture_to_bedrock(agent, java_path)


def _map_texture_type(agent, java_type: str) -> str:
    """Map Java texture type to Bedrock texture type."""
    return _map_texture_type(agent, java_type)


def _map_bedrock_texture_to_java(agent, bedrock_path: str, namespace: str) -> str:
    """Map a Bedrock texture path to Java format."""
    return _map_bedrock_texture_to_java(agent, bedrock_path, namespace)


def _map_bedrock_type_to_java(agent, bedrock_type: str) -> str:
    """Map Bedrock texture type to Java texture type."""
    return _map_bedrock_type_to_java(agent, bedrock_type)


def validate_textures_batch(agent, texture_paths: List[str], metadata: Dict = None) -> Dict:
    """Validate multiple textures in batch."""
    return validate_textures_batch(agent, texture_paths, metadata)


def extract_texture_atlas_from_jar(agent, jar_path: str, atlas_type: str, output_dir: str) -> Dict:
    """Extract a texture atlas from a JAR file."""
    return extract_texture_atlas_from_jar(agent, jar_path, atlas_type, output_dir)


def convert_jar_textures_to_bedrock(
    agent, jar_path: str, output_dir: str, namespace: str = None
) -> Dict:
    """Convert all textures from a JAR to Bedrock format."""
    return convert_jar_textures_to_bedrock(agent, jar_path, output_dir, namespace)


def _generate_fallback_texture(agent, usage: str = "block", size: tuple = (16, 16)):
    """Generate a fallback texture."""
    return _generate_fallback_texture(agent, usage, size)


def _get_mod_ids_from_jar(agent, jar) -> List[str]:
    """Get mod IDs from a JAR file."""
    return _get_mod_ids_from_jar(agent, jar)


def _extract_textures_from_alt_locations(agent, jar, output_path: Path):
    """Extract textures from alternative locations in a JAR."""
    return _extract_textures_from_alt_locations(agent, jar, output_path)


def _convert_single_texture(
    agent, texture_path: str, metadata: Dict, usage: str, output_dir: Path = None
) -> Dict:
    """Convert a single texture to Bedrock format."""
    return _tc_convert_single_texture(agent, texture_path, metadata, usage, output_dir)


def _generate_texture_pack_structure(agent, textures: List[Dict]) -> Dict:
    """Generate texture pack structure files."""
    return _tc_generate_texture_pack_structure(agent, textures)
