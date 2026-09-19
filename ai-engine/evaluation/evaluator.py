"""
Rubric-grounded evaluation engine for conversion quality assessment.

Provides structured evaluation of Java-to-Bedrock Minecraft mod conversions
using verifiable rubric criteria with partial-credit scoring.
"""

import json
import re
from typing import Optional

from evaluation.models import (
    RubricCategory,
    RubricScore,
    RubricResult,
    RewardSignal,
    BEDROCK_CONSTRAINTS,
    BedrockConstraintType,
)


# Rubric definitions with criteria and scoring
RUBRIC_DEFINITIONS: dict[RubricCategory, dict] = {
    RubricCategory.BEHAVIORAL_PRESERVATION: {
        "name": "Behavioral Preservation",
        "description": "Does the converted code preserve the mod's intended behavior?",
        "max_score": 4.0,
        "criteria": [
            "entity_spawning_preserved",
            "block_placement_preserved",
            "item_interaction_preserved",
            "event_handling_preserved",
        ],
        "partial_credits": {
            "all_preserved": 4.0,
            "3_of_4": 3.0,
            "2_of_4": 2.0,
            "1_of_4": 1.0,
            "none_preserved": 0.0,
        },
    },
    RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE: {
        "name": "Bedrock Constraint Compliance",
        "description": "Are Bedrock-specific constraints respected (tick limits, JSON nesting depth, API availability)?",
        "max_score": 3.0,
        "criteria": [
            "tick_rate_respected",
            "json_depth_valid",
            "api_version_compatible",
        ],
        "partial_credits": {
            "all_compliant": 3.0,
            "2_of_3": 2.0,
            "1_of_3": 1.0,
            "none_compliant": 0.0,
        },
    },
    RubricCategory.CODE_QUALITY: {
        "name": "Code Quality",
        "description": "Is the code maintainable and idiomatic Bedrock Scripting?",
        "max_score": 3.0,
        "criteria": [
            "idiomatic_bedrock_script",
            "proper_imports",
            "no_deprecated_apis",
        ],
        "partial_credits": {
            "all_met": 3.0,
            "2_of_3": 2.0,
            "1_of_3": 1.0,
            "none_met": 0.0,
        },
    },
    RubricCategory.STRUCTURAL_VALIDITY: {
        "name": "Structural Validity",
        "description": "Is the output valid JSON and JavaScript that can be parsed and executed?",
        "max_score": 3.0,
        "criteria": [
            "manifest_valid_json",
            "scripts_parseable",
            "behavior_file_structure",
        ],
        "partial_credits": {
            "all_valid": 3.0,
            "2_of_3": 2.0,
            "1_of_3": 1.0,
            "none_valid": 0.0,
        },
    },
}


