"""
Enhanced Packaging Validator for comprehensive .mcaddon validation.

Thin orchestrator composing schema validation (SchemaValidatorMixin) and
runtime checks (RuntimeValidatorMixin). Per issue #1766 this file was split:
- schema_validator.py  — data classes + structure/manifest/component checks
- runtime_validator.py — compatibility + forbidden file + version checks
- validator.py (this)  — PackagingValidator orchestration + scoring + reporting

The public API (PackagingValidator, ValidationResult, ValidationIssue,
ValidationSeverity) is unchanged; existing imports continue to work.
"""

import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .runtime_validator import RuntimeValidatorMixin
from .schema_validator import (
    SchemaValidatorMixin,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PackagingValidator",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
]


class PackagingValidator(SchemaValidatorMixin, RuntimeValidatorMixin):
    """
    Comprehensive validator for Bedrock .mcaddon packages.

    Validates:
    - Folder structure (behavior_packs/, resource_packs/)
    - Manifest.json files against official schemas
    - Block, item, and entity definitions
    - File integrity and format compliance
    - UUID uniqueness and validity
    - Version compatibility

    Schema/structure checks come from SchemaValidatorMixin; runtime
    compatibility and forbidden-file checks come from RuntimeValidatorMixin.
    """

    def __init__(self, schema_dir: Optional[Path] = None):
        """Initialize validator with JSON schemas."""
        if schema_dir is None:
            schema_dir = Path(__file__).parent.parent.parent / "schemas"

        self.schema_dir = Path(schema_dir)
        self.schemas = self._load_schemas()

        self.required_top_level_dirs = {
            "behavior_packs": "Behavior packs (plural)",
            "resource_packs": "Resource packs (plural)",
        }

        self.forbidden_patterns = [
            "behavior_pack/",
            "resource_pack/",
            ".tmp",
            ".temp",
            "~$",
            "Thumbs.db",
            ".DS_Store",
        ]

        self.behavior_pack_dirs = {
            "animations",
            "animation_controllers",
            "blocks",
            "entities",
            "functions",
            "items",
            "loot_tables",
            "recipes",
            "scripts",
            "spawn_rules",
            "texts",
            "trading",
            "dialogs",
        }

        self.resource_pack_dirs = {
            "animations",
            "animation_controllers",
            "attachables",
            "blocks",
            "entity",
            "fogs",
            "font",
            "models",
            "particles",
            "render_controllers",
            "sounds",
            "textures",
            "texts",
            "ui",
        }

        self.max_texture_size = 1024
        self.max_file_size_mb = 500
        self.max_script_size_kb = 500

    def _load_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Load JSON schemas from schema directory."""
        schemas = {}

        if not self.schema_dir.exists():
            logger.warning(f"Schema directory not found: {self.schema_dir}")
            return schemas

        schema_files = {
            "manifest": "bedrock_manifest_schema.json",
            "block": "bedrock_block_schema.json",
            "item": "bedrock_item_schema.json",
        }

        for schema_name, filename in schema_files.items():
            schema_path = self.schema_dir / filename
            if schema_path.exists():
                try:
                    with open(schema_path, "r") as f:
                        schemas[schema_name] = json.load(f)
                    logger.debug(f"Loaded schema: {schema_name}")
                except Exception as e:
                    logger.error(f"Failed to load schema {filename}: {e}")
            else:
                logger.warning(f"Schema file not found: {schema_path}")

        return schemas

    def validate_mcaddon(self, mcaddon_path: Path) -> ValidationResult:
        """Perform comprehensive validation of a .mcaddon file."""
        logger.info(f"Starting validation of {mcaddon_path}")

        issues = []
        stats = {}
        compatibility = {}
        file_structure = {}

        try:
            if not mcaddon_path.exists():
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        category="file",
                        message=f"File does not exist: {mcaddon_path}",
                    )
                )
                return self._create_result(False, issues, stats, compatibility, file_structure)

            try:
                with zipfile.ZipFile(mcaddon_path, "r") as zipf:
                    zipf.testzip()
            except zipfile.BadZipFile as e:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        category="file",
                        message=f"Invalid ZIP file: {e}",
                    )
                )
                return self._create_result(False, issues, stats, compatibility, file_structure)

            with zipfile.ZipFile(mcaddon_path, "r") as zipf:
                stats = self._analyze_package_stats(zipf)
                structure_issues, file_structure = self._validate_structure(zipf)
                issues.extend(structure_issues)
                manifest_issues = self._validate_manifests(zipf)
                issues.extend(manifest_issues)
                component_issues = self._validate_components(zipf)
                issues.extend(component_issues)
                compatibility = self._check_compatibility(zipf)
                forbidden_issues = self._check_forbidden_files(zipf)
                issues.extend(forbidden_issues)

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    category="validation",
                    message=f"Validation error: {e}",
                )
            )

        score = self._calculate_score(issues, stats)
        is_valid = not any(
            issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR]
            for issue in issues
        )

        return self._create_result(is_valid, score, issues, stats, compatibility, file_structure)

    def _analyze_package_stats(self, zipf: zipfile.ZipFile) -> Dict[str, Any]:
        """Analyze package statistics."""
        namelist = zipf.namelist()

        stats = {
            "total_files": len(namelist),
            "total_size_compressed": sum(info.compress_size for info in zipf.infolist()),
            "total_size_uncompressed": sum(info.file_size for info in zipf.infolist()),
            "behavior_packs": set(),
            "resource_packs": set(),
            "file_types": {},
            "largest_files": [],
        }

        for info in zipf.infolist():
            if not info.is_dir():
                ext = Path(info.filename).suffix.lower()
                stats["file_types"][ext] = stats["file_types"].get(ext, 0) + 1

                if info.filename.startswith("behavior_packs/"):
                    parts = info.filename.split("/")
                    if len(parts) > 1:
                        stats["behavior_packs"].add(parts[1])
                elif info.filename.startswith("resource_packs/"):
                    parts = info.filename.split("/")
                    if len(parts) > 1:
                        stats["resource_packs"].add(parts[1])

                if info.file_size > 1024 * 1024:
                    stats["largest_files"].append(
                        {"filename": info.filename, "size_mb": info.file_size / (1024 * 1024)}
                    )

        stats["behavior_packs"] = list(stats["behavior_packs"])
        stats["resource_packs"] = list(stats["resource_packs"])

        stats["largest_files"].sort(key=lambda x: x["size_mb"], reverse=True)
        stats["largest_files"] = stats["largest_files"][:10]

        return stats

    def _calculate_score(self, issues: List[ValidationIssue], stats: Dict[str, Any]) -> int:
        """Calculate overall quality score (0-100)."""
        score = 100

        for issue in issues:
            if issue.severity == ValidationSeverity.CRITICAL:
                score -= 20
            elif issue.severity == ValidationSeverity.ERROR:
                score -= 10
            elif issue.severity == ValidationSeverity.WARNING:
                score -= 3

        if stats.get("behavior_packs") and stats.get("resource_packs"):
            score += 5

        return max(0, min(100, score))

    def _create_result(
        self,
        is_valid: bool,
        score: int,
        issues: List[ValidationIssue],
        stats: Dict[str, Any],
        compatibility: Dict[str, Any],
        file_structure: Dict[str, Any],
    ) -> ValidationResult:
        """Create ValidationResult object."""
        if isinstance(score, int) and score >= 0:
            overall_score = score
        else:
            overall_score = self._calculate_score(issues, stats)

        return ValidationResult(
            is_valid=is_valid,
            overall_score=overall_score,
            issues=issues,
            stats=stats,
            compatibility=compatibility,
            file_structure=file_structure,
        )

    def generate_report(self, result: ValidationResult) -> str:
        """Generate human-readable validation report."""
        lines = []
        lines.append("=" * 80)
        lines.append("Bedrock .mcaddon Validation Report")
        lines.append("=" * 80)
        lines.append("")

        status = "PASS" if result.is_valid else "FAIL"
        lines.append(f"Overall Status: {status} (Score: {result.overall_score}/100)")
        lines.append("")

        for severity in [
            ValidationSeverity.CRITICAL,
            ValidationSeverity.ERROR,
            ValidationSeverity.WARNING,
            ValidationSeverity.INFO,
        ]:
            issues = result.get_issues_by_severity(severity)
            if issues:
                lines.append(f"{severity.value.upper()} ({len(issues)}):")
                for issue in issues:
                    location = f" [{issue.file_path}]" if issue.file_path else ""
                    lines.append(f"  - {issue.message}{location}")
                    if issue.suggestion:
                        lines.append(f"    Suggestion: {issue.suggestion}")
                lines.append("")

        lines.append("Package Statistics:")
        lines.append(f"  Total Files: {result.stats.get('total_files', 0)}")
        lines.append(f"  Behavior Packs: {len(result.stats.get('behavior_packs', []))}")
        lines.append(f"  Resource Packs: {len(result.stats.get('resource_packs', []))}")
        lines.append("")

        lines.append("Compatibility:")
        comp = result.compatibility
        lines.append(
            f"  Minimum Version: {'.'.join(map(str, comp.get('min_version', [1, 16, 0])))}"
        )
        lines.append(f"  Experimental Features: {len(comp.get('experimental_features', []))}")
        lines.append("")

        return "\n".join(lines)
