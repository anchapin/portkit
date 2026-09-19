"""
Texture converter package - handles all texture-related conversion logic.
Modularized from texture_converter.py for better organization.

Public API re-exports from submodules to maintain backwards compatibility.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

logger = logging.getLogger(__name__)

from agents.texture_converter.atlas import (
    convert_atlas_to_bedrock,
    detect_texture_atlas,
    extract_texture_atlas,
    extract_texture_atlas_from_jar,
    parse_atlas_metadata,
)
from agents.texture_converter.conversion import (
    _assess_conversion_complexity,
    _convert_single_texture,
    _generate_conversion_recommendations,
    _generate_texture_pack_structure,
    _get_recommended_resolution,
    convert_jar_textures_to_bedrock,
    convert_textures,
)
from agents.texture_converter.fallback import (
    _generate_fallback_texture,
    generate_fallback_for_jar,
)
from agents.texture_converter.jar_extractor import (
    _extract_textures_from_alt_locations,
    _get_mod_ids_from_jar,
    extract_textures_from_jar,
)
from agents.texture_converter.path_mapper import (
    _map_bedrock_texture_to_java,
    _map_bedrock_type_to_java,
    _map_java_texture_to_bedrock,
    _map_texture_type,
    convert_java_texture_path,
)
from agents.texture_converter.validation import (
    validate_texture,
    validate_textures_batch,
)
from agents.texture_converter.diffusion import (
    MinecraftTextureLoRA,
    TextureConversionPipeline,
    TextureConversionConfig,
    LoRATrainingConfig,
    TexturePairDataset,
    TextureConversionMode,
    DiffusionModelType,
    ConversionResult,
    QualityMetric,
    TexturePair,
    compute_ssim,
    compute_lpips,
    prepare_training_dataset,
)

__all__ = [
    "convert_single_texture",
    "detect_texture_atlas",
    "extract_texture_atlas",
    "parse_atlas_metadata",
    "convert_atlas_to_bedrock",
    "convert_java_texture_path",
    "validate_texture",
    "validate_textures_batch",
    "generate_fallback_texture",
    "generate_fallback_for_jar",
    "extract_textures_from_jar",
    "extract_texture_atlas_from_jar",
    "convert_jar_textures_to_bedrock",
    "MinecraftTextureLoRA",
    "TextureConversionPipeline",
    "TextureConversionConfig",
    "LoRATrainingConfig",
    "TexturePairDataset",
    "TextureConversionMode",
    "DiffusionModelType",
    "ConversionResult",
    "QualityMetric",
    "TexturePair",
    "compute_ssim",
    "compute_lpips",
    "prepare_training_dataset",
]

convert_single_texture = _convert_single_texture
generate_fallback_texture = _generate_fallback_texture
