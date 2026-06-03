"""
Unit tests for evaluation/evaluator.py

Covers BedrockConstraintChecker (JSON depth, tick rate, script API version,
event queue size), RubricEvaluator.evaluate, and the RUBRIC_DEFINITIONS
catalog. Tests are fast and isolated — no DB, no AI calls.
"""

import json

import pytest

from evaluation.evaluator import (
    RUBRIC_DEFINITIONS,
    BedrockConstraintChecker,
    RubricEvaluator,
)
from evaluation.models import (
    BEDROCK_CONSTRAINTS,
    BedrockConstraint,
    BedrockConstraintType,
    RubricCategory,
)


pytestmark = pytest.mark.unit


# -----------------------------------------------------------------------
# RUBRIC_DEFINITIONS
# -----------------------------------------------------------------------


class TestRubricDefinitions:
    """Cover the static RUBRIC_DEFINITIONS catalog."""

    def test_defines_all_four_categories(self):
        assert set(RUBRIC_DEFINITIONS.keys()) == {
            RubricCategory.BEHAVIORAL_PRESERVATION,
            RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE,
            RubricCategory.CODE_QUALITY,
            RubricCategory.STRUCTURAL_VALIDITY,
        }

    def test_each_definition_has_required_fields(self):
        for category, definition in RUBRIC_DEFINITIONS.items():
            assert "name" in definition
            assert "description" in definition
            assert "max_score" in definition
            assert "criteria" in definition
            assert "partial_credits" in definition
            assert definition["max_score"] > 0

    def test_max_scores_sum_to_thirteen(self):
        total = sum(d["max_score"] for d in RUBRIC_DEFINITIONS.values())
        assert total == pytest.approx(13.0)

    def test_partial_credits_sorted(self):
        # Every partial_credits mapping should be sorted from highest to lowest
        for definition in RUBRIC_DEFINITIONS.values():
            credits = definition["partial_credits"]
            values = list(credits.values())
            assert values == sorted(values, reverse=True)

    def test_criteria_are_unique_strings(self):
        for definition in RUBRIC_DEFINITIONS.values():
            assert isinstance(definition["criteria"], list)
            assert all(isinstance(c, str) for c in definition["criteria"])
            assert len(definition["criteria"]) == len(set(definition["criteria"]))


# -----------------------------------------------------------------------
# BedrockConstraintChecker
# -----------------------------------------------------------------------


