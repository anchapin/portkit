"""
Texture conversion pipeline that orchestrates diffusion + LoRA with fallback.

This module owns :class:`TextureConversionPipeline`, the user-facing orchestrator
that batches texture conversion, applies AI-powered conversion when the diffusion
model is available, and falls back to the standard converter otherwise.

Layering: imports from ``model`` (the diffusion/LoRA wrapper). Split from
``diffusion_lora.py`` per issue #1768.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from agents.texture_converter.diffusion.model import (
    ConversionResult,
    LoRATrainingConfig,
    MinecraftTextureLoRA,
    TextureConversionConfig,
    TextureConversionMode,
)

logger = logging.getLogger(__name__)


class TextureConversionPipeline:
    """
    Main pipeline that orchestrates AI-powered texture conversion
    with fallback to standard conversion methods.
    """

    def __init__(
        self,
        lora_config: Optional[LoRATrainingConfig] = None,
        conversion_config: Optional[TextureConversionConfig] = None,
    ):
        self.lora = MinecraftTextureLoRA.get_instance()
        self.lora.lora_config = lora_config or LoRATrainingConfig()
        self.lora.config = conversion_config or TextureConversionConfig()
        self._standard_converter = None

    def initialize(self, model_path: Optional[str] = None) -> bool:
        """
        Initialize the conversion pipeline.

        Args:
            model_path: Optional path to custom LoRA weights

        Returns:
            True if initialization succeeded
        """
        return self.lora.initialize(model_path)

    def is_ai_available(self) -> bool:
        """Check if AI-powered conversion is available."""
        return self.lora.is_available()

    def convert_batch(
        self,
        textures: List[Dict],
        output_dir: Path,
        conversion_mode: TextureConversionMode = TextureConversionMode.FORMAT_CONVERSION,
    ) -> List[ConversionResult]:
        """
        Convert a batch of textures with AI-powered conversion.

        Args:
            textures: List of texture dicts with 'path', 'type', 'usage' keys
            output_dir: Output directory for converted textures
            conversion_mode: The conversion mode to use

        Returns:
            List of ConversionResult objects
        """
        results = []

        if self.lora.config.use_batch_processing and self.is_ai_available():
            results = self._convert_batch_ai(textures, output_dir, conversion_mode)
        else:
            results = self._convert_batch_standard(textures, output_dir)

        return results

    def _convert_batch_ai(
        self,
        textures: List[Dict],
        output_dir: Path,
        conversion_mode: TextureConversionMode,
    ) -> List[ConversionResult]:
        """Convert textures using AI model."""
        results = []
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        batch_size = self.lora.config.batch_size

        for i in range(0, len(textures), batch_size):
            batch = textures[i : i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}, size: {len(batch)}")

            for texture_data in batch:
                texture_path = texture_data.get("path", "")
                texture_type = texture_data.get("usage", "block")

                try:
                    java_texture = Image.open(texture_path)
                    result = self.lora.convert_texture(java_texture, conversion_mode, texture_path)

                    if result.success and not result.fallback_used:
                        converted_image = self._get_converted_image(texture_path, conversion_mode)
                        if converted_image:
                            output_path = self._get_output_path(
                                output_dir, texture_path, texture_type
                            )
                            converted_image.save(output_path, "PNG", optimize=True)
                            result.converted_path = str(output_path)

                    if result.fallback_used and self.lora.config.fallback_to_standard:
                        fallback_result = self._fallback_conversion(
                            texture_path, texture_type, output_dir
                        )
                        results.append(fallback_result)
                    else:
                        results.append(result)

                except Exception as e:
                    logger.error(f"Error converting {texture_path}: {e}")
                    results.append(
                        ConversionResult(
                            success=False,
                            original_path=texture_path,
                            converted_path=None,
                            quality_score=None,
                            error=str(e),
                        )
                    )

        return results

    def _convert_batch_standard(
        self, textures: List[Dict], output_dir: Path
    ) -> List[ConversionResult]:
        """Convert textures using standard (non-AI) methods."""
        results = []
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for texture_data in textures:
            texture_path = texture_data.get("path", "")
            texture_type = texture_data.get("usage", "block")
            metadata = texture_data.get("metadata", {})

            try:
                if self._standard_converter is None:
                    self._standard_converter = self._get_standard_converter()

                result = self._standard_converter(texture_path, metadata, texture_type, output_dir)

                if result.get("success"):
                    results.append(
                        ConversionResult(
                            success=True,
                            original_path=texture_path,
                            converted_path=result.get("converted_path"),
                            quality_score=None,
                            fallback_used=True,
                            metrics={},
                        )
                    )
                else:
                    results.append(
                        ConversionResult(
                            success=False,
                            original_path=texture_path,
                            converted_path=None,
                            quality_score=None,
                            fallback_used=True,
                            error=result.get("error", "Unknown error"),
                        )
                    )
            except Exception as e:
                logger.error(f"Standard conversion error for {texture_path}: {e}")
                results.append(
                    ConversionResult(
                        success=False,
                        original_path=texture_path,
                        converted_path=None,
                        quality_score=None,
                        fallback_used=True,
                        error=str(e),
                    )
                )

        return results

    def _fallback_conversion(
        self, texture_path: str, texture_type: str, output_dir: Path
    ) -> ConversionResult:
        """Perform fallback standard conversion when AI fails."""
        return self._convert_batch_standard(
            [{"path": texture_path, "usage": texture_type}], output_dir
        )[0]

    def _get_standard_converter(self):
        """Get the standard texture converter function."""
        from agents.texture_converter import _convert_single_texture

        return _convert_single_texture

    def _get_converted_image(
        self, texture_path: str, mode: TextureConversionMode
    ) -> Optional[Image.Image]:
        """Get the converted image from cache or regenerate."""
        cache_key = f"{texture_path}_{mode.value}"
        if cache_key in self.lora._prediction_cache:
            return Image.fromarray(self.lora._prediction_cache[cache_key])
        return None

    def _get_output_path(self, output_dir: Path, original_path: str, texture_type: str) -> Path:
        """Generate the output path for a converted texture."""
        base_name = Path(original_path).stem
        subdir = texture_type if texture_type else "other"
        return output_dir / "textures" / f"{subdir}s" / f"{base_name}.png"
