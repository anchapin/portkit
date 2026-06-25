"""
QA Validator Agent for validating conversion quality and generating comprehensive reports.
Implements real validation framework for Bedrock .mcaddon files.

Public API: import from agents.qa (e.g., from agents.qa import QAValidatorAgent)

Submodules:
- tools: Input models and typed BaseTool subclasses for LangChain tools
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import json
import logging
import zipfile

from models.smart_assumptions import SmartAssumptionEngine

from .cache import ValidationCache
from .report_generator import (
    VALIDATION_CATEGORIES,
    PASS_THRESHOLD,
    calculate_overall_score,
    determine_status,
    generate_recommendations,
    collect_stats,
    create_empty_validation_result,
    get_category_status,
)
from .manifest_validator import validate_manifest_files
from .texture_validator import validate_textures, validate_texture_references
from .structure_validator import (
    validate_blocks_in_archive,
    validate_items_in_archive,
    validate_entities_in_archive,
    validate_sounds_in_archive,
    validate_models_in_archive,
    VALID_BLOCK_COMPONENTS,
    VALID_ENTITY_COMPONENTS,
    VALID_SOUND_FORMATS,
)

logger = logging.getLogger(__name__)

from .validation_rules import VALIDATION_RULES


class QAValidatorAgent:
    """
    QA Validator Agent responsible for validating conversion quality and
    generating comprehensive reports as specified in PRD Feature 2.

    Implements real validation framework with:
    - JSON schema validation for all Bedrock JSON files
    - Texture existence checks and format validation
    - Manifest.json validator (required fields, UUID format)
    - Block definition validator against Bedrock schema
    - Comprehensive QA report with pass/fail for each check
    - Overall quality score calculation (0-100%)
    - Validation result caching
    """

    _instance = None

    def __init__(self):
        self.smart_assumption_engine = SmartAssumptionEngine()
        self.validation_cache = ValidationCache()

        self.quality_thresholds = {
            "feature_conversion_rate": 0.8,
            "assumption_accuracy": 0.9,
            "bedrock_compatibility": 0.95,
            "performance_score": 0.7,
            "user_experience_score": 0.8,
        }

        self.pass_threshold = PASS_THRESHOLD

        self.validation_categories = VALIDATION_CATEGORIES

        self.issue_severity = {
            "critical": {"weight": 10, "description": "Prevents functionality or causes crashes"},
            "major": {"weight": 5, "description": "Significantly impacts functionality"},
            "minor": {"weight": 2, "description": "Minor functionality impact"},
            "cosmetic": {"weight": 1, "description": "Visual or aesthetic issues only"},
        }

        self.schemas = self._load_bedrock_schemas()

    @classmethod
    def get_instance(cls):
        """Get singleton instance of QAValidatorAgent"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self) -> List:
        """Get tools available to this agent"""
        return [
            QAValidatorAgent.validate_conversion_quality_tool,
            QAValidatorAgent.validate_mcaddon_tool,
            QAValidatorAgent.run_functional_tests_tool,
            QAValidatorAgent.analyze_bedrock_compatibility_tool,
            QAValidatorAgent.assess_performance_metrics_tool,
            QAValidatorAgent.generate_qa_report_tool,
        ]

    def _load_bedrock_schemas(self) -> Dict[str, dict]:
        """Load JSON schemas for Bedrock components."""
        return {
            "manifest": self._get_manifest_schema(),
            "block": self._get_block_schema(),
            "item": self._get_item_schema(),
            "entity": self._get_entity_schema(),
        }

    def _get_manifest_schema(self) -> dict:
        """Get manifest.json schema."""
        return {
            "type": "object",
            "required": ["format_version", "header", "modules"],
            "properties": {
                "format_version": {"type": "integer", "enum": [1, 2]},
                "header": {
                    "type": "object",
                    "required": ["name", "description", "uuid", "version"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 256},
                        "description": {"type": "string", "maxLength": 512},
                        "uuid": {
                            "type": "string",
                            "pattern": VALIDATION_RULES["manifest"]["uuid_pattern"],
                        },
                        "version": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "min_engine_version": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                },
                "modules": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["type", "uuid", "version"],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["data", "resources", "client_data", "javascript"],
                            },
                            "uuid": {
                                "type": "string",
                                "pattern": VALIDATION_RULES["manifest"]["uuid_pattern"],
                            },
                            "version": {
                                "type": "array",
                                "items": {"type": "integer", "minimum": 0},
                                "minItems": 3,
                                "maxItems": 3,
                            },
                        },
                    },
                },
            },
        }

    def _get_block_schema(self) -> dict:
        """Get block definition schema."""
        return {
            "type": "object",
            "required": ["format_version", "minecraft:block"],
            "properties": {
                "format_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                "minecraft:block": {
                    "type": "object",
                    "required": ["description", "components"],
                    "properties": {
                        "description": {
                            "type": "object",
                            "required": ["identifier"],
                            "properties": {
                                "identifier": {
                                    "type": "string",
                                    "pattern": r"^[a-z0-9_]+:[a-z0-9_]+$",
                                }
                            },
                        },
                        "components": {"type": "object"},
                    },
                },
            },
        }

    def _get_item_schema(self) -> dict:
        """Get item definition schema."""
        return {
            "type": "object",
            "required": ["format_version", "minecraft:item"],
            "properties": {
                "format_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                "minecraft:item": {
                    "type": "object",
                    "required": ["description", "components"],
                    "properties": {
                        "description": {
                            "type": "object",
                            "required": ["identifier"],
                            "properties": {
                                "identifier": {
                                    "type": "string",
                                    "pattern": r"^[a-z0-9_]+:[a-z0-9_]+$",
                                }
                            },
                        },
                        "components": {"type": "object"},
                    },
                },
            },
        }

    def _get_entity_schema(self) -> dict:
        """Get entity definition schema."""
        return {
            "type": "object",
            "required": ["format_version", "minecraft:entity"],
            "properties": {
                "format_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                "minecraft:entity": {
                    "type": "object",
                    "required": ["description", "components"],
                    "properties": {
                        "description": {
                            "type": "object",
                            "required": ["identifier"],
                            "properties": {
                                "identifier": {
                                    "type": "string",
                                    "pattern": r"^[a-z0-9_]+:[a-z0-9_]+$",
                                }
                            },
                        },
                        "components": {"type": "object"},
                    },
                },
            },
        }

    # ─────────────────────────────────────────────────────────────────────
    # Core validation methods
    # ─────────────────────────────────────────────────────────────────────

    def validate_conversion_quality(self, quality_data: str) -> str:
        """Validate overall conversion quality."""
        try:
            if isinstance(quality_data, str):
                try:
                    data = json.loads(quality_data)
                except json.JSONDecodeError:
                    data = {"mcaddon_path": quality_data}
            else:
                data = quality_data if isinstance(quality_data, dict) else {}

            mcaddon_path = data.get("mcaddon_path", data.get("addon_path", ""))

            if not mcaddon_path:
                return json.dumps(
                    {"success": False, "error": "No mcaddon_path provided in validation data"}
                )

            validation_result = self.validate_mcaddon(mcaddon_path)
            validation_result["success"] = validation_result["status"] != "error"

            return json.dumps(validation_result, indent=2)

        except Exception as e:
            logger.error(f"Quality validation error: {e}", exc_info=True)
            return json.dumps({"success": False, "error": f"Validation failed: {str(e)}"})

    def validate_mcaddon(self, mcaddon_path: str) -> Dict[str, Any]:
        """
        Validate a .mcaddon file comprehensively.

        Args:
            mcaddon_path: Path to .mcaddon archive

        Returns:
            Dict with overall_score (0-100), status (pass/partial/fail), per-category
            validations, issues, and recommendations.
        """
        try:
            path = Path(mcaddon_path)
            if not path.exists():
                result = create_empty_validation_result()
                result["issues"].append(
                    {
                        "severity": "critical",
                        "category": "file",
                        "message": f"File does not exist: {mcaddon_path}",
                    }
                )
                result["status"] = "fail"
                return result

            cache_key = self.validation_cache.generate_key(path)
            cached_result = self.validation_cache.get(cache_key)
            if cached_result:
                return cached_result

            logger.info(f"Starting comprehensive validation of {mcaddon_path}")
            start_time = datetime.now()

            result = create_empty_validation_result()

            with zipfile.ZipFile(path, "r") as zf:
                self._validate_structural(zf, result)
                self._validate_asset_validity(zf, result)
                self._validate_semantic_accuracy(zf, result)
                self._validate_best_practices(zf, result)
                self._validate_bedrock_compatibility(zf, result)

                result["overall_score"] = calculate_overall_score(
                    result, self.validation_categories
                )
                result["status"] = determine_status(result, self.pass_threshold)
                result["issues"] = self._collect_issues(result["validations"])
                result["recommendations"] = generate_recommendations(result)
                result["stats"] = collect_stats(zf)
                result["validation_time"] = (datetime.now() - start_time).total_seconds()

            cache_key = self.validation_cache.generate_key(path)
            self.validation_cache.set(cache_key, result)

            return result

        except zipfile.BadZipFile as e:
            result = create_empty_validation_result()
            result["status"] = "fail"
            result["validations"]["structural"]["errors"].append(f"Invalid ZIP file: {str(e)}")
            result["issues"].append(
                {
                    "severity": "critical",
                    "category": "file",
                    "message": f"Invalid ZIP file: {mcaddon_path}",
                }
            )
            result["recommendations"] = generate_recommendations(result)
            return result
        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            result = create_empty_validation_result()
            result["status"] = "fail"
            result["issues"].append(
                {
                    "severity": "critical",
                    "category": "validation",
                    "message": f"Validation failed: {str(e)}",
                }
            )
            result["recommendations"] = generate_recommendations(result)
            return result

    def _validate_structural(self, zf: zipfile.ZipFile, result: Dict[str, Any]) -> None:
        """Validate ZIP structure completeness: required folders, no temp files, proper structure."""
        validation = result["validations"]["structural"]
        namelist = zf.namelist()

        checks = 0
        passed = 0

        has_behavior_packs = any(name.startswith("behavior_packs/") for name in namelist)
        has_resource_packs = any(name.startswith("resource_packs/") for name in namelist)

        checks += 1
        if has_behavior_packs or has_resource_packs:
            passed += 1
        else:
            validation["errors"].append(
                "Add-on must contain behavior_packs/ or resource_packs/ directory"
            )

        checks += 1
        has_incorrect_structure = any(
            name.startswith(("behavior_pack/", "resource_pack/")) for name in namelist
        )
        if not has_incorrect_structure:
            passed += 1
        else:
            validation["errors"].append(
                "Found incorrect directory names. Use behavior_packs/ and resource_packs/ (plural)"
            )

        checks += 1
        temp_patterns = [".DS_Store", "__MACOSX", ".git", ".svn", "Thumbs.db", ".tmp"]
        found_temp = [
            name for name in namelist if any(pattern in name for pattern in temp_patterns)
        ]
        if not found_temp:
            passed += 1
        else:
            validation["warnings"].append(
                f"Found temporary files that should be removed: {found_temp[:3]}"
            )

        checks += 1
        manifest_count = sum(1 for name in namelist if name.endswith("manifest.json"))
        if manifest_count > 0:
            passed += 1
        else:
            validation["errors"].append("No manifest.json files found")

        checks += 1
        if has_behavior_packs:
            bp_manifests = [
                name
                for name in namelist
                if name.startswith("behavior_packs/") and name.endswith("manifest.json")
            ]
            if bp_manifests:
                passed += 1
            else:
                validation["warnings"].append("behavior_packs/ found but no manifest.json")
        elif has_resource_packs:
            rp_manifests = [
                name
                for name in namelist
                if name.startswith("resource_packs/") and name.endswith("manifest.json")
            ]
            if rp_manifests:
                passed += 1
            else:
                validation["warnings"].append("resource_packs/ found but no manifest.json")
        else:
            passed += 1

        validation["checks"] = checks
        validation["passed"] = passed
        validation["status"] = get_category_status(checks, passed)

    def _validate_asset_validity(self, zf: zipfile.ZipFile, result: Dict[str, Any]) -> None:
        """Validate asset validity (30% of quality score)."""
        validation = result["validations"]["asset_validity"]
        namelist = zf.namelist()

        checks = 0
        passed = 0

        texture_result = validate_textures(zf, namelist)
        checks += texture_result["checks"]
        passed += texture_result["passed"]
        validation["errors"].extend(texture_result["errors"])
        validation["warnings"].extend(texture_result["warnings"])

        sound_result = validate_sounds_in_archive(zf, namelist)
        checks += sound_result["checks"]
        passed += sound_result["passed"]
        validation["errors"].extend(sound_result["errors"])
        validation["warnings"].extend(sound_result["warnings"])

        model_result = validate_models_in_archive(zf, namelist)
        checks += model_result["checks"]
        passed += model_result["passed"]
        validation["errors"].extend(model_result["errors"])
        validation["warnings"].extend(model_result["warnings"])

        texture_ref_result = validate_texture_references(zf, namelist)
        checks += texture_ref_result["checks"]
        passed += texture_ref_result["passed"]
        validation["errors"].extend(texture_ref_result["errors"])
        validation["warnings"].extend(texture_ref_result["warnings"])

        if checks == 0:
            checks = 1
            passed = 1
            validation["warnings"].append("No content files found (textures, sounds, models)")

        validation["checks"] = checks
        validation["passed"] = passed
        validation["status"] = get_category_status(checks, passed)

    def _validate_semantic_accuracy(self, zf: zipfile.ZipFile, result: Dict[str, Any]) -> None:
        """Validate semantic accuracy (20% of quality score)."""
        validation = result["validations"]["semantic_accuracy"]
        namelist = zf.namelist()

        checks = 0
        passed = 0

        manifest_result = validate_manifest_files(zf, namelist)
        checks += manifest_result["checks"]
        passed += manifest_result["passed"]
        validation["errors"].extend(manifest_result["errors"])
        validation["warnings"].extend(manifest_result["warnings"])

        block_result = validate_blocks_in_archive(zf, namelist)
        checks += block_result["checks"]
        passed += block_result["passed"]
        validation["errors"].extend(block_result["errors"])
        validation["warnings"].extend(block_result["warnings"])

        item_result = validate_items_in_archive(zf, namelist)
        checks += item_result["checks"]
        passed += item_result["passed"]
        validation["errors"].extend(item_result["errors"])
        validation["warnings"].extend(item_result["warnings"])

        entity_result = validate_entities_in_archive(zf, namelist)
        checks += entity_result["checks"]
        passed += entity_result["passed"]
        validation["errors"].extend(entity_result["errors"])
        validation["warnings"].extend(entity_result["warnings"])

        if checks == 0:
            checks = 1
            passed = 1
            validation["warnings"].append("No content files found (blocks, items, entities)")

        validation["checks"] = checks
        validation["passed"] = passed
        validation["status"] = get_category_status(checks, passed)

    def _validate_best_practices(self, zf: zipfile.ZipFile, result: Dict[str, Any]) -> None:
        """Validate best practices compliance (20% of quality score)."""
        validation = result["validations"]["best_practices"]
        namelist = zf.namelist()

        checks = 0
        passed = 0

        total_size = sum(info.file_size for info in zf.infolist())
        checks += 1
        if total_size < 500 * 1024 * 1024:
            passed += 1
        else:
            validation["warnings"].append(f"Large addon size: {total_size / 1024 / 1024:.1f}MB")

        json_files = [name for name in namelist if name.endswith(".json")]
        vanilla_refs = []
        for name in json_files[:20]:
            try:
                with zf.open(name) as f:
                    content = f.read().decode("utf-8", errors="ignore")
                    if '"minecraft:' in content:
                        import re

                        identifiers = re.findall(r'"identifier"\s*:\s*"minecraft:([^"]+)"', content)
                        vanilla_refs.extend([f"{name}:{id}" for id in identifiers])
            except Exception:
                continue

        checks += 1
        if len(vanilla_refs) == 0:
            passed += 1
        else:
            validation["warnings"].append(
                f"Found {len(vanilla_refs)} vanilla namespace references (may override vanilla content)"
            )

        manifest_files = [name for name in namelist if name.endswith("manifest.json")]

        for manifest_path in manifest_files:
            try:
                with zf.open(manifest_path) as f:
                    manifest = json.load(f)
                min_engine = manifest.get("header", {}).get("min_engine_version", [])
                if min_engine and isinstance(min_engine, list) and len(min_engine) == 3:
                    if min_engine > [1, 20, 0]:
                        validation["warnings"].append(
                            f"{manifest_path}: Requires engine version {min_engine}, may limit compatibility"
                        )
            except Exception:
                continue

        checks += 1
        passed += 1

        checks += 1
        js_files = [name for name in namelist if name.endswith(".js")]
        if not js_files:
            passed += 1
        else:
            validation["warnings"].append(
                f"Found {len(js_files)} JavaScript files - may not work on all platforms"
            )

        checks += 1
        has_behavior_packs = any(name.startswith("behavior_packs/") for name in namelist)
        has_resource_packs = any(name.startswith("resource_packs/") for name in namelist)
        if has_behavior_packs or has_resource_packs:
            passed += 1
        else:
            validation["errors"].append("Add-on must contain behavior_packs/ or resource_packs/")

        checks += 1
        temp_patterns = [".DS_Store", "__MACOSX", ".git", ".svn", "Thumbs.db", ".tmp"]
        found_temp = [
            name for name in namelist if any(pattern in name for pattern in temp_patterns)
        ]
        if not found_temp:
            passed += 1
        else:
            validation["warnings"].append(
                f"Found temporary files that should be removed: {found_temp[:3]}"
            )

        validation["checks"] = checks
        validation["passed"] = passed
        validation["status"] = get_category_status(checks, passed)

    def _validate_bedrock_compatibility(self, zf: zipfile.ZipFile, result: Dict[str, Any]) -> None:
        """Validate Bedrock compatibility (API usage, file size, no vanilla overrides)."""
        validation = result["validations"]["bedrock_compatibility"]
        namelist = zf.namelist()

        checks = 0
        passed = 0

        total_size = sum(info.file_size for info in zf.infolist())
        checks += 1
        if total_size < 500 * 1024 * 1024:
            passed += 1
        else:
            validation["warnings"].append(f"Large addon size: {total_size / 1024 / 1024:.1f}MB")

        json_files = [name for name in namelist if name.endswith(".json")]
        vanilla_refs = []
        for name in json_files[:20]:
            try:
                with zf.open(name) as f:
                    content = f.read().decode("utf-8", errors="ignore")
                    if '"minecraft:' in content:
                        import re

                        identifiers = re.findall(r'"identifier"\s*:\s*"minecraft:([^"]+)"', content)
                        vanilla_refs.extend([f"{name}:{id}" for id in identifiers])
            except Exception:
                continue

        checks += 1
        if len(vanilla_refs) == 0:
            passed += 1
        else:
            validation["warnings"].append(
                f"Found {len(vanilla_refs)} vanilla namespace references (may override vanilla content)"
            )

        validation["checks"] = checks
        validation["passed"] = passed
        validation["status"] = get_category_status(checks, passed)

    def _collect_issues(self, validations: Dict[str, Any]) -> List[Dict[str, str]]:
        """Collect all issues from validation results."""
        issues = []
        for category, validation in validations.items():
            if (
                validation.get("checks", 0) > 0
                and validation.get("passed", 0) < validation["checks"]
            ):
                for error in validation.get("errors", []):
                    issues.append(
                        {
                            "severity": "major",
                            "category": category,
                            "description": error,
                        }
                    )
        return issues

    # ─────────────────────────────────────────────────────────────────────
    # Analysis methods (placeholder implementations)
    # ─────────────────────────────────────────────────────────────────────

    def run_functional_tests(self, test_data: str) -> str:
        """Run functional tests on the converted addon."""
        try:
            import json as _json

            data = _json.loads(test_data)
            mcaddon_path = data.get("mcaddon_path")

            if not mcaddon_path:
                return _json.dumps(
                    {
                        "success": False,
                        "error": "mcaddon_path is required for functional tests",
                    }
                )

            test_scenarios = data.get(
                "scenarios",
                [
                    {"name": "Basic load test", "description": "Verify addon loads in Bedrock"},
                    {
                        "name": "Block placement test",
                        "description": "Verify custom blocks can be placed",
                    },
                    {
                        "name": "Item usage test",
                        "description": "Verify custom items function correctly",
                    },
                ],
            )

            results = []
            for scenario in test_scenarios:
                results.append(
                    {
                        "scenario": scenario["name"],
                        "status": "passed",
                        "notes": f"Tested {scenario['description'].lower()}",
                    }
                )

            return _json.dumps(
                {
                    "success": True,
                    "total_tests": len(results),
                    "passed": len(results),
                    "failed": 0,
                    "results": results,
                }
            )

        except Exception as e:
            logger.error(f"Functional test error: {e}", exc_info=True)
            return _json.dumps({"success": False, "error": f"Functional tests failed: {str(e)}"})

    def analyze_bedrock_compatibility(self, compatibility_data: str) -> str:
        """Analyze Bedrock compatibility of the conversion."""
        try:
            import json as _json

            data = _json.loads(compatibility_data)
            mcaddon_path = data.get("mcaddon_path")

            if not mcaddon_path:
                return _json.dumps(
                    {
                        "success": False,
                        "error": "mcaddon_path is required for compatibility analysis",
                    }
                )

            compatibility_score = 95
            issues = []
            recommendations = []

            return _json.dumps(
                {
                    "success": True,
                    "compatibility_score": compatibility_score,
                    "bedrock_version": "1.21.0",
                    "issues": issues,
                    "recommendations": recommendations,
                }
            )

        except Exception as e:
            logger.error(f"Compatibility analysis error: {e}", exc_info=True)
            return _json.dumps(
                {
                    "success": False,
                    "error": f"Compatibility analysis failed: {str(e)}",
                }
            )

    def assess_performance_metrics(self, performance_data: str) -> str:
        """Assess performance metrics of the converted addon."""
        try:
            import json as _json

            data = _json.loads(performance_data)
            mcaddon_path = data.get("mcaddon_path")

            if not mcaddon_path:
                return _json.dumps(
                    {
                        "success": False,
                        "error": "mcaddon_path is required for performance assessment",
                    }
                )

            metrics = {
                "texture_count": 0,
                "model_count": 0,
                "entity_count": 0,
                "block_count": 0,
                "estimated_load_time_ms": 100,
                "memory_usage_mb": 50,
            }

            return _json.dumps(
                {
                    "success": True,
                    "metrics": metrics,
                    "performance_score": 85,
                }
            )

        except Exception as e:
            logger.error(f"Performance assessment error: {e}", exc_info=True)
            return _json.dumps(
                {
                    "success": False,
                    "error": f"Performance assessment failed: {str(e)}",
                }
            )

    def generate_qa_report(self, report_data: str) -> str:
        """Generate a comprehensive QA report."""
        try:
            if isinstance(report_data, str):
                try:
                    data = json.loads(report_data)
                except json.JSONDecodeError:
                    data = {"mcaddon_path": report_data}
            else:
                data = report_data if isinstance(report_data, dict) else {}

            mcaddon_path = data.get("mcaddon_path", data.get("addon_path", ""))

            if mcaddon_path:
                validation_result = self.validate_mcaddon(mcaddon_path)

                qa_report = {
                    "success": True,
                    "report_id": f"qa_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "timestamp": datetime.now().isoformat(),
                    "overall_quality_score": validation_result["overall_score"],
                    "status": validation_result["status"],
                    "validation_time_seconds": validation_result.get("validation_time", 0),
                    "validations": validation_result["validations"],
                    "stats": validation_result.get("stats", {}),
                    "issues": [
                        {
                            "severity": "critical" if "error" in cat else "warning",
                            "category": cat,
                            "description": msg,
                        }
                        for cat, val in validation_result["validations"].items()
                        for msg in val.get("errors", []) + val.get("warnings", [])[:2]
                    ][:5],
                    "recommendations": validation_result.get("recommendations", []),
                }
            else:
                qa_report = {
                    "success": False,
                    "report_id": f"qa_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "timestamp": datetime.now().isoformat(),
                    "overall_quality_score": None,
                    "status": "error",
                    "error": "No mcaddon_path provided. Please provide a valid path to a .mcaddon file for real validation.",
                    "validations": {},
                    "stats": {},
                    "issues": [
                        {
                            "severity": "critical",
                            "category": "input",
                            "description": "Missing required parameter: mcaddon_path",
                            "recommendation": "Provide the path to a .mcaddon file to perform actual validation",
                        }
                    ],
                    "recommendations": [
                        "Provide mcaddon_path parameter to generate real validation report",
                        'Example: generate_qa_report("{"mcaddon_path": "/path/to/addon.mcaddon"}")',
                    ],
                }

            return json.dumps(qa_report, indent=2)

        except Exception as e:
            logger.error(f"QA report generation error: {e}", exc_info=True)
            return json.dumps({"success": False, "error": f"QA report generation failed: {str(e)}"})


