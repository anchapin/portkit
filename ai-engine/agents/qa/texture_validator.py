"""
PNG format, dimensions, existence checks.
"""

import re
import struct
from typing import Any, Dict, List, Set


def validate_png_dimensions(zipf, texture_file: str) -> Dict[str, Any]:
    """Validate a PNG texture file's dimensions and format."""
    errors = []
    warnings = []

    try:
        with zipf.open(texture_file) as f:
            header = f.read(24)
            if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
                width = struct.unpack(">I", header[16:20])[0]
                height = struct.unpack(">I", header[20:24])[0]
                return {"width": width, "height": height, "valid": True}
            else:
                errors.append(f"{texture_file}: Invalid PNG format")
                return {"width": 0, "height": 0, "valid": False}
    except Exception as e:
        warnings.append(f"{texture_file}: Could not validate: {str(e)}")
        return {"width": 0, "height": 0, "valid": False}


def is_power_of_2(n: int) -> bool:
    """Check if a number is a power of 2."""
    return n != 0 and (n & (n - 1)) == 0


def validate_texture_dimensions(width: int, height: int) -> bool:
    """Check if dimensions are power of 2 or standard sizes."""
    return (is_power_of_2(width) and is_power_of_2(height)) or (width <= 512 and height <= 512)


def extract_texture_references(zipf) -> List[str]:
    """Extract all texture file references from JSON files in a ZIP."""
    texture_refs: Set[str] = set()
    namelist = zipf.namelist()

    for name in namelist:
        if name.endswith(".json"):
            try:
                with zipf.open(name) as f:
                    content = f.read().decode("utf-8", errors="ignore")

                matches = re.findall(r'"texture"\s*:\s*"([^"]+)"', content)
                texture_refs.update(matches)
            except Exception:
                continue

    return list(texture_refs)


def validate_textures(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate all textures in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    texture_files = [
        name
        for name in namelist
        if name.startswith("resource_packs/") and name.lower().endswith(".png")
    ]

    for texture_file in texture_files:
        checks += 1
        result = validate_png_dimensions(zipf, texture_file)

        if result["valid"]:
            if validate_texture_dimensions(result["width"], result["height"]):
                passed += 1
            else:
                warnings.append(
                    f"{texture_file}: Non-standard dimensions {result['width']}x{result['height']}"
                )
        else:
            if result["errors"]:
                errors.extend(result["errors"])
            if result["warnings"]:
                warnings.extend(result["warnings"])

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_texture_references(zipf, namelist: List[str]) -> Dict[str, Any]:
    """Validate that texture references in JSON files match actual files."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    texture_refs = extract_texture_references(zipf)
    if texture_refs:
        checks += 1
        missing_textures = []
        for ref in texture_refs:
            ref_variations = [
                ref,
                f"textures/{ref}",
                f"textures/{ref}.png",
                ref.replace("\\", "/"),
            ]
            if not any(any(var in name for name in namelist) for var in ref_variations):
                missing_textures.append(ref)

        if not missing_textures:
            passed += 1
        else:
            errors.append(f"Missing texture files: {missing_textures[:5]}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}
