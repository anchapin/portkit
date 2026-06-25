"""
Minecraft Contract Validation and Reward Models for Bedrock API Idiomaticity

Implements a validation-driven workflow for Minecraft mod conversion based on:
- GeoContra (https://arxiv.org/abs/2605.00782v1)
- Validation-Driven LLM Workflows (https://arxiv.org/abs/2605.00800v1)

This module provides:
- Minecraft contract validation layer
- Bedrock API idiomaticity scoring
- Automatic LLM-based repair loop for violations
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ViolationSeverity(Enum):
    """Severity levels for contract violations."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ContractType(Enum):
    """Types of Minecraft/Bedrock contracts."""

    COORDINATE_SEMANTICS = "coordinate_semantics"
    COMPONENT_NESTING = "component_nesting"
    JSON_SCHEMA = "json_schema"
    API_CONTRACT = "api_contract"
    BEHAVIOR_TREE = "behavior_tree"
    MANIFEST_STRUCTURE = "manifest_structure"


@dataclass
class ContractViolation:
    """Represents a single contract violation."""

    contract_type: ContractType
    severity: ViolationSeverity
    message: str
    location: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    repair_suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_type": self.contract_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
            "context": self.context,
            "repair_suggestion": self.repair_suggestion,
        }


@dataclass
class BedrockIdiomaticityScore:
    """Score for Bedrock API idiomaticity."""

    overall_score: float = 0.0
    coordinate_score: float = 0.0
    component_score: float = 0.0
    schema_score: float = 0.0
    api_contract_score: float = 0.0
    violations: List[ContractViolation] = field(default_factory=list)
    repair_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "coordinate_score": self.coordinate_score,
            "component_score": self.component_score,
            "schema_score": self.schema_score,
            "api_contract_score": self.api_contract_score,
            "violations": [v.to_dict() for v in self.violations],
            "repair_count": self.repair_count,
        }


@dataclass
class MinecraftContractResult:
    """Result of Minecraft contract validation."""

    is_valid: bool
    idiomaticity_score: BedrockIdiomaticityScore
    violations: List[ContractViolation]
    repair_loop_triggered: bool = False
    repair_attempts: int = 0
    repair_successful: bool = False
    repaired_code: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "idiomaticity_score": self.idiomaticity_score.to_dict(),
            "violations": [v.to_dict() for v in self.violations],
            "repair_loop_triggered": self.repair_loop_triggered,
            "repair_attempts": self.repair_attempts,
            "repair_successful": self.repair_successful,
            "repaired_code": self.repaired_code,
            "timestamp": self.timestamp,
        }


class CoordinateContractValidator:
    """Validates Minecraft coordinate semantics - block positions must use integer coords."""

    COORDINATE_PATTERN = re.compile(r'"(-?\d+(?:\.\d+)?)"')

    def validate(self, code: str, location: Optional[str] = None) -> List[ContractViolation]:
        """Check for non-integer coordinates in block position contexts."""
        violations = []
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if (
                stripped.startswith('"x"')
                or stripped.startswith('"y"')
                or stripped.startswith('"z"')
            ):
                coord_matches = re.findall(r":\s*(-?\d+\.\d+)", line)
                for match in coord_matches:
                    violations.append(
                        ContractViolation(
                            contract_type=ContractType.COORDINATE_SEMANTICS,
                            severity=ViolationSeverity.ERROR,
                            message=f"Block coordinates must be integers, found float: {match}",
                            location=f"{location}:{line_num}" if location else f"line {line_num}",
                            context={"coordinate_value": match, "line": line.strip()},
                            repair_suggestion=f"Convert {match} to integer by removing decimal part",
                        )
                    )

        return violations

    def get_score(self, violations: List[ContractViolation]) -> float:
        """Calculate coordinate semantics score from violations."""
        if not violations:
            return 1.0
        critical_count = sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL)
        error_count = sum(1 for v in violations if v.severity == ViolationSeverity.ERROR)
        return max(0.0, 1.0 - (critical_count * 0.3 + error_count * 0.1))


