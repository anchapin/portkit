"""
Runtime compatibility and cleanliness checks for Bedrock .mcaddon packages.

Extracted from packaging/validator.py per issue #1766. Contains:
- RuntimeValidatorMixin: Bedrock version compatibility, forbidden/temp file
  detection, and version comparison helpers.

Consumed by PackagingValidator (see validator.py) via mixin composition.
"""

import json
import zipfile
from typing import Any, Dict, List

from .schema_validator import ValidationIssue, ValidationSeverity


class RuntimeValidatorMixin:
    """
    Mixin providing runtime compatibility and forbidden-file checks for
    .mcaddon packages.

    Relies on the following instance attributes (set by PackagingValidator):
    - ``self.forbidden_patterns``: list of forbidden filename patterns
    """

    def _check_forbidden_files(self, zipf: zipfile.ZipFile) -> List[ValidationIssue]:
        """Check for forbidden files and patterns."""
        issues = []

        for name in zipf.namelist():
            for pattern in self.forbidden_patterns:
                if pattern in name:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            category="cleanup",
                            message=f"Found forbidden pattern: {pattern}",
                            file_path=name,
                            suggestion="Remove temporary/system files before packaging",
                        )
                    )
                    break

        return issues

    def _check_compatibility(self, zipf: zipfile.ZipFile) -> Dict[str, Any]:
        """Check Bedrock version compatibility."""
        compatibility = {
            "min_version": [1, 16, 0],
            "detected_features": [],
            "experimental_features": [],
            "platform_support": {"bedrock": True, "education": True, "preview": True},
        }

        manifest_files = [name for name in zipf.namelist() if name.endswith("manifest.json")]

        for manifest_path in manifest_files:
            try:
                with zipf.open(manifest_path) as f:
                    manifest = json.load(f)

                capabilities = manifest.get("capabilities", [])
                for cap in capabilities:
                    if "experimental" in cap.lower():
                        compatibility["experimental_features"].append(cap)
                    compatibility["detected_features"].append(cap)

                min_engine = manifest.get("header", {}).get("min_engine_version", [])
                if min_engine:
                    if self._compare_versions(min_engine, compatibility["min_version"]) > 0:
                        compatibility["min_version"] = min_engine

            except Exception:
                continue

        script_files = [name for name in zipf.namelist() if name.endswith(".js")]
        if script_files:
            compatibility["platform_support"]["education"] = False

        return compatibility

    def _compare_versions(self, v1: List[int], v2: List[int]) -> int:
        """Compare version arrays. Returns -1, 0, or 1."""
        max_len = max(len(v1), len(v2))
        for i in range(max_len):
            a = v1[i] if i < len(v1) else 0
            b = v2[i] if i < len(v2) else 0
            if a < b:
                return -1
            elif a > b:
                return 1
        return 0
