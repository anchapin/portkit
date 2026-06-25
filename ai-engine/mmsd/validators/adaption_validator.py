import hashlib
import json
import os
import re
from pathlib import Path
from typing import Tuple, List, Set, Dict

from mmsd.validators.code_validator import CodeValidator
from mmsd.validators.mojmap_validator import MojmapMappingValidator


class AdaptionDatasetValidator:
    """
    Validates and deduplicates adaption lab datasets against existing MMSD data.
    """

    EXPECTED_FIELDS = ["instruction", "reasoning_trace", "java_source", "bedrock_source"]
    ADAPTION_PATTERNS = [
        r"\badaption_\w+\.jsonl$",
        r"adaption_lab",
    ]

    def __init__(self, validated_pairs_path: str):
        self.validated_pairs_path = validated_pairs_path
        self.code_validator = CodeValidator()
        self.mojmap_validator = MojmapMappingValidator()
        self._existing_hashes: Set[str] = set()
        self._load_existing_hashes()

    def _load_existing_hashes(self) -> None:
        """Pre-compute hashes of existing validated pairs for deduplication."""
        if not os.path.exists(self.validated_pairs_path):
            return

        with open(self.validated_pairs_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    h = self._compute_pair_hash(entry)
                    self._existing_hashes.add(h)
                except json.JSONDecodeError:
                    continue

        print(f"Loaded {len(self._existing_hashes)} existing pair hashes for deduplication")

    def _compute_pair_hash(self, entry: dict) -> str:
        """Compute a deterministic hash of java_source + bedrock_source."""
        java = entry.get("java_source", "")
        bedrock = entry.get("bedrock_source", "")
        combined = java + bedrock
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _compute_string_hash(self, text: str) -> str:
        """Compute a simple hash of text for near-duplicate detection."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def validate_schema(self, entry: dict) -> Tuple[bool, str]:
        """Check if entry has all required fields."""
        for field in self.EXPECTED_FIELDS:
            if field not in entry:
                return False, f"Missing field: {field}"
            if not isinstance(entry[field], str) or not entry[field].strip():
                return False, f"Empty field: {field}"
        return True, "Schema valid"

    def _has_error_fields(self, entry: dict) -> bool:
        """Check if entry has error marker fields."""
        error_fields = ["reasoning_trace", "java_source", "bedrock_source"]
        for field in error_fields:
            val = entry.get(field, "")
            if isinstance(val, str) and (val.startswith("Error:") or val.startswith("ERROR_PREFIX")):
                return True
        return False

    def validate_entry(self, entry: dict) -> Tuple[bool, str, str]:
        """
        Full validation of a single entry.

        Returns: (is_valid, validation_status, rejection_reason)
        """
        if self._has_error_fields(entry):
            return False, "error_fields", "Error fields present"

        schema_ok, schema_msg = self.validate_schema(entry)
        if not schema_ok:
            return False, "schema", schema_msg

        java_ok, java_msg = self.code_validator.validate_java(entry["java_source"])
        if not java_ok:
            return False, "java_invalid", f"Java invalid: {java_msg[:100]}"

        bedrock_ok, bedrock_msg = self.code_validator.validate_bedrock_json(entry["bedrock_source"])
        if not bedrock_ok:
            return False, "bedrock_invalid", f"Bedrock invalid: {bedrock_msg[:100]}"

        mojmap_ok, mojmap_msg = self.mojmap_validator.validate(entry["java_source"])
        if not mojmap_ok:
            return False, "non_mojmap", f"Non-Mojmap: {mojmap_msg}"

        return True, "valid", ""

    def find_adaption_datasets(self, data_dir: str) -> List[str]:
        """Find all adaption dataset files in the given directory."""
        adaption_files = []
        path = Path(data_dir)

        if not path.exists():
            return adaption_files

        for file in path.iterdir():
            if file.is_file() and file.suffix == ".jsonl":
                for pattern in self.ADAPTION_PATTERNS:
                    if re.search(pattern, file.name, re.IGNORECASE):
                        adaption_files.append(str(file))
                        break

        return sorted(adaption_files)

    def process_adaption_dataset(
        self,
        input_path: str,
        output_path: str = None,
        skip_dedup: bool = False,
    ) -> Dict[str, int]:
        """
        Process a single adaption dataset file.

        Returns statistics about the processing.
        """
        stats = {
            "total": 0,
            "valid": 0,
            "skipped_schema": 0,
            "skipped_java_invalid": 0,
            "skipped_bedrock_invalid": 0,
            "skipped_non_mojmap": 0,
            "skipped_error_fields": 0,
            "skipped_duplicate": 0,
        }

        if output_path is None:
            output_path = input_path.replace(".jsonl", "_validated.jsonl")

        with open(input_path, "r") as in_f, open(output_path, "w") as out_f:
            for line in in_f:
                stats["total"] += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    stats["skipped_schema"] += 1
                    continue

                is_valid, status, reason = self.validate_entry(entry)

                if not is_valid:
                    if status == "error_fields":
                        stats["skipped_error_fields"] += 1
                    elif status == "schema":
                        stats["skipped_schema"] += 1
                    elif status == "java_invalid":
                        stats["skipped_java_invalid"] += 1
                    elif status == "bedrock_invalid":
                        stats["skipped_bedrock_invalid"] += 1
                    elif status == "non_mojmap":
                        stats["skipped_non_mojmap"] += 1
                    continue

                if not skip_dedup:
                    pair_hash = self._compute_pair_hash(entry)
                    if pair_hash in self._existing_hashes:
                        stats["skipped_duplicate"] += 1
                        continue

                    string_hash = self._compute_string_hash(
                        entry.get("instruction", "") + entry.get("reasoning_trace", "")[:500]
                    )
                    if string_hash in self._existing_hashes:
                        stats["skipped_duplicate"] += 1
                        continue

                out_f.write(json.dumps(entry) + "\n")
                self._existing_hashes.add(pair_hash)
                stats["valid"] += 1

        return stats

    def merge_datasets(
        self,
        validated_paths: List[str],
        output_path: str,
    ) -> int:
        """
        Merge multiple validated adaption datasets into a single file.

        Returns the number of entries written.
        """
        count = 0
        written_hashes: Set[str] = set()

        with open(output_path, "w") as out_f:
            for path in validated_paths:
                if not os.path.exists(path):
                    print(f"Warning: File not found: {path}")
                    continue

                with open(path, "r") as in_f:
                    for line in in_f:
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        h = self._compute_pair_hash(entry)
                        if h in written_hashes:
                            continue

                        out_f.write(json.dumps(entry) + "\n")
                        written_hashes.add(h)
                        count += 1

        return count


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate adaption lab datasets")
    parser.add_argument(
        "--data-dir",
        default="ai-engine/mmsd/data/processed",
        help="Directory containing adaption datasets",
    )
    parser.add_argument(
        "--validated-pairs",
        default="ai-engine/mmsd/data/processed/validated_pairs.jsonl",
        help="Existing validated pairs for deduplication",
    )
    parser.add_argument(
        "--output-dir",
        default="ai-engine/mmsd/data/processed",
        help="Output directory for validated adaption datasets",
    )
    parser.add_argument(
        "--skip-dedup",
        action="store_true",
        help="Skip deduplication against existing pairs",
    )

    args = parser.parse_args()

    validator = AdaptionDatasetValidator(args.validated_pairs)
    adaption_files = validator.find_adaption_datasets(args.data_dir)

    if not adaption_files:
        print("No adaption datasets found in", args.data_dir)
        print("Expected files matching: adaption_*.jsonl or *adaption*.jsonl")
        return

    print(f"Found {len(adaption_files)} adaption dataset(s):")
    for f in adaption_files:
        print(f"  - {f}")

    validated_paths = []

    for input_path in adaption_files:
        output_path = os.path.join(
            args.output_dir,
            os.path.basename(input_path).replace(".jsonl", "_validated.jsonl"),
        )
        validated_paths.append(output_path)

        print(f"\nProcessing: {input_path}")
        stats = validator.process_adaption_dataset(
            input_path,
            output_path,
            skip_dedup=args.skip_dedup,
        )

        print(f"  Total: {stats['total']}")
        print(f"  Valid: {stats['valid']}")
        print(f"  Skipped (error fields): {stats['skipped_error_fields']}")
        print(f"  Skipped (schema): {stats['skipped_schema']}")
        print(f"  Skipped (java invalid): {stats['skipped_java_invalid']}")
        print(f"  Skipped (bedrock invalid): {stats['skipped_bedrock_invalid']}")
        print(f"  Skipped (non-Mojmap): {stats['skipped_non_mojmap']}")
        print(f"  Skipped (duplicate): {stats['skipped_duplicate']}")
        print(f"  Validated output: {output_path}")

    merged_path = os.path.join(args.output_dir, "adaption_lab_merged.jsonl")
    print(f"\nMerging {len(validated_paths)} validated files...")
    merged_count = validator.merge_datasets(validated_paths, merged_path)
    print(f"Merged {merged_count} unique entries to: {merged_path}")


if __name__ == "__main__":
    main()