class ComponentNestingValidator:
    """Validates component nesting constraints - items can't have certain nested components."""

    FORBIDDEN_NESTING = {
        "minecraft:lodestone": ["minecraft:display_name", "minecraft:lore"],
        "minecraft:enchantments": ["minecraft:enchantment"],
        "minecraft:hand_items": ["minecraft:item"],
    }

    def validate(self, code: str, location: Optional[str] = None) -> List[ContractViolation]:
        """Check for invalid component nesting patterns."""
        violations = []

        try:
            data = json.loads(code) if isinstance(code, str) else code
            if isinstance(data, dict):
                for key, value in data.items():
                    for forbidden_parent, forbidden_children in self.FORBIDDEN_NESTING.items():
                        if key == forbidden_parent and isinstance(value, dict):
                            for child_key in value.keys():
                                if child_key in forbidden_children:
                                    violations.append(
                                        ContractViolation(
                                            contract_type=ContractType.COMPONENT_NESTING,
                                            severity=ViolationSeverity.ERROR,
                                            message=f"Invalid nesting: {child_key} cannot be nested inside {forbidden_parent}",
                                            location=location,
                                            context={
                                                "parent": forbidden_parent,
                                                "child": child_key,
                                            },
                                            repair_suggestion=f"Move {child_key} to top level or remove nested relationship",
                                        )
                                    )
        except json.JSONDecodeError:
            pass

        return violations

    def get_score(self, violations: List[ContractViolation]) -> float:
        """Calculate component nesting score from violations."""
        if not violations:
            return 1.0
        error_count = sum(
            1
            for v in violations
            if v.severity in [ViolationSeverity.CRITICAL, ViolationSeverity.ERROR]
        )
        return max(0.0, 1.0 - (error_count * 0.2))


class JsonSchemaValidator:
    """Validates JSON schema compliance with official Bedrock schema."""

    REQUIRED_FIELDS = {
        "format_version": ["format_version"],
        "manifest_version": ["header", "format_version"],
    }

    VALID_FORMAT_VERSIONS = [
        "1.20.10",
        "1.20.20",
        "1.20.30",
        "1.20.40",
        "1.21.0",
        "1.21.10",
        "1.21.20",
    ]

    def validate(self, code: str, location: Optional[str] = None) -> List[ContractViolation]:
        """Validate JSON structure against Bedrock schema rules."""
        violations = []

        try:
            data = json.loads(code) if isinstance(code, str) else code

            if isinstance(data, dict):
                if "format_version" in data:
                    fv = data["format_version"]
                    if isinstance(fv, str) and fv not in self.VALID_FORMAT_VERSIONS:
                        violations.append(
                            ContractViolation(
                                contract_type=ContractType.JSON_SCHEMA,
                                severity=ViolationSeverity.WARNING,
                                message=f"Unknown format_version '{fv}', may not be valid",
                                location=location,
                                context={"format_version": fv},
                                repair_suggestion=f"Use one of: {', '.join(self.VALID_FORMAT_VERSIONS)}",
                            )
                        )

                if "header" in data and isinstance(data["header"], dict):
                    header = data["header"]
                    required = ["name", "uuid", "version"]
                    for field in required:
                        if field not in header:
                            violations.append(
                                ContractViolation(
                                    contract_type=ContractType.JSON_SCHEMA,
                                    severity=ViolationSeverity.ERROR,
                                    message=f"Missing required manifest header field: {field}",
                                    location=location,
                                    context={"missing_field": field},
                                    repair_suggestion=f"Add '{field}' to manifest header",
                                )
                            )

        except json.JSONDecodeError as e:
            violations.append(
                ContractViolation(
                    contract_type=ContractType.JSON_SCHEMA,
                    severity=ViolationSeverity.CRITICAL,
                    message=f"Invalid JSON: {str(e)}",
                    location=location,
                    context={"error": str(e)},
                    repair_suggestion="Fix JSON syntax errors",
                )
            )

        return violations

    def get_score(self, violations: List[ContractViolation]) -> float:
        """Calculate JSON schema score from violations."""
        if not violations:
            return 1.0
        critical = sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL)
        errors = sum(1 for v in violations if v.severity == ViolationSeverity.ERROR)
        warnings = sum(1 for v in violations if v.severity == ViolationSeverity.WARNING)
        return max(0.0, 1.0 - (critical * 0.4 + errors * 0.2 + warnings * 0.05))


