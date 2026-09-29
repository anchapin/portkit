"""
Unit tests for Issue #1775 - Entity Behavior Contract Validation

Tests that generated entity behavior components conform to the Bedrock API contract
by validating that all `minecraft:behavior.*` keys are present in the Bedrock behavior allowlist.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.qa.minecraft_contract import (
    MinecraftContract,
    Severity,
    VALID_BEDROCK_BEHAVIORS,
)
from agents.entity.entity_converter import EntityConverter


class TestEntityBehaviorContract:
    """Test cases for entity behavior contract validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.contract = MinecraftContract()

    def test_valid_behavior_passes_validation(self):
        """Test that a valid vanilla behavior passes validation without violations."""
        data = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {"identifier": "testmod:valid_zombie"},
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                    "minecraft:behavior.melee_attack": {
                        "priority": 3,
                        "speed_multiplier": 1.0,
                        "track_target": True,
                    },
                    "minecraft:behavior.wander": {
                        "priority": 6,
                        "speed_multiplier": 0.8,
                    },
                    "minecraft:behavior.panic": {
                        "priority": 1,
                        "speed_multiplier": 1.25,
                    },
                },
                "events": {},
            },
        }
        passed, violations = self.contract.validate_bedrock_json(data, "test.json")
        assert passed is True, f"Expected valid behaviors to pass, got violations: {violations}"
        assert len(violations) == 0

    def test_fabricated_behavior_is_flagged(self):
        """Test that a fabricated `minecraft:behavior.<bogus>` key is flagged with rule_id='entity_behavior_contract'."""
        data = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {"identifier": "testmod:fabricated_zombie"},
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                    "minecraft:behavior.summon_lightning": {
                        "priority": 1,
                    },
                },
                "events": {},
            },
        }
        passed, violations = self.contract.validate_bedrock_json(data, "test.json")
        assert passed is False
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 1, (
            f"Expected exactly 1 entity_behavior_contract violation, got {len(entity_behavior_violations)}"
        )
        violation = entity_behavior_violations[0]
        assert violation.severity == Severity.HIGH
        assert "summon_lightning" in violation.message
        assert "test.json" in violation.location

    def test_mixed_valid_and_fabricated_behaviors(self):
        """Test entity with one valid and one fabricated behavior produces exactly one contract violation."""
        data = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {"identifier": "testmod:mixed_mob"},
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                    "minecraft:behavior.melee_attack": {"priority": 3},
                    "minecraft:behavior.fake_super_ability": {"priority": 1},
                },
                "events": {},
            },
        }
        passed, violations = self.contract.validate_bedrock_json(data, "test.json")
        assert passed is False
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 1, (
            f"Expected exactly 1 entity_behavior_contract violation, got {len(entity_behavior_violations)}"
        )
        assert "fake_super_ability" in entity_behavior_violations[0].message

    def test_hostile_mob_fixture_passes(self):
        """Test that the canonical hostile mob fixture from test_entity_ai_conversion.py passes under the new rule."""
        converter = EntityConverter()
        java_entity = {
            "id": "smart_zombie",
            "namespace": "testmod",
            "category": "hostile",
            "attributes": {
                "max_health": 40.0,
                "movement_speed": 0.28,
                "attack_damage": 6.0,
            },
            "ai_goals": [
                {"type": "melee_attack", "priority": 3},
                {"type": "look_at_player", "priority": 5, "config": {"range": 10.0}},
                {"type": "move", "priority": 4},
                {"type": "panic", "priority": 1},
                {"type": "wander", "priority": 6},
            ],
        }
        result = converter.convert_entities([java_entity])
        entity_data = result["testmod:smart_zombie"]
        passed, violations = self.contract.validate_bedrock_json(entity_data, "test.json")
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 0, (
            f"Expected hostile mob fixture to pass without entity_behavior_contract violations, "
            f"got: {[v.message for v in entity_behavior_violations]}"
        )

    def test_passive_mob_fixture_passes(self):
        """Test that the canonical passive mob fixture passes under the new rule."""
        converter = EntityConverter()
        java_entity = {
            "id": "friendly_chicken",
            "namespace": "testmod",
            "category": "passive",
            "attributes": {
                "max_health": 10.0,
                "movement_speed": 0.2,
            },
            "can_breed": True,
        }
        result = converter.generate_passive_mob(java_entity)
        passed, violations = self.contract.validate_bedrock_json(result, "test.json")
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 0, (
            f"Expected passive mob fixture to pass without entity_behavior_contract violations, "
            f"got: {[v.message for v in entity_behavior_violations]}"
        )

    def test_behavior_in_component_groups(self):
        """Test that behaviors inside component_groups are also validated."""
        data = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {"identifier": "testmod:state_mob"},
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                },
                "component_groups": {
                    "awake": {
                        "components": {
                            "minecraft:behavior.melee_attack": {"priority": 3},
                        },
                    },
                    "sleeping": {
                        "components": {
                            "minecraft:behavior.fake_sleep_behavior": {"priority": 1},
                        },
                    },
                },
                "events": {},
            },
        }
        passed, violations = self.contract.validate_bedrock_json(data, "test.json")
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 1
        assert "fake_sleep_behavior" in entity_behavior_violations[0].message

    def test_valid_bedrock_behaviors_allowlist_populated(self):
        """Test that VALID_BEDROCK_BEHAVIORS contains expected common behaviors."""
        expected_behaviors = [
            "minecraft:behavior.melee_attack",
            "minecraft:behavior.wander",
            "minecraft:behavior.panic",
            "minecraft:behavior.follow_player",
            "minecraft:behavior.look_at_player",
            "minecraft:behavior.float",
            "minecraft:behavior.random_stroll",
            "minecraft:behavior.swim",
            "minecraft:behavior.breed",
            "minecraft:behavior.avoid_entity",
        ]
        for behavior in expected_behaviors:
            assert behavior in VALID_BEDROCK_BEHAVIORS, (
                f"Expected {behavior} to be in VALID_BEDROCK_BEHAVIORS"
            )

    def test_fabricated_behavior_rule_id_is_entity_behavior_contract(self):
        """Test that fabricated behavior violations have rule_id='entity_behavior_contract'."""
        data = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {"identifier": "testmod:test"},
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                    "minecraft:behavior.hallucinated_ai_behavior": {"priority": 1},
                },
                "events": {},
            },
        }
        _, violations = self.contract.validate_bedrock_json(data, "test.json")
        assert any(v.rule_id == "entity_behavior_contract" for v in violations)

    def test_multiple_fabricated_behaviors_all_flagged(self):
        """Test that multiple fabricated behaviors in same entity are each flagged separately."""
        data = {
            "format_version": "1.19.0",
            "minecraft:entity": {
                "description": {"identifier": "testmod:multi_fake"},
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                    "minecraft:behavior.fake_one": {"priority": 1},
                    "minecraft:behavior.fake_two": {"priority": 2},
                },
                "events": {},
            },
        }
        _, violations = self.contract.validate_bedrock_json(data, "test.json")
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 2


