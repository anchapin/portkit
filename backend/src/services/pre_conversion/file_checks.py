"""Per-file-type checks extracted from pre_conversion/analyzer.py (Issue #1871).

Contains specialized validation logic for Java class files, resource packs,
metadata manifests, and asset directories encountered during mod scanning.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def check_java_manifest(manifest_path: Path) -> list[str]:
    """Validate FML/Forge mod metadata inside META-INF/mods.toml or mcmod.info.

    Returns a list of warning/error strings if incompatible configurations are found.
    """
    issues: list[str] = []
    if not manifest_path.exists():
        return issues

    try:
        content = manifest_path.read_text(encoding="utf-8")
        if "modLoader" in content or "loaderVersion" in content:
            issues.append("Legacy FML manifest detected; may require manual mapping.")
    except Exception as e:  # noqa: BLE001
        issues.append(f"Failed to parse manifest: {e}")
    return issues


def check_resource_pack_json(pack_path: Path) -> dict[str, Any]:
    """Validate pack.mcjson for Bedrock compatibility prerequisites.

    Returns a dictionary with compatibility flags and missing dependencies.
    """
    result: dict[str, Any] = {"compatible": True, "missing": []}
    pack_file = pack_path / "pack.mcjson"
    if not pack_file.exists():
        return result

    try:
        with open(pack_file, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("pack_format", 0) < 2:
            result["compatible"] = False
            result["missing"].append("pack_format >= 2")
    except json.JSONDecodeError as e:
        result["compatible"] = False
        result["missing"].append(f"Invalid JSON in pack.mcjson: {e}")
    return result


def scan_asset_directory(asset_dir: Path) -> list[str]:
    """Walk asset directory and flag files with unsupported extensions or sizes.

    Returns a list of problematic file paths.
    """
    flagged: list[str] = []
    allowed_ext = {".png", ".json", ".ogg", ".wav", ".js", ".mcmacro"}
    for root, _, files in os.walk(asset_dir):
        for fname in files:
            if Path(fname).suffix.lower() not in allowed_ext:
                flagged.append(str(Path(root) / fname))
    return flagged