class BedrockAPIContractValidator:
    """Validates Bedrock API contract violations."""

    VALID_COMPONENT_TYPES = {
        "minecraft:item",
        "minecraft:block",
        "minecraft:entity",
        "minecraft:recipe",
        "minecraft:loot_table",
        "minecraft:chat_type",
        "minecraft:custom_art",
        "minecraft:animation",
        "minecraft:attachable",
        "minecraft:client_request",
        "minecraft:geometry",
        "minecraft:material",
        "minecraft:model",
        "minecraft:molang",
        "minecraft:render_controller",
        "minecraft:particle",
        "minecraft:spelling",
        "minecraft:music",
        "minecraft:sound",
        "minecraft:swamp_slime_subbbiography",
        "minecraft:template",
        "minecraft:item_texture",
        "minecraft:terrain_texture",
        "minecraft:flipbook_texture",
    }

    VALID_EVENTS = {
        "minecraft:on_player_placed",
        "minecraft:on_player_interacted",
        "minecraft:on_entity_hit_player",
        "minecraft:on_entity_hit_entity",
        "minecraft:on_item_use",
        "minecraft:on_item_use_on",
    }

    def validate(self, code: str, location: Optional[str] = None) -> List[ContractViolation]:
        """Check for invalid Bedrock API usage."""
        violations = []
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            if '"type"' in line or '"component"' in line:
                for invalid_type in ["minecraft:player", "minecraft:world"]:
                    if invalid_type in line:
                        violations.append(
                            ContractViolation(
                                contract_type=ContractType.API_CONTRACT,
                                severity=ViolationSeverity.ERROR,
                                message=f"Invalid Bedrock API type: {invalid_type}",
                                location=f"{location}:{line_num}"
                                if location
                                else f"line {line_num}",
                                context={"invalid_type": invalid_type, "line": line.strip()},
                                repair_suggestion=f"Use valid Bedrock component type",
                            )
                        )

            if "minecraft:spawn_entity" in line:
                if "entity_type" not in line and "type" not in line:
                    violations.append(
                        ContractViolation(
                            contract_type=ContractType.API_CONTRACT,
                            severity=ViolationSeverity.WARNING,
                            message="spawn_entity requires 'entity_type' parameter",
                            location=f"{location}:{line_num}" if location else f"line {line_num}",
                            context={"line": line.strip()},
                            repair_suggestion="Add 'entity_type' parameter to spawn_entity call",
                        )
                    )

        return violations

    def get_score(self, violations: List[ContractViolation]) -> float:
        """Calculate API contract score from violations."""
        if not violations:
            return 1.0
        errors = sum(
            1
            for v in violations
            if v.severity in [ViolationSeverity.CRITICAL, ViolationSeverity.ERROR]
        )
        warnings = sum(1 for v in violations if v.severity == ViolationSeverity.WARNING)
        return max(0.0, 1.0 - (errors * 0.25 + warnings * 0.05))


