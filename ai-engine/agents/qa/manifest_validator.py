"""
Manifest field checks, UUID format, version arrays.
"""

import re
from typing import Any, Dict, List

from .validation_rules import VALIDATION_RULES


def validate_manifest(manifest: dict, path: str) -> Dict[str, Any]:
    """
    Validate manifest against schema.

    Returns dict with checks, passed, errors, warnings.
    """
    checks = 0
    passed = 0
    errors = []
    warnings = []

    rules = VALIDATION_RULES["manifest"]

    checks += 1
    format_version = manifest.get("format_version")
    if format_version in rules["format_version"]:
        passed += 1
    else:
        errors.append(
            f"{path}: format_version must be {rules['format_version']}, got {format_version}"
        )

    header = manifest.get("header", {})
    for field in rules["required_fields"]:
        checks += 1
        if field in header and header[field]:
            passed += 1
        else:
            errors.append(f"{path}: Missing required header field: {field}")

    checks += 1
    uuid_str = header.get("uuid", "")
    # Issue #1655: UUID v4 format validation (xxxxxxxx-xxxx-4xxx-[89ab]xxx-xxxxxxxxxxxx)
    uuid_pattern = rules["uuid_pattern"]
    if re.match(uuid_pattern, uuid_str.lower()):
        passed += 1
    else:
        errors.append(f"{path}: Invalid UUID v4 format: {uuid_str}")

    checks += 1
    version = header.get("version", [])
    # Issue #1656: Version array format [major, minor, patch] with numeric values
    if (
        isinstance(version, list)
        and len(version) == 3
        and all(isinstance(v, int) for v in version)
    ):
        passed += 1
    else:
        errors.append(f"{path}: Version must be array of 3 integers [major, minor, patch], got {version}")

    checks += 1
    min_engine_version = header.get("min_engine_version", [])
    min_engine_rule = rules.get("min_engine_version", [1, 21, 0])
    if isinstance(min_engine_version, list) and len(min_engine_version) == 3:
        if min_engine_version >= min_engine_rule:
            passed += 1
        else:
            errors.append(
                f"{path}: min_engine_version {min_engine_version} is below required {min_engine_rule} "
                f"(Bedrock Scripting API 2.x requires [1, 21, 0])"
            )
    else:
        errors.append(f"{path}: min_engine_version must be array of 3 integers, got {min_engine_version}")

    checks += 1
    modules = manifest.get("modules", [])
    valid_types = rules.get("valid_module_types", [])
    if modules and isinstance(modules, list):
        passed += 1
        for i, module in enumerate(modules):
            checks += 1
            module_uuid = module.get("uuid", "")
            if re.match(rules["uuid_pattern"], module_uuid.lower()):
                passed += 1
            else:
                errors.append(f"{path}: Module {i} has invalid UUID: {module_uuid}")
            # Issue #1657: Module type validity check against Bedrock module types
            checks += 1
            module_type = module.get("type", "")
            if module_type in valid_types:
                passed += 1
            else:
                errors.append(
                    f"{path}: Module {i} has invalid type '{module_type}'. "
                    f"Valid types: {valid_types}"
                )
    else:
        errors.append(f"{path}: No modules defined or invalid modules format")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}


def validate_manifest_files(
    zipf, namelist: List[str]
) -> Dict[str, Any]:
    """Validate all manifest.json files in a ZIP archive."""
    checks = 0
    passed = 0
    errors = []
    warnings = []

    manifest_files = [name for name in namelist if name.endswith("manifest.json")]

    if manifest_files:
        for manifest_path in manifest_files:
            import json

            try:
                with zipf.open(manifest_path) as f:
                    manifest = json.load(f)

                result = validate_manifest(manifest, manifest_path)
                checks += result["checks"]
                passed += result["passed"]
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])

            except json.JSONDecodeError as e:
                checks += 1
                errors.append(f"Invalid JSON in {manifest_path}: {str(e)}")
            except Exception as e:
                checks += 1
                errors.append(f"Error reading {manifest_path}: {str(e)}")

    return {"checks": checks, "passed": passed, "errors": errors, "warnings": warnings}