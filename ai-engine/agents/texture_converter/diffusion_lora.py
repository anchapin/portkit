"""
Backwards-compatibility shim.

The contents of this module have been split into the ``diffusion`` subpackage
per issue #1768:

- :mod:`agents.texture_converter.diffusion.model`        — model loading/inference
- :mod:`agents.texture_converter.diffusion.lora_adapter` — LoRA weights + dataset
- :mod:`agents.texture_converter.diffusion.pipeline`     — batch orchestration

This shim re-exports the previous public API so existing imports of the form
``from agents.texture_converter.diffusion_lora import X`` keep working.
Prefer importing from :mod:`agents.texture_converter.diffusion` in new code.
"""

from agents.texture_converter.diffusion import (  # noqa: F401
    ConversionResult,
    DatasetEntry,
    DiffusionModelType,
    LoRATrainingConfig,
    MinecraftTextureLoRA,
    QualityMetric,
    TextureConversionConfig,
    TextureConversionMode,
    TextureConversionPipeline,
    TexturePair,
    TexturePairDataset,
    compute_lpips,
    compute_ssim,
    load_lora_weights,
    prepare_training_dataset,
)

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