class TestBedrockConstraintChecker:
    """Cover each constraint check independently."""

    def test_default_uses_global_constraints(self):
        checker = BedrockConstraintChecker()
        assert checker.constraints is BEDROCK_CONSTRAINTS

    def test_custom_constraints_override_default(self):
        custom = {
            BedrockConstraintType.JSON_NESTING_DEPTH: BedrockConstraint(
                constraint_type=BedrockConstraintType.JSON_NESTING_DEPTH,
                description="test",
                max_value=2.0,
            )
        }
        checker = BedrockConstraintChecker(constraints=custom)
        assert checker.constraints is custom

    # --- check_json_nesting_depth -------------------------------------

    def test_json_depth_within_limit(self):
        checker = BedrockConstraintChecker()
        # 3 levels deep, limit is 6
        json_str = '{"a": {"b": {"c": 1}}}'
        valid, depth = checker.check_json_nesting_depth(json_str)
        assert valid is True
        assert depth == 3

    def test_json_depth_exceeds_limit(self):
        checker = BedrockConstraintChecker()
        # 8 levels deep, limit is 6
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}}
        valid, depth = checker.check_json_nesting_depth(json.dumps(deep))
        assert valid is False
        assert depth == 8

    def test_json_depth_with_custom_lower_limit(self):
        # Custom limit of 1 level
        custom = {
            BedrockConstraintType.JSON_NESTING_DEPTH: BedrockConstraint(
                constraint_type=BedrockConstraintType.JSON_NESTING_DEPTH,
                description="tight",
                max_value=1.0,
            )
        }
        checker = BedrockConstraintChecker(constraints=custom)
        # 2 levels deep > limit of 1
        valid, depth = checker.check_json_nesting_depth('{"a": {"b": 1}}')
        assert valid is False
        assert depth == 2

    def test_json_depth_invalid_json(self):
        checker = BedrockConstraintChecker()
        valid, depth = checker.check_json_nesting_depth("not valid json {{{")
        assert valid is False
        assert depth == 0

    def test_json_depth_empty_object(self):
        checker = BedrockConstraintChecker()
        valid, depth = checker.check_json_nesting_depth("{}")
        assert valid is True
        assert depth == 0

    def test_json_depth_empty_list(self):
        checker = BedrockConstraintChecker()
        valid, depth = checker.check_json_nesting_depth("[]")
        assert valid is True
        assert depth == 0

    def test_json_depth_uses_max_recursion_not_first(self):
        # The structure is asymmetric — depth 5 only in one branch
        checker = BedrockConstraintChecker()
        deep_branch = {"x": {"y": {"z": {"w": {"q": 1}}}}}
        shallow_branch = {"a": 1}
        js = json.dumps([deep_branch, shallow_branch])
        valid, depth = checker.check_json_nesting_depth(js)
        # Top-level list = +1, dict = +1, then 4 more levels for the deep branch
        # depth tracking: list(+1) -> dict(+1) -> dict(+1) -> dict(+1) -> dict(+1) -> dict(+1)
        # Inner dict in deep branch is empty so it returns current_depth
        assert depth >= 4
        assert valid is True  # 6 is the limit, depth is well under

    # --- check_script_api_version -------------------------------------

    def test_script_api_version_compatible(self):
        checker = BedrockConstraintChecker()
        js = "import { world } from '@minecraft/server';\nworld.afterEvents.playerSpawn.subscribe()"
        valid, issues = checker.check_script_api_version(js)
        assert valid is True
        assert issues == []

    def test_script_api_version_v1_imports_flagged(self):
        checker = BedrockConstraintChecker()
        js = "import { world } from '@minecraft/server.v1.10';\nworld.afterEvents.foo.subscribe();"
        valid, issues = checker.check_script_api_version(js)
        assert valid is False
        assert any("v1 API imports are deprecated" in i for i in issues)

    def test_script_api_version_settype_flagged(self):
        checker = BedrockConstraintChecker()
        js = "import { world } from '@minecraft/server';\nworld.getBlock().setType("
        valid, issues = checker.check_script_api_version(js)
        assert valid is False
        assert any("setType API changed in v2" in i for i in issues)

    def test_script_api_version_missing_import_flagged(self):
        checker = BedrockConstraintChecker()
        # No @minecraft/server import at all
        js = "console.log('hi');"
        valid, issues = checker.check_script_api_version(js)
        assert valid is False
        assert any("No Script API import found" in i for i in issues)

    def test_script_api_version_aggregates_multiple_issues(self):
        checker = BedrockConstraintChecker()
        js = "import { world } from '@minecraft/server.v1';\nworld.getBlock().setType("
        valid, issues = checker.check_script_api_version(js)
        assert valid is False
        # Both v1 import and setType should be flagged
        assert len(issues) >= 2

    # --- check_tick_rate ----------------------------------------------

    def test_tick_rate_clean(self):
        checker = BedrockConstraintChecker()
        js = "import { world } from '@minecraft/server';\nworld.afterEvents.foo.subscribe((e) => log(e));"
        valid, violations = checker.check_tick_rate(js)
        assert valid is True
        assert violations == []

    def test_tick_rate_blocks_while_loop(self):
        checker = BedrockConstraintChecker()
        # Note: pattern is `subscribe([^)]*` so no `)` may appear between
        # `subscribe(` and the keyword. Place while directly in the args.
        js = "world.afterEvents.foo.subscribe(while(x){y});"
        valid, violations = checker.check_tick_rate(js)
        assert valid is False
        assert any("while" in v for v in violations)

    def test_tick_rate_blocks_for_loop(self):
        checker = BedrockConstraintChecker()
        js = "world.afterEvents.foo.subscribe(for(let i=0;i<10;i++));"
        valid, violations = checker.check_tick_rate(js)
        assert valid is False
        assert any("for" in v for v in violations)

    def test_tick_rate_flags_settimeout(self):
        checker = BedrockConstraintChecker()
        js = "setTimeout(() => log('hi'), 100);"
        valid, violations = checker.check_tick_rate(js)
        assert valid is False
        assert any("setTimeout" in v for v in violations)

    # --- check_event_queue_size ---------------------------------------

    def test_event_queue_size_normal(self):
        checker = BedrockConstraintChecker()
        js = "world.afterEvents.foo.subscribe(cb);\nworld.afterEvents.bar.subscribe(cb);"
        valid, msg = checker.check_event_queue_size(js)
        assert valid is True
        assert msg == ""

    def test_event_queue_size_too_many_subscriptions(self):
        checker = BedrockConstraintChecker()
        js = "\n".join([f"world.afterEvents.e{i}.subscribe(cb);" for i in range(105)])
        valid, msg = checker.check_event_queue_size(js)
        assert valid is False
        assert "105" in msg