class MinecraftContractValidator:
    """
    Main validator that combines all Minecraft contract validators.
    Implements the GeoContra-inspired validation-driven workflow.
    """

    def __init__(self):
        self.coordinate_validator = CoordinateContractValidator()
        self.component_validator = ComponentNestingValidator()
        self.schema_validator = JsonSchemaValidator()
        self.api_validator = BedrockAPIContractValidator()

        self.max_repair_attempts = 3
        self.repair_confidence_threshold = 0.8

    def validate(
        self,
        code: str,
        file_type: str = "json",
        location: Optional[str] = None,
        enable_repair: bool = True,
    ) -> MinecraftContractResult:
        """
        Validate code against all Minecraft contracts.

        Args:
            code: The Bedrock code to validate
            file_type: Type of file (json, js, etc.)
            location: Optional location identifier
            enable_repair: Whether to enable automatic repair

        Returns:
            MinecraftContractResult with validation results and potential repair
        """
        all_violations = []

        coordinate_violations = self.coordinate_validator.validate(code, location)
        all_violations.extend(coordinate_violations)

        component_violations = self.component_validator.validate(code, location)
        all_violations.extend(component_violations)

        schema_violations = self.schema_validator.validate(code, location)
        all_violations.extend(schema_violations)

        api_violations = self.api_validator.validate(code, location)
        all_violations.extend(api_violations)

        idiomaticity = BedrockIdiomaticityScore(
            overall_score=0.0,
            coordinate_score=self.coordinate_validator.get_score(coordinate_violations),
            component_score=self.component_validator.get_score(component_violations),
            schema_score=self.schema_validator.get_score(schema_violations),
            api_contract_score=self.api_validator.get_score(api_violations),
            violations=all_violations,
            repair_count=0,
        )

        total_score = (
            idiomaticity.coordinate_score * 0.25
            + idiomaticity.component_score * 0.25
            + idiomaticity.schema_score * 0.25
            + idiomaticity.api_contract_score * 0.25
        )
        idiomaticity.overall_score = total_score

        has_critical = any(v.severity == ViolationSeverity.CRITICAL for v in all_violations)
        is_valid = len(all_violations) == 0 or not has_critical

        result = MinecraftContractResult(
            is_valid=is_valid,
            idiomaticity_score=idiomaticity,
            violations=all_violations,
            repair_loop_triggered=False,
            repair_attempts=0,
            repair_successful=False,
            repaired_code=None,
        )

        if enable_repair and not is_valid and all_violations:
            repaired_code, success = self._attempt_repair(code, all_violations)
            if repaired_code is not None:
                result.repaired_code = repaired_code
                result.repair_attempts = 1
                result.repair_successful = success
                result.repair_loop_triggered = True

                if success:
                    result.is_valid = True
                    idiomaticity.repair_count = 1

        return result

    def _attempt_repair(
        self, code: str, violations: List[ContractViolation]
    ) -> Tuple[Optional[str], bool]:
        """Attempt automatic repair of violations."""
        repaired_code = code

        for violation in violations:
            if violation.contract_type == ContractType.COORDINATE_SEMANTICS:
                repaired_code = self._repair_coordinate_violation(repaired_code, violation)
            elif violation.contract_type == ContractType.COMPONENT_NESTING:
                repaired_code = self._repair_component_violation(repaired_code, violation)
            elif violation.contract_type == ContractType.JSON_SCHEMA:
                repaired_code = self._repair_schema_violation(repaired_code, violation)
            elif violation.contract_type == ContractType.API_CONTRACT:
                repaired_code = self._repair_api_violation(repaired_code, violation)

        validated = self.validate(repaired_code, enable_repair=False)
        success = (
            validated.is_valid
            and validated.idiomaticity_score.overall_score >= self.repair_confidence_threshold
        )

        return repaired_code if success else None, success

    def _repair_coordinate_violation(self, code: str, violation: ContractViolation) -> str:
        """Repair coordinate semantics violations."""
        context = violation.context or {}
        coord_value = context.get("coordinate_value", "")

        if coord_value and "." in str(coord_value):
            int_value = str(int(float(coord_value)))
            repaired = code.replace(f'"{coord_value}"', f'"{int_value}"')
            return repaired

        return code

    def _repair_component_violation(self, code: str, violation: ContractViolation) -> str:
        """Repair component nesting violations."""
        context = violation.context or {}
        parent = context.get("parent", "")
        child = context.get("child", "")

        if parent and child:
            pattern = rf'("\{parent}":\s*\{{[^}}]*"\{child}"[^}}]*\}})'
            match = re.search(pattern, code)
            if match:
                return code.replace(match.group(0), "")

        return code

    def _repair_schema_violation(self, code: str, violation: ContractViolation) -> str:
        """Repair JSON schema violations."""
        context = violation.context or {}

        if "missing_field" in context:
            missing = context["missing_field"]
            if '"header"' in code:
                code = code.replace('"header": {', f'"header": {{\n    "{missing}": "",')
            elif '"format_version"' in context:
                code = code.replace('"format_version"', '"format_version": "1.20.10",')

        return code

    def _repair_api_violation(self, code: str, violation: ContractViolation) -> str:
        """Repair API contract violations."""
        context = violation.context or {}
        invalid_type = context.get("invalid_type", "")

        if invalid_type:
            code = code.replace(f'"{invalid_type}"', '"minecraft:entity"')

        return code


