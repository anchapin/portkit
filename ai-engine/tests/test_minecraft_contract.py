"""
Unit tests for Minecraft Contract - schema validation and automatic repair.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.qa.minecraft_contract import (
    MinecraftContract,
    ContractViolation,
    Severity,
    validate_bedrock_json,
    validate_script_api,
    repair_contract_violations,
    VALID_SCRIPT_API_METHODS,
    NUMERIC_RANGES,
    COORDINATE_SCHEMA,
)


class TestContractViolation:
    """Test cases for ContractViolation dataclass"""

    def test_contract_violation_to_dict(self):
        violation = ContractViolation(
            severity=Severity.HIGH,
            message="Test violation",
            location="test.json:entity",
            suggestion="Fix this",
            rule_id="test_rule",
        )
        result = violation.to_dict()
        assert result["severity"] == "high"
        assert result["message"] == "Test violation"
        assert result["location"] == "test.json:entity"
        assert result["suggestion"] == "Fix this"
        assert result["rule_id"] == "test_rule"


class TestMinecraftContractInit:
    """Test cases for MinecraftContract initialization"""

    def test_default_values(self):
        contract = MinecraftContract()
        assert contract.strict_mode is True
        assert contract.max_violations == 100
        assert contract.repair_threshold == 5

    def test_custom_values(self):
        contract = MinecraftContract(strict_mode=False, max_violations=50, repair_threshold=10)
        assert contract.strict_mode is False
        assert contract.max_violations == 50
        assert contract.repair_threshold == 10


class TestValidateBedrockJson:
    """Test cases for validate_bedrock_json method"""

    def test_valid_entity_with_all_components(self):
        data = {
            "format_version": "1.20.0",
            "minecraft:entity": {
                "description": {"identifier": "test:custom_entity"},
                "components": {
                    "minecraft:health": {"value": 20},
                    "minecraft:movement": {"value": 0.25},
                },
                "events": {},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert passed is True
        assert len(violations) == 0

    def test_valid_block(self):
        data = {
            "format_version": "1.20.0",
            "minecraft:block": {
                "description": {"identifier": "test:custom_block"},
                "components": {"minecraft:geometry": "geometry.test"},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "block.json")
        assert passed is True

    def test_valid_item(self):
        data = {
            "format_version": "1.20.0",
            "minecraft:item": {
                "description": {"identifier": "test:custom_item"},
                "components": {"minecraft:max_stack_size": 64},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "item.json")
        assert passed is True

    def test_missing_required_field(self):
        data = {
            "minecraft:entity": {
                "description": {"identifier": "test:entity"},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert passed is False
        assert len(violations) > 0
        assert any(v.rule_id == "required_field" for v in violations)

    def test_events_outside_components(self):
        data = {
            "minecraft:entity": {
                "description": {"identifier": "test:entity"},
                "events": {"test_event": {"trigger": {}}},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert passed is False
        assert any(v.rule_id == "entity_event_nesting" for v in violations)

    def test_numeric_range_violation_damage(self):
        data = {
            "minecraft:item": {
                "description": {"identifier": "test:weapon"},
                "components": {"minecraft:damage": 50000},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert len(violations) > 0
        assert any(v.rule_id == "numeric_range" for v in violations)

    def test_numeric_range_violation_health(self):
        data = {
            "minecraft:entity": {
                "description": {"identifier": "test:entity"},
                "components": {
                    "minecraft:health": {"value": 9999},
                },
                "events": {},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert len(violations) > 0

    def test_valid_numeric_ranges(self):
        data = {
            "minecraft:item": {
                "description": {"identifier": "test:sword"},
                "components": {
                    "minecraft:damage": 10,
                    "minecraft:max_stack_size": 1,
                },
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert passed is True

    def test_coordinate_out_of_bounds(self):
        data = {
            "minecraft:entity": {
                "description": {"identifier": "test:entity"},
                "components": {
                    "minecraft:spawn_conditions": {
                        "x": 50000000,
                        "y": 10,
                        "z": 0,
                    },
                },
                "events": {},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert passed is False
        assert any(v.rule_id == "coordinate_bounds" for v in violations)

    def test_valid_coordinates(self):
        data = {
            "minecraft:entity": {
                "description": {"identifier": "test:entity"},
                "components": {
                    "minecraft:spawn_conditions": {
                        "x": 100,
                        "y": 64,
                        "z": 200,
                    },
                },
                "events": {},
            },
        }
        contract = MinecraftContract()
        passed, violations = contract.validate_bedrock_json(data, "test.json")
        assert passed is True


class TestValidateScriptApi:
    """Test cases for validate_script_api method"""

    def test_valid_script_api_usage(self):
        script = """
        import { world } from '@minecraft/server';

        world.afterEvents.entitySpawn.subscribe((event) => {
            const entity = event.entity;
            entity.applyDamage(10);
        });
        """
        contract = MinecraftContract()
        passed, violations = contract.validate_script_api(script, "test.ts")
        assert passed is True

    def test_unknown_script_api_method(self):
        script = """
        import { world } from '@minecraft/server';

        world.someUnknownMethod();
        entity.invalidMethod();
        """
        contract = MinecraftContract()
        passed, violations = contract.validate_script_api(script, "test.ts")
        assert len(violations) > 0
        assert any(v.rule_id == "script_api_method" or v.rule_id == "script_api_object" for v in violations)

    def test_valid_entity_api_call(self):
        script = """
        const entity = world.getEntities().next();
        entity.getComponent('minecraft:health');
        """
        contract = MinecraftContract()
        passed, violations = contract.validate_script_api(script, "test.ts")
        assert len(violations) == 0

    def test_invalid_player_api_call(self):
        script = """
        player.sendFakeMessage();
        player.invalidMethod();
        """
        contract = MinecraftContract()
        passed, violations = contract.validate_script_api(script, "test.ts")
        assert len(violations) > 0


class TestRepairContractViolations:
    """Test cases for repair_contract_violations method"""

    def test_no_repair_needed(self):
        violations = []
        content = '{"test": "content"}'
        result = repair_contract_violations(violations, content)
        assert result["needs_repair"] is False
        assert result["original_content"] == content

    def test_repair_needed_threshold(self):
        violations = [
            ContractViolation(
                severity=Severity.MEDIUM,
                message="Test violation",
                location="test.json",
                suggestion="Fix it",
                rule_id="test",
            ),
        ] * 5
        content = '{"test": "content"}'
        result = repair_contract_violations(violations, content)
        assert result["needs_repair"] is True
        assert result["violations_count"] == 5

    def test_repair_needed_critical(self):
        violations = [
            ContractViolation(
                severity=Severity.CRITICAL,
                message="Critical error",
                location="test.json",
                suggestion="Fix immediately",
                rule_id="critical",
            ),
        ]
        content = '{"test": "content"}'
        result = repair_contract_violations(violations, content)
        assert result["needs_repair"] is True
        assert result["critical_count"] == 1

    def test_repair_prompt_generation(self):
        violations = [
            ContractViolation(
                severity=Severity.CRITICAL,
                message="Critical error",
                location="test.json",
                suggestion="Fix immediately",
                rule_id="critical",
            ),
            ContractViolation(
                severity=Severity.HIGH,
                message="Missing field",
                location="test.json:entity",
                suggestion="Add the field",
                rule_id="required_field",
            ),
        ]
        content = '{"minecraft:entity": {"description": {"identifier": "test"}}}'
        result = repair_contract_violations(violations, content, "Test context")
        assert "repair_prompt" in result
        assert "Violations found" in result["repair_prompt"]


class TestGetContractScore:
    """Test cases for get_contract_score method"""

    def test_no_violations_score_100(self):
        contract = MinecraftContract()
        score = contract.get_contract_score([])
        assert score == 100.0

    def test_critical_violation_penalty(self):
        contract = MinecraftContract()
        violations = [
            ContractViolation(
                severity=Severity.CRITICAL,
                message="Critical",
                location="test.json",
                suggestion="Fix",
                rule_id="test",
            ),
        ]
        score = contract.get_contract_score(violations)
        assert score < 100

    def test_multiple_violations(self):
        contract = MinecraftContract()
        violations = [
            ContractViolation(Severity.HIGH, "High", "loc", "sug", "r1"),
            ContractViolation(Severity.MEDIUM, "Medium", "loc", "sug", "r2"),
            ContractViolation(Severity.LOW, "Low", "loc", "sug", "r3"),
        ]
        score = contract.get_contract_score(violations)
        assert score < 100
        assert score > 0


class TestFormatViolationReport:
    """Test cases for format_violation_report method"""

    def test_no_violations(self):
        contract = MinecraftContract()
        report = contract.format_violation_report([])
        assert report == "No contract violations found."

    def test_format_violations_by_severity(self):
        contract = MinecraftContract()
        violations = [
            ContractViolation(Severity.CRITICAL, "Critical error", "loc1", "fix1", "r1"),
            ContractViolation(Severity.HIGH, "High error", "loc2", "fix2", "r2"),
            ContractViolation(Severity.MEDIUM, "Medium error", "loc3", "fix3", "r3"),
        ]
        report = contract.format_violation_report(violations)
        assert "CRITICAL" in report
        assert "HIGH" in report
        assert "MEDIUM" in report
        assert "3 violations" in report


class TestValidateBedrockFile:
    """Test cases for validate_bedrock_file method"""

    def test_valid_json_file(self):
        contract = MinecraftContract()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "minecraft:entity": {
                        "description": {"identifier": "test:entity"},
                        "components": {},
                        "events": {},
                    }
                },
                f,
            )
            f.flush()
            path = Path(f.name)
            passed, violations = contract.validate_bedrock_file(path)
            assert passed is True
            path.unlink()

    def test_invalid_json_file(self):
        contract = MinecraftContract()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            f.flush()
            path = Path(f.name)
            passed, violations = contract.validate_bedrock_file(path)
            assert passed is False
            assert any(v.rule_id == "json_syntax" for v in violations)
            path.unlink()


class TestValidateDirectory:
    """Test cases for validate_directory method"""

    def test_directory_with_valid_files(self):
        contract = MinecraftContract()
        with tempfile.TemporaryDirectory() as tmpdir:
            entity_path = Path(tmpdir) / "entity.json"
            entity_path.write_text(
                json.dumps(
                    {
                        "minecraft:entity": {
                            "description": {"identifier": "test:entity"},
                            "components": {},
                            "events": {},
                        }
                    }
                )
            )
            passed, violations = contract.validate_directory(Path(tmpdir))
            assert passed is True

    def test_directory_with_violations(self):
        contract = MinecraftContract()
        with tempfile.TemporaryDirectory() as tmpdir:
            entity_path = Path(tmpdir) / "entity.json"
            entity_path.write_text(
                json.dumps(
                    {
                        "minecraft:entity": {
                            "description": {"identifier": "test"},
                        }
                    }
                )
            )
            passed, violations = contract.validate_directory(Path(tmpdir))
            assert passed is False


class TestConstants:
    """Test cases for module constants"""

    def test_script_api_methods_defined(self):
        assert "Entity" in VALID_SCRIPT_API_METHODS
        assert "Player" in VALID_SCRIPT_API_METHODS
        assert "World" in VALID_SCRIPT_API_METHODS

    def test_numeric_ranges_defined(self):
        assert "damage" in NUMERIC_RANGES
        assert NUMERIC_RANGES["damage"] == (0, 32767)
        assert "health" in NUMERIC_RANGES
        assert "max_stack_size" in NUMERIC_RANGES

    def test_coordinate_schema_defined(self):
        assert "x" in COORDINATE_SCHEMA
        assert "y" in COORDINATE_SCHEMA
        assert "z" in COORDINATE_SCHEMA
        assert COORDINATE_SCHEMA["y"]["min"] == -64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])