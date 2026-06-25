"""
Asset Converter Agent - Backward compatibility shim.

This module has been replaced by the asset_converter/ subpackage.
All imports should now use `from agents.asset_converter import ...` instead of
`from agents.asset_converter import AssetConverterAgent, ...`.

For new code, import directly from the subpackage:
    from agents.asset_converter import AssetConverterAgent

This module re-exports from agents.asset_converter for backward compatibility.
"""

import warnings

warnings.warn(
    "agents.asset_converter has been moved to agents.asset_converter package. "
    "Please update imports to use 'from agents.asset_converter import ...' instead. "
    "This compatibility shim will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new package
from agents.asset_converter import (
    AssetConverterAgent,
    # Texture functions
    convert_textures,
    detect_texture_atlas,
    extract_texture_atlas,
    parse_atlas_metadata,
    convert_atlas_to_bedrock,
    convert_java_texture_path,
    validate_texture,
    validate_textures_batch,
    generate_fallback_for_jar,
    extract_textures_from_jar,
    extract_texture_atlas_from_jar,
    convert_jar_textures_to_bedrock,
    # Model functions
    convert_models,
    convert_blockstate,
    parse_blockstate,
    # Audio functions
    convert_audio,
    # Utility functions
    is_power_of_2,
    next_power_of_2,
    previous_power_of_2,
    analyze_assets,
    # Helper exports
    HAS_AUDIO_SUPPORT,
    # Tools
    analyze_assets_tool,
    convert_textures_tool,
    convert_models_tool,
    convert_audio_tool,
    validate_bedrock_assets_tool,
    extract_jar_textures_tool,
)

__all__ = [
    "AssetConverterAgent",
    "convert_textures",
    "detect_texture_atlas",
    "extract_texture_atlas",
    "parse_atlas_metadata",
    "convert_atlas_to_bedrock",
    "convert_java_texture_path",
    "validate_texture",
    "validate_textures_batch",
    "generate_fallback_for_jar",
    "extract_textures_from_jar",
    "extract_texture_atlas_from_jar",
    "convert_jar_textures_to_bedrock",
    "convert_models",
    "convert_blockstate",
    "parse_blockstate",
    "convert_audio",
    "is_power_of_2",
    "next_power_of_2",
    "previous_power_of_2",
    "analyze_assets",
    "HAS_AUDIO_SUPPORT",
    "analyze_assets_tool",
    "convert_textures_tool",
    "convert_models_tool",
    "convert_audio_tool",
    "validate_bedrock_assets_tool",
    "extract_jar_textures_tool",
]