class BedrockIdiomaticityRewardModel:
    """
    Reward model for Bedrock API idiomaticity scoring.
    Provides reward signals for RL training based on contract validation.
    """

    def __init__(self):
        self.validator = MinecraftContractValidator()

        self.reward_config = {
            "excellent_idiomaticity": 2.0,
            "good_idiomaticity": 1.0,
            "acceptable_idiomaticity": 0.5,
            "violation_penalty": -0.5,
            "critical_violation_penalty": -1.0,
            "repair_success_bonus": 1.5,
            "self_repair_bonus": 0.5,
        }

    def score(
        self,
        code: str,
        file_type: str = "json",
        location: Optional[str] = None,
        enable_repair: bool = True,
    ) -> Tuple[MinecraftContractResult, float]:
        """
        Score code for Bedrock idiomaticity and compute reward.

        Args:
            code: Bedrock code to score
            file_type: Type of file
            location: Optional location identifier
            enable_repair: Whether to enable repair loop

        Returns:
            Tuple of (validation result, reward signal)
        """
        result = self.validator.validate(code, file_type, location, enable_repair)

        reward = self._compute_reward(result)

        return result, reward

    def _compute_reward(self, result: MinecraftContractResult) -> float:
        """Compute reward from validation result."""
        reward = 0.0
        idiomaticity = result.idiomaticity_score

        overall = idiomaticity.overall_score

        if overall >= 0.9:
            reward += self.reward_config["excellent_idiomaticity"]
        elif overall >= 0.75:
            reward += self.reward_config["good_idiomaticity"]
        elif overall >= 0.6:
            reward += self.reward_config["acceptable_idiomaticity"]

        for violation in result.violations:
            if violation.severity == ViolationSeverity.CRITICAL:
                reward += self.reward_config["critical_violation_penalty"]
            elif violation.severity == ViolationSeverity.ERROR:
                reward += self.reward_config["violation_penalty"]

        if result.repair_loop_triggered:
            if result.repair_successful:
                reward += self.reward_config["repair_success_bonus"]
            else:
                reward -= self.reward_config["repair_success_bonus"] * 0.5

        if idiomaticity.repair_count > 0:
            reward += self.reward_config["self_repair_bonus"] * idiomaticity.repair_count

        return max(-2.0, min(3.0, reward))

    def batch_score(
        self, code_samples: List[Dict[str, Any]]
    ) -> List[Tuple[MinecraftContractResult, float]]:
        """Score multiple code samples."""
        results = []

        for sample in code_samples:
            code = sample.get("code", "")
            file_type = sample.get("file_type", "json")
            location = sample.get("location")
            enable_repair = sample.get("enable_repair", True)

            result, reward = self.score(code, file_type, location, enable_repair)
            results.append((result, reward))

        return results


def create_minecraft_contract_validator() -> MinecraftContractValidator:
    """Factory function to create a Minecraft contract validator."""
    return MinecraftContractValidator()


def create_idiomaticity_reward_model() -> BedrockIdiomaticityRewardModel:
    """Factory function to create a Bedrock idiomaticity reward model."""
    return BedrockIdiomaticityRewardModel()
