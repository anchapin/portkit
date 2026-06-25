"""
Unit tests for failure_taxonomy - operational failure classification for converter/validator agents.

Covers all six failure categories from the research-validated operational safety taxonomy
(arxiv:2605.30777) as applied to PortKit's Java->Bedrock conversion pipeline.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from conversion.failure_taxonomy import (
    FailureClassifier,
    FailureType,
    Severity,
    FailureClassification,
    FailureEvidence,
    classify_conversion_failure,
    classify_all_failures,
)


class TestFailureClassifierFabricatedSuccess:
    """Tests for FABRICATED_SUCCESS failure type detection."""

    def test_empty_bedrock_output(self):
        classifier = FailureClassifier()
        result = classifier.classify("")
        assert result.failure_type == FailureType.FABRICATED_SUCCESS
        assert result.confidence >= 0.9

    def test_comment_only_output(self):
        classifier = FailureClassifier()
        output = "// TODO: implement this\n// Also need to finish"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.FABRICATED_SUCCESS
        assert result.confidence >= 0.9

    def test_unclosed_function(self):
        classifier = FailureClassifier()
        output = "function test() {\n  console.log('hello'\n"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.FABRICATED_SUCCESS
        assert any("unclosed" in e.description.lower() for e in result.evidence)

    def test_unclosed_brace_at_start(self):
        classifier = FailureClassifier()
        output = "} else { console.log('test'); }"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.FABRICATED_SUCCESS

    def test_valid_output_no_failure(self):
        classifier = FailureClassifier()
        output = "import { world } from '@minecraft/server';\nworld.afterEvents.playerBreakBlock.subscribe(() => {});"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE

    def test_clean_function_with_braces(self):
        classifier = FailureClassifier()
        output = "function activate() {\n  console.log('Activated');\n}"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE


class TestFailureClassifierScopeCreep:
    """Tests for SCOPE_CREEP failure type detection."""

    def test_unconvertable_marker(self):
        classifier = FailureClassifier()
        bedrock = "function convert() { console.log('hi'); } // unconvertable feature"
        java = "obj.getClass().getMethods();"
        result = classifier.classify(bedrock, java_input=java)
        assert result.failure_type == FailureType.SCOPE_CREEP

    def test_java_reflection_without_bedrock_reflection(self):
        classifier = FailureClassifier()
        bedrock = "function test() { console.log('test'); }"
        java = "Method[] methods = obj.getClass().getDeclaredMethods();"
        result = classifier.classify(bedrock, java_input=java)
        assert result.failure_type == FailureType.SCOPE_CREEP

    def test_java_threading_without_async(self):
        classifier = FailureClassifier()
        bedrock = "function test() { let x = 1; }"
        java = "new Thread(() -> doWork()).start();"
        result = classifier.classify(bedrock, java_input=java)
        assert result.failure_type == FailureType.SCOPE_CREEP

    def test_no_java_input_no_scope_creep_detection(self):
        classifier = FailureClassifier()
        bedrock = "function test() { console.log('test'); }"
        result = classifier.classify(bedrock, java_input="")
        assert result.failure_type != FailureType.SCOPE_CREEP

    def test_java_threading_with_async_handling(self):
        classifier = FailureClassifier()
        bedrock = "function test() { system.run(() => doWork()); }"
        java = "new Thread(() -> doWork()).start();"
        result = classifier.classify(bedrock, java_input=java)
        assert result.failure_type == FailureType.NONE


class TestFailureClassifierHallucinatedApi:
    """Tests for HALLUCINATED_API failure type detection."""

    def test_double_underscore_minecraft_api(self):
        classifier = FailureClassifier()
        output = "import { world } from '@minecraft/server';\nminecraft__server.world.getAllPlayers();"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.HALLUCINATED_API
        assert any("double-underscore" in e.description.lower() for e in result.evidence)

    def test_valid_minecraft_api_no_hallucination(self):
        classifier = FailureClassifier()
        output = "import { world } from '@minecraft/server';\nworld.afterEvents.playerBreakBlock.subscribe(() => {});"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE

    def test_unknown_world_api_with_import(self):
        classifier = FailureClassifier()
        output = "import { world } from '@minecraft/server';\nworld.getNonexistentMethod();"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.HALLUCINATED_API

    def test_player_nonexistent_api_with_import(self):
        classifier = FailureClassifier()
        output = "import { player } from '@minecraft/server';\nplayer.getNonexistentProperty();"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.HALLUCINATED_API


class TestFailureClassifierIncompleteConversion:
    """Tests for INCOMPLETE_CONVERSION failure type detection."""

    def test_incomplete_markers_single(self):
        classifier = FailureClassifier()
        output = "function convert() {\n  return '???';\n}"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.INCOMPLETE_CONVERSION

    @pytest.mark.parametrize(
        "marker",
        ["???", "TODO", "FIXME", "UNCONVERTED", "NOT_YET_IMPLEMENTED", "PLACEHOLDER"],
    )
    def test_incomplete_markers(self, marker):
        classifier = FailureClassifier()
        output = f"function convert() {{\n  // {marker}: need to handle this\n}}"
        results = classifier.classify_all(output)
        types_found = {r.failure_type for r in results}
        assert FailureType.INCOMPLETE_CONVERSION in types_found

    def test_multiple_incomplete_markers(self):
        classifier = FailureClassifier()
        output = "???\nTODO: implement\nFIXME: fix this later"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.INCOMPLETE_CONVERSION
        assert len(result.evidence) >= 3

    def test_no_incomplete_markers(self):
        classifier = FailureClassifier()
        output = "function activate() { console.log('Activated'); }"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE


class TestFailureClassifierTypeMismatch:
    """Tests for TYPE_MISMATCH failure type detection."""

    def test_raw_long_type(self):
        classifier = FailureClassifier()
        output = "const id: long = 12345;"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.TYPE_MISMATCH

    def test_raw_arraylist(self):
        classifier = FailureClassifier()
        output = "const items = new ArrayList();"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.TYPE_MISMATCH

    def test_raw_hashmap(self):
        classifier = FailureClassifier()
        output = "const map = new HashMap();"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.TYPE_MISMATCH

    def test_java_generic_list(self):
        classifier = FailureClassifier()
        output = "const items: List<Item> = [];"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.TYPE_MISMATCH

    def test_proper_bedrock_types(self):
        classifier = FailureClassifier()
        output = "const items: MinecraftItem[] = [];\nconst playerMap: Map<string, number> = new Map();"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE


class TestFailureClassifierDependencyMismatch:
    """Tests for DEPENDENCY_MISMATCH failure type detection."""

    def test_uses_api_without_import(self):
        classifier = FailureClassifier()
        output = "world.afterEvents.playerBreakBlock.subscribe(handler);"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.DEPENDENCY_MISMATCH

    def test_java_import_in_bedrock_output(self):
        classifier = FailureClassifier()
        output = "import java.io.File;\nfunction test() { world.getAllPlayers(); }"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.DEPENDENCY_MISMATCH

    def test_proper_import_statement(self):
        classifier = FailureClassifier()
        output = "import { world } from '@minecraft/server';\nworld.afterEvents.playerBreakBlock.subscribe(handler);"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE

    def test_no_api_usage_no_import(self):
        classifier = FailureClassifier()
        output = "const x = 1 + 2;"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE


class TestFailureClassifierClassifyAll:
    """Tests for multi-failure detection via classify_all."""

    def test_multiple_failures_detected(self):
        classifier = FailureClassifier()
        output = "???\nimport java.io.File;\nimport { world } from '@minecraft/server';\nworld.badApiMethod();"
        java = "new Thread().start();"
        results = classifier.classify_all(output, java_input=java)
        failure_types = {r.failure_type for r in results}
        assert FailureType.INCOMPLETE_CONVERSION in failure_types
        assert FailureType.DEPENDENCY_MISMATCH in failure_types

    def test_classify_all_with_clean_output(self):
        classifier = FailureClassifier()
        output = "import { world } from '@minecraft/server';\nworld.afterEvents.playerBreakBlock.subscribe(() => {});"
        results = classifier.classify_all(output)
        assert len(results) == 0


class TestFailureClassifierHardeningMode:
    """Tests for hardening mode behavior."""

    def test_hardening_mode_attribute(self):
        classifier = FailureClassifier(hardening_mode=True)
        assert classifier.hardening_mode is True

    def test_standard_mode_attribute(self):
        classifier = FailureClassifier()
        assert classifier.hardening_mode is False


class TestFailureClassifierEdgeCases:
    """Edge case tests."""

    def test_whitespace_only_output(self):
        classifier = FailureClassifier()
        result = classifier.classify("   \n\n   ")
        assert result.failure_type == FailureType.FABRICATED_SUCCESS

    def test_unicode_in_output(self):
        classifier = FailureClassifier()
        output = "function test() { console.log('こんにちは'); }"
        result = classifier.classify(output)
        assert result.failure_type == FailureType.NONE

    def test_very_long_line(self):
        classifier = FailureClassifier()
        long_line = "function test() { " + "x" * 1000 + " }"
        result = classifier.classify(long_line)
        assert result.failure_type in (FailureType.NONE, FailureType.FABRICATED_SUCCESS)

    def test_classify_with_empty_conversion_scope(self):
        classifier = FailureClassifier()
        output = "function test() { console.log('test'); }"
        result = classifier.classify(output, conversion_scope=[])
        assert result.failure_type == FailureType.NONE


class TestClassifyConversionFailure:
    """Tests for the module-level convenience function."""

    def test_classify_conversion_failure_function(self):
        result = classify_conversion_failure("???", java_input="Thread.sleep(100);")
        assert result.failure_type != FailureType.NONE

    def test_classify_all_failures_function(self):
        results = classify_all_failures("???\nimport java.util.List;\nworld.badApi();")
        assert len(results) >= 2


class TestFailureClassificationToDict:
    """Tests for serialization of FailureClassification."""

    def test_to_dict_includes_all_fields(self):
        classification = FailureClassification(
            failure_type=FailureType.FABRICATED_SUCCESS,
            confidence=0.85,
            message="Test message",
            severity=Severity.HIGH,
            evidence=[
                FailureEvidence(
                    location="line 1",
                    description="Test evidence",
                    snippet="test snippet",
                )
            ],
        )
        d = classification.to_dict()
        assert d["failure_type"] == "fabricated_success"
        assert d["confidence"] == 0.85
        assert d["severity"] == "high"
        assert d["message"] == "Test message"
        assert len(d["evidence"]) == 1
        assert d["evidence"][0]["location"] == "line 1"


class TestFailureTypeEnumValues:
    """Verify FailureType enum has expected values."""

    def test_all_expected_types_present(self):
        expected = {
            "fabricated_success",
            "scope_creep",
            "hallucinated_api",
            "incomplete_conversion",
            "type_mismatch",
            "dependency_mismatch",
            "none",
        }
        actual = {ft.value for ft in FailureType}
        assert expected == actual


if __name__ == "__main__":
    pytest.main([__file__, "-v"])