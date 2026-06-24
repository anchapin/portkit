"""
Schema and structure validation for Bedrock .mcaddon packages.

Extracted from packaging/validator.py per issue #1766. Contains:
- Data classes (ValidationSeverity, ValidationIssue, ValidationResult)
- SchemaValidatorMixin: folder structure, manifest, and component validation

These are consumed by PackagingValidator (see validator.py) via mixin
composition so the public API (PackagingValidator, ValidationResult, ...)
remains unchanged.
"""

import json
import uuid
import zipfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import jsonschema


class ValidationSeverity(Enum):
    """Validation issue severity levels."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""

    severity: ValidationSeverity
    category: str
    message: str
    file_path: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Complete validation result for an .mcaddon package."""

    is_valid: bool
    overall_score: int
    issues: List[ValidationIssue]
    stats: Dict[str, Any]
    compatibility: Dict[str, Any]
    file_structure: Dict[str, Any]

    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Get all issues of a specific severity."""
        return [issue for issue in self.issues if issue.severity == severity]

    def get_issues_by_category(self, category: str) -> List[ValidationIssue]:
        """Get all issues in a specific category."""
        return [issue for issue in self.issues if issue.category == category]


class SchemaValidatorMixin:
    """
    Mixin providing schema, structure, and component validation for
    .mcaddon packages.

    Relies on the following instance attributes (set by PackagingValidator):
    - ``self.schemas``: dict of loaded JSON schemas
    - ``self.behavior_pack_dirs``: set of valid behavior pack subdirectories
    - ``self.resource_pack_dirs``: set of valid resource pack subdirectories
    """

    def _validate_structure(
        self, zipf: zipfile.ZipFile
    ) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
        """Validate package folder structure."""
        issues = []
        structure = {"behavior_packs": [], "resource_packs": [], "unexpected_files": []}

        namelist = zipf.namelist()

        has_behavior_packs = any(name.startswith("behavior_packs/") for name in namelist)
        has_resource_packs = any(name.startswith("resource_packs/") for name in namelist)

        if not has_behavior_packs and not has_resource_packs:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    category="structure",
                    message="Package must contain behavior_packs/ or resource_packs/ directory",
                    suggestion="Ensure you're using plural directory names (behavior_packs/, resource_packs/)",
                )
            )

        has_old_behavior = any(name.startswith("behavior_pack/") for name in namelist)
        has_old_resource = any(name.startswith("resource_pack/") for name in namelist)

        if has_old_behavior or has_old_resource:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="structure",
                    message="Found incorrect directory structure (singular form)",
                    suggestion="Use 'behavior_packs/' and 'resource_packs/' (plural) instead of singular forms",
                )
            )

        for name in namelist:
            if name.startswith("behavior_packs/"):
                parts = name.split("/")
                if len(parts) > 1:
                    pack_name = parts[1]
                    if pack_name not in structure["behavior_packs"]:
                        structure["behavior_packs"].append(pack_name)

            elif name.startswith("resource_packs/"):
                parts = name.split("/")
                if len(parts) > 1:
                    pack_name = parts[1]
                    if pack_name not in structure["resource_packs"]:
                        structure["resource_packs"].append(pack_name)

        for pack_name in structure["behavior_packs"]:
            pack_issues = self._validate_behavior_pack_structure(zipf, pack_name, namelist)
            issues.extend(pack_issues)

        for pack_name in structure["resource_packs"]:
            pack_issues = self._validate_resource_pack_structure(zipf, pack_name, namelist)
            issues.extend(pack_issues)

        root_files = [name for name in namelist if "/" not in name.strip("/")]
        if root_files:
            structure["unexpected_files"] = root_files
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="structure",
                    message=f"Found {len(root_files)} files in package root",
                    suggestion="Files should be in behavior_packs/ or resource_packs/ subdirectories",
                )
            )

        return issues, structure

    def _validate_behavior_pack_structure(
        self, zipf: zipfile.ZipFile, pack_name: str, namelist: List[str]
    ) -> List[ValidationIssue]:
        """Validate behavior pack structure."""
        issues = []
        prefix = f"behavior_packs/{pack_name}/"

        manifest_path = f"{prefix}manifest.json"
        if manifest_path not in namelist:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    category="structure",
                    message=f"Missing manifest.json in behavior pack '{pack_name}'",
                    file_path=manifest_path,
                )
            )

        pack_files = [name for name in namelist if name.startswith(prefix)]
        for file_path in pack_files:
            parts = file_path.split("/")
            if len(parts) > 2:
                dir_name = parts[2]
                if dir_name not in self.behavior_pack_dirs:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.INFO,
                            category="structure",
                            message=f"Unexpected directory '{dir_name}' in behavior pack",
                            file_path=file_path,
                            suggestion=f"Valid directories: {', '.join(sorted(self.behavior_pack_dirs))}",
                        )
                    )

        return issues

    def _validate_resource_pack_structure(
        self, zipf: zipfile.ZipFile, pack_name: str, namelist: List[str]
    ) -> List[ValidationIssue]:
        """Validate resource pack structure."""
        issues = []
        prefix = f"resource_packs/{pack_name}/"

        manifest_path = f"{prefix}manifest.json"
        if manifest_path not in namelist:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    category="structure",
                    message=f"Missing manifest.json in resource pack '{pack_name}'",
                    file_path=manifest_path,
                )
            )

        pack_files = [name for name in namelist if name.startswith(prefix)]
        for file_path in pack_files:
            parts = file_path.split("/")
            if len(parts) > 2:
                dir_name = parts[2]
                if dir_name not in self.resource_pack_dirs:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.INFO,
                            category="structure",
                            message=f"Unexpected directory '{dir_name}' in resource pack",
                            file_path=file_path,
                            suggestion=f"Valid directories: {', '.join(sorted(self.resource_pack_dirs))}",
                        )
                    )

        return issues

    def _validate_manifests(self, zipf: zipfile.ZipFile) -> List[ValidationIssue]:
        """Validate all manifest.json files."""
        issues = []
        manifest_files = [name for name in zipf.namelist() if name.endswith("manifest.json")]

        if not manifest_files:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    category="manifest",
                    message="No manifest.json files found in package",
                )
            )
            return issues

        uuids = set()

        for manifest_path in manifest_files:
            try:
                with zipf.open(manifest_path) as f:
                    manifest = json.load(f)

                if "manifest" in self.schemas:
                    try:
                        jsonschema.validate(manifest, self.schemas["manifest"])
                    except jsonschema.ValidationError as e:
                        issues.append(
                            ValidationIssue(
                                severity=ValidationSeverity.ERROR,
                                category="manifest",
                                message=f"Schema validation failed: {e.message}",
                                file_path=manifest_path,
                                suggestion=f"Check {e.path[0] if e.path else 'root'} field",
                            )
                        )

                pack_uuid = manifest.get("header", {}).get("uuid")
                if pack_uuid:
                    try:
                        uuid.UUID(pack_uuid)
                        if pack_uuid in uuids:
                            issues.append(
                                ValidationIssue(
                                    severity=ValidationSeverity.ERROR,
                                    category="manifest",
                                    message=f"Duplicate UUID: {pack_uuid}",
                                    file_path=manifest_path,
                                )
                            )
                        uuids.add(pack_uuid)
                    except ValueError:
                        issues.append(
                            ValidationIssue(
                                severity=ValidationSeverity.ERROR,
                                category="manifest",
                                message=f"Invalid UUID format: {pack_uuid}",
                                file_path=manifest_path,
                            )
                        )
                else:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            category="manifest",
                            message="Missing UUID in header",
                            file_path=manifest_path,
                        )
                    )

                modules = manifest.get("modules", [])
                if not modules:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            category="manifest",
                            message="No modules defined",
                            file_path=manifest_path,
                        )
                    )

                for i, module in enumerate(modules):
                    module_uuid = module.get("uuid")
                    if module_uuid:
                        try:
                            uuid.UUID(module_uuid)
                            if module_uuid in uuids:
                                issues.append(
                                    ValidationIssue(
                                        severity=ValidationSeverity.ERROR,
                                        category="manifest",
                                        message=f"Duplicate module UUID: {module_uuid}",
                                        file_path=manifest_path,
                                    )
                                )
                            uuids.add(module_uuid)
                        except ValueError:
                            issues.append(
                                ValidationIssue(
                                    severity=ValidationSeverity.ERROR,
                                    category="manifest",
                                    message=f"Invalid module UUID: {module_uuid}",
                                    file_path=manifest_path,
                                )
                            )

            except json.JSONDecodeError as e:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        category="manifest",
                        message=f"Invalid JSON: {e}",
                        file_path=manifest_path,
                    )
                )
            except Exception as e:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category="manifest",
                        message=f"Validation error: {e}",
                        file_path=manifest_path,
                    )
                )

        return issues

    def _validate_components(self, zipf: zipfile.ZipFile) -> List[ValidationIssue]:
        """Validate component files (blocks, items, entities)."""
        issues = []

        for info in zipf.infolist():
            if info.is_dir():
                continue

            file_path = info.filename

            if "/blocks/" in file_path and file_path.endswith(".json"):
                issues.extend(self._validate_block_file(zipf, file_path))

            elif "/items/" in file_path and file_path.endswith(".json"):
                issues.extend(self._validate_item_file(zipf, file_path))

            elif file_path.endswith(".json"):
                issues.extend(self._validate_json_syntax(zipf, file_path))

        return issues

    def _validate_block_file(self, zipf: zipfile.ZipFile, file_path: str) -> List[ValidationIssue]:
        """Validate a block definition file."""
        issues = []

        try:
            with zipf.open(file_path) as f:
                block_data = json.load(f)

            if "block" in self.schemas:
                try:
                    jsonschema.validate(block_data, self.schemas["block"])
                except jsonschema.ValidationError as e:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            category="schema",
                            message=f"Block schema validation: {e.message}",
                            file_path=file_path,
                        )
                    )

        except json.JSONDecodeError as e:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="schema",
                    message=f"Invalid JSON in block file: {e}",
                    file_path=file_path,
                )
            )

        return issues

    def _validate_item_file(self, zipf: zipfile.ZipFile, file_path: str) -> List[ValidationIssue]:
        """Validate an item definition file."""
        issues = []

        try:
            with zipf.open(file_path) as f:
                item_data = json.load(f)

            if "item" in self.schemas:
                try:
                    jsonschema.validate(item_data, self.schemas["item"])
                except jsonschema.ValidationError as e:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            category="schema",
                            message=f"Item schema validation: {e.message}",
                            file_path=file_path,
                        )
                    )

        except json.JSONDecodeError as e:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="schema",
                    message=f"Invalid JSON in item file: {e}",
                    file_path=file_path,
                )
            )

        return issues

    def _validate_json_syntax(self, zipf: zipfile.ZipFile, file_path: str) -> List[ValidationIssue]:
        """Validate JSON syntax."""
        issues = []

        try:
            with zipf.open(file_path) as f:
                json.load(f)
        except json.JSONDecodeError as e:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="syntax",
                    message=f"Invalid JSON: {e}",
                    file_path=file_path,
                )
            )

        return issues