class BedrockConstraintChecker:
    """Checks Bedrock-specific constraints in converted output."""

    def __init__(self, constraints: dict[BedrockConstraintType, dict] | None = None):
        """Initialize with optional custom constraints."""
        self.constraints = constraints or BEDROCK_CONSTRAINTS

    def check_json_nesting_depth(self, json_str: str) -> tuple[bool, int]:
        """Check if JSON nesting depth exceeds limits.

        Returns (is_valid, max_depth_found).
        """
        try:
            data = json.loads(json_str)
            max_depth = self._compute_json_depth(data)
            limit = self.constraints[BedrockConstraintType.JSON_NESTING_DEPTH].max_value
            return max_depth <= limit, max_depth
        except (json.JSONDecodeError, TypeError):
            return False, 0

    def _compute_json_depth(self, obj, current_depth: int = 0) -> int:
        """Recursively compute maximum JSON nesting depth."""
        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(self._compute_json_depth(v, current_depth + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return current_depth
            return max(self._compute_json_depth(item, current_depth + 1) for item in obj)
        return current_depth

    def check_script_api_version(self, js_code: str) -> tuple[bool, list[str]]:
        """Check if Script API usage is compatible with target version.

        Returns (is_compatible, list_of_issues).
        """
        issues = []

        # Check for API 1.x patterns that don't exist in 2.x
        v1_only_patterns = [
            (r"@minecraft/server\.v1\.?\d*", "v1 API imports are deprecated"),
            (r"\.getBlock\(\)\.setType\(", "Block setType API changed in v2"),
        ]

        for pattern, description in v1_only_patterns:
            if re.search(pattern, js_code):
                issues.append(description)

        # Check for proper v2 imports
        v2_import = re.search(r"@minecraft/server[^\s]*", js_code)
        if not v2_import:
            issues.append("No Script API import found")

        return len(issues) == 0, issues

    def check_tick_rate(self, js_code: str) -> tuple[bool, list[str]]:
        """Check for tick rate violations.

        Returns (is_valid, list_of_violations).
        """
        violations = []

        # Check for blocking operations in tick handlers
        tick_handler_patterns = [
            (
                r"world\.afterEvents\..*\.subscribe\([^)]*\bwhile\b",
                "Blocking while loop in event handler",
            ),
            (
                r"world\.afterEvents\..*\.subscribe\([^)]*\bfor\b\s*\(",
                "Blocking for loop in event handler",
            ),
            (r"setTimeout|setInterval", "setTimeout/setInterval can cause tick issues"),
        ]

        for pattern, description in tick_handler_patterns:
            if re.search(pattern, js_code, re.DOTALL):
                violations.append(description)

        return len(violations) == 0, violations

    def check_event_queue_size(self, js_code: str) -> tuple[bool, str]:
        """Check for event queue size issues.

        Returns (is_valid, warning_message).
        """
        # Count potential event subscriptions
        subscribe_count = len(re.findall(r"\.subscribe\(", js_code))

        if subscribe_count > 100:
            return False, f"High event subscription count: {subscribe_count}"
        return True, ""


class RubricEvaluator:
    """Main evaluator for rubric-grounded conversion quality assessment."""

    def __init__(self, constraint_checker: Optional[BedrockConstraintChecker] = None):
        """Initialize evaluator with optional custom constraint checker."""
        self.constraint_checker = constraint_checker or BedrockConstraintChecker()

    def evaluate(
        self,
        java_source: str,
        bedrock_output: str,
        conversion_id: Optional[str] = None,
    ) -> RubricResult:
        """Evaluate conversion quality against rubrics.

        Args:
            java_source: Original Java source code
            bedrock_output: Converted Bedrock output (may include manifest.json and scripts)
            conversion_id: Optional identifier for this conversion

        Returns:
            RubricResult with per-category scores and overall reward signal
        """
        # Extract components from bedrock output
        manifest, scripts = self._extract_components(bedrock_output)

        # Score each rubric category
        scores = {}

        # 1. Behavioral Preservation
        scores[RubricCategory.BEHAVIORAL_PRESERVATION] = self._score_behavioral_preservation(
            java_source, manifest, scripts
        )

        # 2. Bedrock Constraint Compliance
        scores[RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE] = self._score_constraint_compliance(
            manifest, scripts
        )

        # 3. Code Quality
        scores[RubricCategory.CODE_QUALITY] = self._score_code_quality(scripts)

        # 4. Structural Validity
        scores[RubricCategory.STRUCTURAL_VALIDITY] = self._score_structural_validity(
            manifest, scripts
        )

        # Compute overall score
        overall_score = sum(s.score for s in scores.values())
        overall_max_score = sum(s.max_score for s in scores.values())

        # Build reward signal
        reward_signal = self._build_reward_signal(scores)

        # Generate adjudication notes
        adjudication_notes = self._generate_adjudication_notes(scores)

        return RubricResult(
            conversion_id=conversion_id,
            java_source=java_source,
            bedrock_output=bedrock_output,
            scores=scores,
            overall_score=overall_score,
            overall_max_score=overall_max_score,
            reward_signal=reward_signal,
            adjudication_notes=adjudication_notes,
        )

    def _extract_components(self, bedrock_output: str) -> tuple[Optional[str], list[str]]:
        """Extract manifest.json and script files from bedrock output."""
        manifest = None
        scripts = []

        # Extract JSON blocks
        json_blocks = re.findall(r"```json\s*(.*?)\s*```", bedrock_output, re.DOTALL)
        for block in json_blocks:
            if "format_version" in block or "header" in block or "modules" in block:
                manifest = block.strip()
                break

        # Extract JS blocks
        js_blocks = re.findall(r"```(?:javascript|js)\s*(.*?)\s*```", bedrock_output, re.DOTALL)
        scripts = [b.strip() for b in js_blocks]

        return manifest, scripts

    def _score_behavioral_preservation(
        self, java_source: str, manifest: Optional[str], scripts: list[str]
    ) -> RubricScore:
        """Score behavioral preservation rubric."""
        definition = RUBRIC_DEFINITIONS[RubricCategory.BEHAVIORAL_PRESERVATION]
        evidence = {}
        partial_credits = definition["partial_credits"]

        # Check entity spawning preservation
        java_has_entities = bool(
            re.search(r"@Mod\.Element.*Entity|register.*Entity", java_source, re.IGNORECASE)
            or re.search(r"EntityType|EntitySpawnEvent", java_source)
        )
        bedrock_has_entities = (
            manifest is not None and bool(re.search(r'"id".*"minecraft:', manifest, re.IGNORECASE))
        ) or any("entity" in s.lower() for s in scripts)
        evidence["entity_spawning_preserved"] = bedrock_has_entities if java_has_entities else True

        # Check block placement preservation
        java_has_blocks = bool(
            re.search(r"Block|BlockState|BlockPos", java_source)
            and re.search(r"register|placement", java_source, re.IGNORECASE)
        )
        bedrock_has_blocks = manifest is not None and bool(
            re.search(r'"format_version"|"header"|"modules"', manifest)
        )
        evidence["block_placement_preserved"] = bedrock_has_blocks if java_has_blocks else True

        # Check item interaction preservation
        java_has_items = bool(re.search(r"Item|ItemStack|useItem", java_source, re.IGNORECASE))
        bedrock_has_items = any(
            re.search(r"ItemStack|@minecraft/server.*Item", s, re.IGNORECASE) for s in scripts
        )
        evidence["item_interaction_preserved"] = bedrock_has_items if java_has_items else True

        # Check event handling preservation
        java_has_events = bool(re.search(r"@SubscribeEvent|EventHandler", java_source))
        bedrock_has_events = any(
            re.search(r"\.subscribe\(|afterEvents|beforeEvents", s) for s in scripts
        )
        evidence["event_handling_preserved"] = bedrock_has_events if java_has_events else True

        # Calculate partial credit
        preserved_count = sum(evidence.values())
        if preserved_count == 4:
            score = partial_credits["all_preserved"]
        elif preserved_count == 3:
            score = partial_credits["3_of_4"]
        elif preserved_count == 2:
            score = partial_credits["2_of_4"]
        elif preserved_count == 1:
            score = partial_credits["1_of_4"]
        else:
            score = partial_credits["none_preserved"]

        return RubricScore(
            category=RubricCategory.BEHAVIORAL_PRESERVATION,
            score=score,
            max_score=definition["max_score"],
            evidence=evidence,
            partial_credit_breakdown={
                "preserved_count": float(preserved_count),
                "max_count": 4.0,
            },
            reasoning=f"Behavioral preservation: {preserved_count}/4 criteria met. "
            f"Entity: {evidence['entity_spawning_preserved']}, "
            f"Block: {evidence['block_placement_preserved']}, "
            f"Item: {evidence['item_interaction_preserved']}, "
            f"Event: {evidence['event_handling_preserved']}",
        )

    def _score_constraint_compliance(
        self, manifest: Optional[str], scripts: list[str]
    ) -> RubricScore:
        """Score Bedrock constraint compliance rubric."""
        definition = RUBRIC_DEFINITIONS[RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE]
        evidence = {}
        partial_credits = definition["partial_credits"]

        # Check tick rate compliance
        tick_valid = True
        tick_violations = []
        for script in scripts:
            is_valid, violations = self.constraint_checker.check_tick_rate(script)
            if not is_valid:
                tick_valid = False
                tick_violations.extend(violations)
        evidence["tick_rate_respected"] = tick_valid

        # Check JSON depth
        json_valid = True
        max_depth = 0
        if manifest:
            is_valid, depth = self.constraint_checker.check_json_nesting_depth(manifest)
            json_valid = is_valid
            max_depth = depth
        evidence["json_depth_valid"] = json_valid

        # Check API version compatibility
        api_valid = True
        api_issues = []
        for script in scripts:
            is_valid, issues = self.constraint_checker.check_script_api_version(script)
            if not is_valid:
                api_valid = False
                api_issues.extend(issues)
        evidence["api_version_compatible"] = api_valid

        # Calculate partial credit
        compliant_count = sum(evidence.values())
        if compliant_count == 3:
            score = partial_credits["all_compliant"]
        elif compliant_count == 2:
            score = partial_credits["2_of_3"]
        elif compliant_count == 1:
            score = partial_credits["1_of_3"]
        else:
            score = partial_credits["none_compliant"]

        reasoning_parts = [
            f"Constraint compliance: {compliant_count}/3 criteria met.",
        ]
        if tick_violations:
            reasoning_parts.append(f"Tick violations: {', '.join(tick_violations[:2])}")
        if not json_valid:
            reasoning_parts.append(f"JSON depth exceeded (max: {max_depth})")
        if api_issues:
            reasoning_parts.append(f"API issues: {', '.join(api_issues[:2])}")

        return RubricScore(
            category=RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE,
            score=score,
            max_score=definition["max_score"],
            evidence=evidence,
            partial_credit_breakdown={
                "compliant_count": float(compliant_count),
                "max_count": 3.0,
            },
            reasoning=" ".join(reasoning_parts),
        )

    def _score_code_quality(self, scripts: list[str]) -> RubricScore:
        """Score code quality rubric."""
        definition = RUBRIC_DEFINITIONS[RubricCategory.CODE_QUALITY]
        evidence = {}
        partial_credits = definition["partial_credits"]

        # Check for idiomatic Bedrock Script usage
        has_imports = any(re.search(r"import.*from.*@minecraft/server", s) for s in scripts)
        has_world_access = any(
            re.search(r"world\.(afterEvents|beforeEvents|getBlock|getDimension)", s)
            for s in scripts
        )
        evidence["idiomatic_bedrock_script"] = has_imports and has_world_access

        # Check proper imports
        proper_imports = all(
            re.search(r"@minecraft/server", s) for s in scripts if "import" in s.lower()
        )
        evidence["proper_imports"] = proper_imports

        # Check no deprecated APIs
        deprecated_patterns = [
            r"minecraft\.server\.v1",
            r"\.setType\(.*\)\s*\.",  # Old block type setting pattern
            r"player\.sendMessage\(\s*['\"]",
        ]
        has_deprecated = any(
            re.search(pattern, s, re.IGNORECASE) for pattern in deprecated_patterns for s in scripts
        )
        evidence["no_deprecated_apis"] = not has_deprecated

        # Calculate partial credit
        met_count = sum(evidence.values())
        if met_count == 3:
            score = partial_credits["all_met"]
        elif met_count == 2:
            score = partial_credits["2_of_3"]
        elif met_count == 1:
            score = partial_credits["1_of_3"]
        else:
            score = partial_credits["none_met"]

        return RubricScore(
            category=RubricCategory.CODE_QUALITY,
            score=score,
            max_score=definition["max_score"],
            evidence=evidence,
            partial_credit_breakdown={"criteria_met": float(met_count), "max_count": 3.0},
            reasoning=f"Code quality: {met_count}/3 criteria met. "
            f"Idiomatic: {evidence['idiomatic_bedrock_script']}, "
            f"Proper imports: {evidence['proper_imports']}, "
            f"No deprecated: {evidence['no_deprecated_apis']}",
        )

    def _score_structural_validity(
        self, manifest: Optional[str], scripts: list[str]
    ) -> RubricScore:
        """Score structural validity rubric."""
        definition = RUBRIC_DEFINITIONS[RubricCategory.STRUCTURAL_VALIDITY]
        evidence = {}
        partial_credits = definition["partial_credits"]

        # Check manifest is valid JSON
        manifest_valid = False
        if manifest:
            try:
                data = json.loads(manifest)
                manifest_valid = "format_version" in data and "header" in data
            except json.JSONDecodeError:
                pass
        evidence["manifest_valid_json"] = manifest_valid

        # Check scripts are parseable (basic syntax check)
        scripts_parseable = True
        for script in scripts:
            # Check for balanced braces
            open_braces = script.count("{")
            close_braces = script.count("}")
            if open_braces != close_braces:
                scripts_parseable = False
                break
            # Check for import statements not followed by semicolons
            if re.search(r"^import\s+.*[^;]$", script, re.MULTILINE):
                scripts_parseable = False
                break
        evidence["scripts_parseable"] = scripts_parseable

        # Check behavior file structure (entity/component definitions)
        has_behavior = manifest is not None and (
            "entity" in manifest.lower() or "component" in manifest.lower()
        )
        evidence["behavior_file_structure"] = has_behavior

        # Calculate partial credit
        valid_count = sum(evidence.values())
        if valid_count == 3:
            score = partial_credits["all_valid"]
        elif valid_count == 2:
            score = partial_credits["2_of_3"]
        elif valid_count == 1:
            score = partial_credits["1_of_3"]
        else:
            score = partial_credits["none_valid"]

        return RubricScore(
            category=RubricCategory.STRUCTURAL_VALIDITY,
            score=score,
            max_score=definition["max_score"],
            evidence=evidence,
            partial_credit_breakdown={"valid_count": float(valid_count), "max_count": 3.0},
            reasoning=f"Structural validity: {valid_count}/3 criteria met. "
            f"Manifest valid: {evidence['manifest_valid_json']}, "
            f"Scripts parseable: {evidence['scripts_parseable']}, "
            f"Behavior structure: {evidence['behavior_file_structure']}",
        )

    def _build_reward_signal(self, scores: dict[RubricCategory, RubricScore]) -> RewardSignal:
        """Build RL reward signal from rubric scores."""
        partial_credits = {}

        behavioral = scores[RubricCategory.BEHAVIORAL_PRESERVATION]
        constraint = scores[RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE]
        quality = scores[RubricCategory.CODE_QUALITY]
        structural = scores[RubricCategory.STRUCTURAL_VALIDITY]

        # Add partial credits for each category
        for category, score in scores.items():
            partial_credits[category.value] = score.score

        # Compute total reward
        total = behavioral.score + constraint.score + quality.score + structural.score

        # Collect penalty reasons
        penalty_reasons = []
        if behavioral.score < behavioral.max_score:
            if behavioral.partial_credit_breakdown.get("preserved_count", 4) < 2:
                penalty_reasons.append("Low behavioral preservation")
        if constraint.score < constraint.max_score:
            if not all(constraint.evidence.values()):
                failed = [k for k, v in constraint.evidence.items() if not v]
                penalty_reasons.append(f"Constraint failures: {', '.join(failed)}")
        if structural.score < structural.max_score:
            if structural.evidence.get("manifest_valid_json") is False:
                penalty_reasons.append("Invalid manifest JSON")

        return RewardSignal(
            total_reward=total,
            behavioral_preservation=behavioral.normalized_score,
            constraint_compliance=constraint.normalized_score,
            code_quality=quality.normalized_score,
            structural_validity=structural.normalized_score,
            partial_credits=partial_credits,
            penalty_reasons=penalty_reasons,
        )

    def _generate_adjudication_notes(self, scores: dict[RubricCategory, RubricScore]) -> str:
        """Generate human-readable adjudication notes."""
        notes = []

        for category, score in scores.items():
            if score.score < score.max_score:
                notes.append(
                    f"[{category.value}] Partial credit: {score.score}/{score.max_score}. "
                    f"Reason: {score.reasoning}"
                )
            else:
                notes.append(f"[{category.value}] Full credit achieved.")

        return " | ".join(notes)
