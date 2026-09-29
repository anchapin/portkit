"""
LoRA adapter concerns: weight injection and training-dataset preparation.

This module owns the LoRA-specific pieces split out from ``diffusion_lora.py``
per issue #1768:

- :func:`load_lora_weights` — inject PEFT/LoRA weights into a diffusers pipeline.
- :class:`DatasetEntry` / :class:`TexturePairDataset` — Java↔Bedrock texture pair
  dataset used to collect LoRA fine-tuning data.
- :func:`prepare_training_dataset` — build a category summary from the dataset.

Layering: this module imports nothing from ``model`` or ``pipeline`` so it can be
imported by both without creating a cycle.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


def load_lora_weights(pipe, lora_path: str):
    """
    Load LoRA weights into a diffusers pipeline via PEFT.

    Args:
        pipe: A ``diffusers`` pipeline whose ``unet`` will be wrapped.
        lora_path: Path to the LoRA adapter directory.

    Returns:
        The pipeline with LoRA weights applied (or the original pipeline on
        failure, so callers can fall back to the base model).
    """
    try:
        from peft import PeftModel

        pipe.unet = PeftModel.from_pretrained(pipe.unet, lora_path)
        return pipe
    except Exception as e:
        logger.warning(f"Could not load LoRA weights: {e}. Using base model.")
        return pipe


@dataclass
class DatasetEntry:
    java_texture_path: str
    bedrock_texture_path: str
    texture_category: str
    resolution: Tuple[int, int]
    is_animated: bool = False


class TexturePairDataset:
    """
    Dataset class for Minecraft texture pairs used in LoRA training.
    """

    def __init__(self, dataset_path: Optional[str] = None):
        self.dataset_path = dataset_path or self._get_default_dataset_path()
        self._entries: List[DatasetEntry] = []

    def _get_default_dataset_path(self) -> str:
        """Get the default dataset path."""
        return str(Path(__file__).parent.parent.parent.parent / "training_data" / "texture_pairs")

    def load(self) -> int:
        """
        Load texture pairs from the dataset directory.

        Returns:
            Number of texture pairs loaded
        """
        if not Path(self.dataset_path).exists():
            logger.warning(f"Dataset path does not exist: {self.dataset_path}")
            return 0

        java_dir = Path(self.dataset_path) / "java"
        bedrock_dir = Path(self.dataset_path) / "bedrock"

        if not java_dir.exists() or not bedrock_dir.exists():
            logger.warning(f"Dataset directories not found: {java_dir}, {bedrock_dir}")
            return 0

        categories = ["blocks", "items", "entities", "particles", "ui"]
        count = 0

        for category in categories:
            java_cat_dir = java_dir / category
            if not java_cat_dir.exists():
                continue

            for texture_file in java_cat_dir.glob("*.png"):
                stem = texture_file.stem
                bedrock_path = bedrock_dir / category / f"{stem}.png"

                if bedrock_path.exists():
                    try:
                        with Image.open(texture_file) as img:
                            resolution = img.size
                            is_animated = self._check_animated(texture_file)

                        self._entries.append(
                            DatasetEntry(
                                java_texture_path=str(texture_file),
                                bedrock_texture_path=str(bedrock_path),
                                texture_category=category,
                                resolution=resolution,
                                is_animated=is_animated,
                            )
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Could not load texture pair {stem}: {e}")

        logger.info(f"Loaded {count} texture pairs from dataset")
        return count

    def _check_animated(self, texture_path: Path) -> bool:
        """Check if a texture is animated (has .mcmeta file)."""
        mcmeta_path = texture_path.with_suffix(".png.mcmeta")
        if not mcmeta_path.exists():
            return False

        try:
            with open(mcmeta_path) as f:
                data = json.load(f)
                return "animation" in data
        except Exception:
            return False

    def get_entries(self) -> List[DatasetEntry]:
        """Get all dataset entries."""
        return self._entries.copy()

    def filter_by_resolution(self, min_res: int = 16, max_res: int = 64) -> List[DatasetEntry]:
        """Filter entries by resolution range."""
        return [
            e
            for e in self._entries
            if min_res <= e.resolution[0] <= max_res and min_res <= e.resolution[1] <= max_res
        ]

    def filter_by_category(self, category: str) -> List[DatasetEntry]:
        """Filter entries by texture category."""
        return [e for e in self._entries if e.texture_category == category]


def prepare_training_dataset(
    output_path: str,
    min_pairs: int = 1000,
    categories: Optional[List[str]] = None,
) -> Dict[str, int]:
    """
    Prepare a training dataset from Java/Bedrock texture pairs.

    Args:
        output_path: Path to save the prepared dataset
        min_pairs: Minimum number of pairs to collect
        categories: List of categories to include

    Returns:
        Summary dict with counts per category
    """
    categories = categories or ["blocks", "items", "entities", "particles", "ui"]
    dataset = TexturePairDataset()
    dataset.load()

    summary: Dict[str, int] = {}
    for cat in categories:
        entries = dataset.filter_by_category(cat)
        summary[cat] = len(entries)

    logger.info(f"Dataset summary: {summary}")
    return summary