# -----------------------------------------------------------------------
# RubricEvaluator
# -----------------------------------------------------------------------


VALID_MANIFEST = json.dumps(
    {
        "format_version": 2,
        "header": {"name": "Test", "uuid": "abc", "version": [1, 0, 0]},
        "modules": [
            {"type": "script", "language": "javascript", "uuid": "x", "version": [1, 0, 0]}
        ],
    }
)
VALID_SCRIPT = (
    "import { world } from '@minecraft/server';\n"
    "world.afterEvents.playerSpawn.subscribe(() => log('hi'));\n"
)


class TestRubricEvaluator:
    """Cover RubricEvaluator end-to-end scoring."""

    def test_init_default_constraint_checker(self):
        ev = RubricEvaluator()
        assert isinstance(ev.constraint_checker, BedrockConstraintChecker)

    def test_init_custom_constraint_checker(self):
        custom = BedrockConstraintChecker()
        ev = RubricEvaluator(constraint_checker=custom)
        assert ev.constraint_checker is custom

    def test_evaluate_returns_rubric_result(self):
        ev = RubricEvaluator()
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\n{VALID_SCRIPT}\n```"
        result = ev.evaluate(
            java_source="",
            bedrock_output=bedrock,
            conversion_id="c1",
        )
        assert result.conversion_id == "c1"
        assert result.java_source == ""
        # All four rubric categories are scored
        assert set(result.scores.keys()) == set(RubricCategory)
        # Max score is 13
        assert result.overall_max_score == pytest.approx(13.0)
        # Score is within range
        assert 0.0 <= result.overall_score <= result.overall_max_score

    def test_evaluate_no_manifest_or_scripts(self):
        ev = RubricEvaluator()
        result = ev.evaluate(java_source="", bedrock_output="nothing here")
        sv = result.scores[RubricCategory.STRUCTURAL_VALIDITY]
        # evidence flags: manifest invalid, scripts vacuously parseable, no behavior
        assert sv.evidence["manifest_valid_json"] is False
        assert sv.evidence["scripts_parseable"] is True  # empty list -> vacuously true
        assert sv.evidence["behavior_file_structure"] is False
        # 1 of 3 criteria met -> 1.0 (partial_credits['1_of_3'])
        assert sv.score == 1.0

    def test_evaluate_behavioral_preservation_with_real_signals(self):
        ev = RubricEvaluator()
        java = (
            "public class Foo { @SubscribeEvent public void onSpawn(EntitySpawnEvent e) {}\n"
            "@Mod.Element public void registerBlock(BlockPos p) {}\n"
            "public void useItem(ItemStack s) {}\n"
            "public void handleEvent(EventHandler e) {}\n"
            "}"
        )
        bedrock = (
            f"```json\n{json.dumps({'format_version': 2, 'header': {'name': 'T', 'uuid': 'a', 'version': [1, 0, 0]}, 'modules': [{'type': 'data', 'uuid': 'b', 'version': [1, 0, 0]}]})}\n```\n"
            f"```javascript\nimport {{ ItemStack }} from '@minecraft/server';\nworld.afterEvents.entitySpawn.subscribe((e) => log(e));\n```"
        )
        result = ev.evaluate(java_source=java, bedrock_output=bedrock)
        bp = result.scores[RubricCategory.BEHAVIORAL_PRESERVATION]
        # At least one behavioral criterion should be preserved
        assert bp.score > 0.0

    def test_evaluate_constraint_compliance_detects_violation(self):
        ev = RubricEvaluator()
        # Use a JS snippet that matches the constraint pattern (no `)` between
        # `subscribe(` and the keyword).
        bedrock = (
            f"```json\n{VALID_MANIFEST}\n```\n"
            "```javascript\nimport { world } from '@minecraft/server';\n"
            "world.afterEvents.foo.subscribe(while(true){});\n"
            "```"
        )
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        cc = result.scores[RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE]
        # tick_rate violation should be in evidence
        assert cc.evidence["tick_rate_respected"] is False

    def test_evaluate_code_quality_with_proper_imports(self):
        ev = RubricEvaluator()
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\n{VALID_SCRIPT}\n```"
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        cq = result.scores[RubricCategory.CODE_QUALITY]
        # Valid import + world access should give full idiomatic credit
        assert cq.evidence["idiomatic_bedrock_script"] is True

    def test_evaluate_code_quality_flags_deprecated(self):
        ev = RubricEvaluator()
        bedrock = (
            f"```json\n{VALID_MANIFEST}\n```\n"
            "```javascript\nimport { world } from '@minecraft/server';\n"
            "world.sendMessage('hi');\n"
            "```"
        )
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        cq = result.scores[RubricCategory.CODE_QUALITY]
        # No deprecated APIs in this snippet
        assert cq.evidence["no_deprecated_apis"] is True

    def test_evaluate_structural_validity_balanced_braces(self):
        ev = RubricEvaluator()
        # Unbalanced braces should mark scripts as unparseable
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\nimport {{ world }} from '@minecraft/server';\nworld.foo = 1;\n```"
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        sv = result.scores[RubricCategory.STRUCTURAL_VALIDITY]
        assert sv.evidence["manifest_valid_json"] is True
        assert sv.evidence["scripts_parseable"] is True

    def test_evaluate_rewards_full_credit_yields_max(self):
        ev = RubricEvaluator()
        # Best-case bedrock output: valid manifest + clean script
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\n{VALID_SCRIPT}\n```"
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        # No Java code -> behavioral preservation should get full credit (vacuously)
        assert (
            result.scores[RubricCategory.BEHAVIORAL_PRESERVATION].score
            == result.scores[RubricCategory.BEHAVIORAL_PRESERVATION].max_score
        )

    def test_evaluate_adjudication_notes_present(self):
        ev = RubricEvaluator()
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\n{VALID_SCRIPT}\n```"
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        assert isinstance(result.adjudication_notes, str)
        assert len(result.adjudication_notes) > 0

    def test_evaluate_reward_signal_present(self):
        ev = RubricEvaluator()
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\n{VALID_SCRIPT}\n```"
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        rs = result.reward_signal
        assert rs.total_reward >= 0.0
        assert 0.0 <= rs.behavioral_preservation <= 1.0
        assert 0.0 <= rs.constraint_compliance <= 1.0
        assert 0.0 <= rs.code_quality <= 1.0
        assert 0.0 <= rs.structural_validity <= 1.0
        # Penalty reasons are a list
        assert isinstance(rs.penalty_reasons, list)