class TestEntityBehaviorContractIntegration:
    """Integration tests for entity behavior contract with EntityConverter output."""

    def setup_method(self):
        """Set up test fixtures."""
        self.contract = MinecraftContract()
        self.converter = EntityConverter()

    def test_convert_entities_output_validated(self):
        """Test that EntityConverter.convert_entities output passes behavior validation."""
        java_entities = [
            {
                "id": "test_zombie",
                "namespace": "testmod",
                "category": "hostile",
                "attributes": {"max_health": 30, "movement_speed": 0.3},
                "ai_goals": [
                    {"type": "melee_attack", "priority": 3},
                    {"type": "panic", "priority": 1},
                ],
            },
        ]
        result = self.converter.convert_entities(java_entities)
        entity_data = result["testmod:test_zombie"]
        passed, violations = self.contract.validate_bedrock_json(entity_data, "test.json")
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 0, (
            f"convert_entities output should not have entity behavior violations, "
            f"got: {[v.message for v in entity_behavior_violations]}"
        )

    def test_generate_hostile_mob_valid_behaviors(self):
        """Test that generate_hostile_mob produces valid behaviors."""
        java_entity = {
            "id": "hostile_creeper",
            "namespace": "testmod",
            "category": "hostile",
            "attributes": {"max_health": 30, "movement_speed": 0.3},
            "can_attack": True,
        }
        result = self.converter.generate_hostile_mob(java_entity)
        passed, violations = self.contract.validate_bedrock_json(result, "test.json")
        entity_behavior_violations = [v for v in violations if v.rule_id == "entity_behavior_contract"]
        assert len(entity_behavior_violations) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
