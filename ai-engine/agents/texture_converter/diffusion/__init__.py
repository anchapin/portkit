"""
Diffusion + LoRA subpackage for AI-powered Minecraft texture conversion.

Public interface re-exported from the focused submodules split out of the
former ``diffusion_lora.py`` monolith (issue #1768):

- ``model``         — diffusion model loading, inference, shared types, metrics
- ``lora_adapter``  — LoRA weight injection + training dataset
- ``pipeline``      — batch orchestration of AI conversion with fallback

Importing from ``agents.texture_converter.diffusion`` is the supported entry
point. The legacy ``agents.texture_converter.diffusion_lora`` module remains as a
backwards-compatibility shim that re-exports these symbols.
"""

from agents.texture_converter.diffusion.lora_adapter import (
    DatasetEntry,
    TexturePairDataset,
    load_lora_weights,
    prepare_training_dataset,
)
from agents.texture_converter.diffusion.model import (
    ConversionResult,
    DiffusionModelType,
    LoRATrainingConfig,
    MinecraftTextureLoRA,
    QualityMetric,
    TextureConversionConfig,
    TextureConversionMode,
    TexturePair,
    compute_lpips,
    compute_ssim,
)
from agents.texture_converter.diffusion.pipeline import TextureConversionPipeline

__all__ = [
    "ConversionResult",
    "DatasetEntry",
    "DiffusionModelType",
    "LoRATrainingConfig",
    "MinecraftTextureLoRA",
    "QualityMetric",
    "TextureConversionConfig",
    "TextureConversionMode",
    "TextureConversionPipeline",
    "TexturePair",
    "TexturePairDataset",
    "compute_lpips",
    "compute_ssim",
    "load_lora_weights",
    "prepare_training_dataset",
]