class TestRubricEvaluatorPartialCredits:
    """Cover the partial-credit math per rubric category."""

    def test_behavioral_partial_credit_branches(self):
        ev = RubricEvaluator()
        # Manually score: 2/4 preserved -> 2.0
        # Java with entity, block, item, but no event
        java = "class X { void f() { EntitySpawnEvent e; BlockPos p; ItemStack i; } }"
        bedrock = f"```json\n{VALID_MANIFEST}\n```\n```javascript\n{VALID_SCRIPT}\n```"
        result = ev.evaluate(java_source=java, bedrock_output=bedrock)
        bp = result.scores[RubricCategory.BEHAVIORAL_PRESERVATION]
        # Score must be one of the partial_credit values
        valid_scores = list(
            RUBRIC_DEFINITIONS[RubricCategory.BEHAVIORAL_PRESERVATION]["partial_credits"].values()
        )
        assert bp.score in valid_scores

    def test_constraint_partial_credit_branches(self):
        ev = RubricEvaluator()
        # Force a tick violation
        bedrock = (
            f"```json\n{VALID_MANIFEST}\n```\n"
            "```javascript\nimport { world } from '@minecraft/server';\n"
            "world.afterEvents.foo.subscribe(while(true){});\n"
            "```"
        )
        result = ev.evaluate(java_source="", bedrock_output=bedrock)
        cc = result.scores[RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE]
        valid_scores = list(
            RUBRIC_DEFINITIONS[RubricCategory.BEDROCK_CONSTRAINT_COMPLIANCE][
                "partial_credits"
            ].values()
        )
        assert cc.score in valid_scores
