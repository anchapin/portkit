import json
import os
from pathlib import Path
from typing import List, Optional, Tuple


class AdaptionDatasetLoader:
    """
    Loads adaption lab datasets and integrates them with MMSD training data.

    The adaption lab datasets are expected to be at:
        ai-engine/mmsd/data/processed/adaption_*.jsonl

    Each entry must have:
        - instruction: str
        - reasoning_trace: str
        - java_source: str
        - bedrock_source: str
    """

    DEFAULT_DATA_DIR = "ai-engine/mmsd/data/processed"
    MERGED_OUTPUT = "adaption_lab_merged.jsonl"

    ADAPTION_FILE_PATTERNS = [
        "adaption_minecraft_mod_to_bedrock.jsonl",
        "adaption_minecraft_bedrock_mod_conversions.jsonl",
        "adaption_minecraft_mod_conversion_pairs.jsonl",
    ]

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self._discovered_files: List[str] = []
        self._merged_cache: Optional[List[dict]] = None

    def discover_adaption_files(self) -> List[str]:
        """Find all adaption dataset files in the data directory."""
        self._discovered_files = []

        if not self.data_dir.exists():
            return self._discovered_files

        for filename in self.ADAPTION_FILE_PATTERNS:
            filepath = self.data_dir / filename
            if filepath.exists():
                self._discovered_files.append(str(filepath))

        for file in self.data_dir.iterdir():
            if file.is_file() and file.suffix == ".jsonl":
                if "adaption" in file.name.lower() and str(file) not in self._discovered_files:
                    self._discovered_files.append(str(file))

        return sorted(self._discovered_files)

    def get_merged_path(self) -> str:
        """Get the path to the merged adaption dataset."""
        return str(self.data_dir / self.MERGED_OUTPUT)

    def load_adaption_pairs(self, validated_only: bool = True) -> List[dict]:
        """
        Load adaption dataset pairs.

        Args:
            validated_only: If True, load from the validated merged file.
                          If False, load from original adaption files (not recommended for training).

        Returns:
            List of adaption dataset entries.
        """
        pairs = []

        if validated_only:
            merged_path = self.get_merged_path()
            if os.path.exists(merged_path):
                with open(merged_path, "r") as f:
                    for line in f:
                        if line.strip():
                            pairs.append(json.loads(line))
                return pairs

        for filepath in self.discover_adaption_files():
            if "validated" not in filepath:
                continue

            with open(filepath, "r") as f:
                for line in f:
                    if line.strip():
                        pairs.append(json.loads(line))

        return pairs

    def get_adaption_stats(self) -> dict:
        """Get statistics about available adaption datasets."""
        stats = {
            "discovered_files": [],
            "total_pairs": 0,
            "has_merged": False,
            "merged_pairs": 0,
        }

        for filepath in self.discover_adaption_files():
            count = 0
            with open(filepath, "r") as f:
                for line in f:
                    if line.strip():
                        count += 1
            stats["discovered_files"].append({
                "path": filepath,
                "pairs": count,
            })
            stats["total_pairs"] += count

        merged_path = self.get_merged_path()
        if os.path.exists(merged_path):
            stats["has_merged"] = True
            with open(merged_path, "r") as f:
                stats["merged_pairs"] = sum(1 for line in f if line.strip())

        return stats

    def merge_adaption_files(
        self,
        output_path: Optional[str] = None,
        skip_dedup_with: Optional[str] = None,
    ) -> Tuple[int, List[str]]:
        """
        Merge all validated adaption files into a single dataset.

        Args:
            output_path: Path for merged output. Defaults to adaption_lab_merged.jsonl
            skip_dedup_with: Path to existing pairs file for deduplication.

        Returns:
            Tuple of (merged_count, written_files)
        """
        import hashlib

        if output_path is None:
            output_path = self.get_merged_path()

        seen_hashes = set()
        merged_count = 0
        written_files = []

        validated_files = [f for f in self.discover_adaption_files() if "validated" in f]

        if not validated_files:
            print("No validated adaption files found to merge")
            return 0, []

        dedup_hashes = set()
        if skip_dedup_with and os.path.exists(skip_dedup_with):
            with open(skip_dedup_with, "r") as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        java = entry.get("java_source", "")
                        bedrock = entry.get("bedrock_source", "")
                        h = hashlib.sha256((java + bedrock).encode()).hexdigest()[:16]
                        dedup_hashes.add(h)
            print(f"Deduplicating against {len(dedup_hashes)} existing pairs")

        with open(output_path, "w") as out_f:
            for filepath in validated_files:
                with open(filepath, "r") as in_f:
                    for line in in_f:
                        if not line.strip():
                            continue

                        entry = json.loads(line)
                        java = entry.get("java_source", "")
                        bedrock = entry.get("bedrock_source", "")
                        h = hashlib.sha256((java + bedrock).encode()).hexdigest()[:16]

                        if h in seen_hashes:
                            continue
                        if h in dedup_hashes:
                            continue

                        out_f.write(json.dumps(entry) + "\n")
                        seen_hashes.add(h)
                        merged_count += 1

                written_files.append(filepath)

        self._merged_cache = None
        return merged_count, written_files


def load_training_data(
    mmsd_path: str = "ai-engine/mmsd/data/processed/validated_pairs.jsonl",
    adaption_data_dir: str = "ai-engine/mmsd/data/processed",
    include_adaption: bool = True,
    adaption_weight: float = 1.0,
) -> Tuple[List[dict], List[dict], dict]:
    """
    Load MMSD and adaption lab data for training.

    Args:
        mmsd_path: Path to validated MMSD pairs
        adaption_data_dir: Directory containing adaption datasets
        include_adaption: Whether to include adaption data
        adaption_weight: Weight multiplier for adaption data (for sampling)

    Returns:
        Tuple of (mmsd_pairs, adaption_pairs, data_stats)
    """
    mmsd_pairs = []

    if os.path.exists(mmsd_path):
        with open(mmsd_path, "r") as f:
            for line in f:
                if line.strip():
                    mmsd_pairs.append(json.loads(line))

    adaption_pairs = []
    adaption_stats = {}

    if include_adaption:
        loader = AdaptionDatasetLoader(adaption_data_dir)
        adaption_pairs = loader.load_adaption_pairs(validated_only=True)
        adaption_stats = loader.get_adaption_stats()

    stats = {
        "mmsd_pairs": len(mmsd_pairs),
        "adaption_pairs": len(adaption_pairs),
        "adaption_files": adaption_stats.get("discovered_files", []),
        "adaption_merged": adaption_stats.get("merged_pairs", 0),
        "total_pairs": len(mmsd_pairs) + len(adaption_pairs) * int(adaption_weight),
    }

    return mmsd_pairs, adaption_pairs, stats