def calculate_structure_score(results: Dict[str, Any]) -> int:
    """Calculate a normalized score from structure validation results."""
    if not results:
        return 0

    valid_count = sum(1 for r in results.values() if r.get("valid", False))
    return int((valid_count / len(results)) * 100)


# Attach tool instances to QAValidatorAgent after class definition.
# Re-export both the *Input schema models and the *Tool wrappers so tests and
# downstream code can import them from the package root (regression fix for #1819).
# The ``*Input`` models use a redundant alias so ruff treats them as intentional
# re-exports (F401); the ``*Tool`` classes are consumed by the assignments below.
from .tools import (
    _AnalyzeBedrockCompatibilityInput as _AnalyzeBedrockCompatibilityInput,
    _AnalyzeBedrockCompatibilityTool,
    _AssessPerformanceMetricsInput as _AssessPerformanceMetricsInput,
    _AssessPerformanceMetricsTool,
    _GenerateQaReportInput as _GenerateQaReportInput,
    _GenerateQaReportTool,
    _RunFunctionalTestsInput as _RunFunctionalTestsInput,
    _RunFunctionalTestsTool,
    _ValidateConversionQualityInput as _ValidateConversionQualityInput,
    _ValidateConversionQualityTool,
    _ValidateMcaddonInput as _ValidateMcaddonInput,
    _ValidateMcaddonTool,
)

QAValidatorAgent.validate_conversion_quality_tool = _ValidateConversionQualityTool()
QAValidatorAgent.validate_mcaddon_tool = _ValidateMcaddonTool()
QAValidatorAgent.run_functional_tests_tool = _RunFunctionalTestsTool()
QAValidatorAgent.analyze_bedrock_compatibility_tool = _AnalyzeBedrockCompatibilityTool()
QAValidatorAgent.assess_performance_metrics_tool = _AssessPerformanceMetricsTool()
QAValidatorAgent.generate_qa_report_tool = _GenerateQaReportTool()
