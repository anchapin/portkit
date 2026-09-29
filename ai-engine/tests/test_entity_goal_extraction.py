"""
Unit tests for Entity Goal Extraction from registerGoals() AST

Tests the extraction of Java entity AI goals from registerGoals() method
bodies via tree-sitter AST analysis, and the handling of unmapped goals.

Issue: #1774
"""

import pytest
import sys
from pathlib import Path

ai_engine_root = Path(__file__).parent.parent
sys.path.insert(0, str(ai_engine_root))

from agents.java_analyzer.feature_extractor import FeatureExtractor
from knowledge.patterns.entity_behavior_patterns import (
    convert_java_goal_to_bedrock,
    get_behavior_stats,
    reset_unmapped_goal_count,
)


class TestRegisterGoalsASTExtraction:
    """Test cases for registerGoals() AST extraction."""

    def setup_method(self):
        """Set up test fixtures."""
        patterns = {
            "blocks": ["Block", "BlockState", "registerBlock", "ModBlocks"],
            "items": ["Item", "ItemStack", "registerItem", "ModItems"],
            "entities": ["Entity", "EntityType", "registerEntity", "ModEntities"],
            "recipes": ["IRecipe", "ShapedRecipe", "ShapelessRecipe", "registerRecipe"],
            "dimensions": ["Dimension", "World", "DimensionType", "createDimension"],
            "gui": ["GuiScreen", "ContainerScreen", "IGuiHandler", "MenuType"],
            "machinery": ["TileEntity", "BlockEntity", "IEnergyStorage", "IFluidHandler"],
            "commands": ["Command", "ICommand", "CommandBase", "registerCommand"],
            "events": ["Event", "SubscribeEvent", "EventHandler", "Listener"],
        }
        self.extractor = FeatureExtractor(patterns)
        reset_unmapped_goal_count()

    def test_extract_melee_attack_goal(self):
        """Test extraction of a MeleeAttackGoal from registerGoals."""
        source = """
package com.example;

import net.minecraft.entity.ai.goal.MeleeAttackGoal;
import net.minecraft.entity.ai.goal.FloatGoal;
import net.minecraft.entity.ai.goal.WaterNavipoor;
import net.minecraft.entity.ai.goal.Goal;

public class CustomEntity extends PathfinderMob {
    @Override
    protected void registerGoals() {
        this.goalSelector.addGoal(0, new FloatGoal(this));
        this.goalSelector.addGoal(1, new MeleeAttackGoal(this, 1.2, true));
        this.goalSelector.addGoal(2, new RandomStrollGoal(this, 1.0));
    }
}
"""
        tree = self.extractor.parse_java_source(source)
        assert tree is not None, "Failed to parse Java source"

        goals = self.extractor.extract_entity_goals_from_ast(tree)

        assert len(goals) >= 1, f"Expected at least 1 goal, got {len(goals)}"
        goal_types = [g["type"] for g in goals]
        assert "melee_attack" in goal_types, f"melee_attack not in {goal_types}"

        melee_goal = next(g for g in goals if g["type"] == "melee_attack")
        assert melee_goal["priority"] == 1
        assert "speed_multiplier" in melee_goal["config"]

    def test_extract_multiple_goals(self):
        """Test extraction of multiple goals with priorities."""
        source = """
public class MyMob extends PathfinderMob {
    @Override
    protected void registerGoals() {
        this.goalSelector.addGoal(0, new FloatGoal(this));
        this.goalSelector.addGoal(1, new MeleeAttackGoal(this, 1.0, true));
        this.goalSelector.addGoal(2, new LookAtPlayerGoal(this, Player.class, 8.0f));
        this.goalSelector.addGoal(3, new RandomStrollGoal(this, 0.8));
    }
}
"""
        tree = self.extractor.parse_java_source(source)
        assert tree is not None

        goals = self.extractor.extract_entity_goals_from_ast(tree)

        assert len(goals) == 4, f"Expected 4 goals, got {len(goals)}"
        priorities = [g["priority"] for g in goals]
        assert 0 in priorities
        assert 1 in priorities

    def test_no_goals_when_no_register_goals(self):
        """Test that goals are empty when no registerGoals method exists."""
        source = """
public class NoGoalsEntity extends PathfinderMob {
    @Override
    protected void someOtherMethod() {
    }
}
"""
        tree = self.extractor.parse_java_source(source)
        goals = self.extractor.extract_entity_goals_from_ast(tree)
        assert goals == [], f"Expected no goals, got {goals}"

    def test_entity_features_include_goals(self):
        """Test that entity features extracted from AST include goals."""
        source = """
public class CustomZombieEntity extends ZombieEntity {
    @Override
    protected void registerGoals() {
        this.goalSelector.addGoal(0, new MeleeAttackGoal(this, 1.0, true));
    }
}
"""
        tree = self.extractor.parse_java_source(source)
        features = self.extractor.extract_features_from_ast(tree)

        assert len(features["entities"]) > 0
        entity = features["entities"][0]
        assert "goals" in entity
        assert len(entity["goals"]) == 1
        assert entity["goals"][0]["type"] == "melee_attack"


class TestUnmappedGoalHandling:
    """Test cases for unmapped goal behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_unmapped_goal_count()

    def test_unmapped_goal_returns_explicit_record(self):
        """Test that unmapped goals return explicit record with _unmapped flag."""
        java_goal = {
            "type": "custom_unknown_goal",
            "priority": 3,
            "config": {"speed_multiplier": 1.0},
        }

        result = convert_java_goal_to_bedrock(java_goal)

        assert "_unmapped" in result
        assert result["_unmapped"] is True
        assert "minecraft:behavior.custom_unknown_goal" in result

    def test_unmapped_goal_preserves_priority(self):
        """Test that unmapped goal preserves priority."""
        java_goal = {"type": "my_custom_goal", "priority": 5}

        result = convert_java_goal_to_bedrock(java_goal)

        assert result["minecraft:behavior.my_custom_goal"]["priority"] == 5

    def test_unmapped_goal_preserves_raw_config(self):
        """Test that unmapped goal preserves raw config."""
        java_goal = {
            "type": " exotic_goal",
            "priority": 2,
            "config": {"custom_param": 42},
        }

        result = convert_java_goal_to_bedrock(java_goal)

        assert "_raw_config" in result["minecraft:behavior.exotic_goal"]
        assert result["minecraft:behavior.exotic_goal"]["_raw_config"]["custom_param"] == 42

    def test_behavior_stats_reports_unmapped(self):
        """Test that get_behavior_stats includes unmapped count."""
        reset_unmapped_goal_count()

        convert_java_goal_to_bedrock({"type": "unknown1", "priority": 1})
        convert_java_goal_to_bedrock({"type": "unknown2", "priority": 2})

        stats = get_behavior_stats()
        assert "unmapped_goal_count" in stats
        assert stats["unmapped_goal_count"] >= 2

    def test_reset_unmapped_goal_count(self):
        """Test that reset_unmapped_goal_count resets the counter."""
        convert_java_goal_to_bedrock({"type": "unknown", "priority": 1})

        reset_unmapped_goal_count()
        stats2 = get_behavior_stats()

        assert stats2["unmapped_goal_count"] == 0

    def test_mapped_goal_does_not_set_unmapped(self):
        """Test that mapped goals do NOT set _unmapped flag."""
        java_goal = {
            "type": "melee_attack",
            "priority": 3,
            "config": {"speed_multiplier": 1.5},
        }

        result = convert_java_goal_to_bedrock(java_goal)

        assert "_unmapped" not in result
        assert "minecraft:behavior.melee_attack" in result


class TestGoalConversionEndToEnd:
    """End-to-end tests for goal conversion."""

    def setup_method(self):
        reset_unmapped_goal_count()

    def test_mixed_vanilla_and_custom_goals(self):
        """Test conversion of mixed vanilla and custom goals."""
        goals = [
            {"type": "melee_attack", "priority": 1, "config": {"speed_multiplier": 1.2}},
            {"type": "wander", "priority": 6, "config": {"speed_multiplier": 0.5}},
            {"type": "custom_special_attack", "priority": 2, "config": {"damage": 10.0}},
        ]

        results = [convert_java_goal_to_bedrock(g) for g in goals]

        mapped = [r for r in results if not r.get("_unmapped")]
        unmapped = [r for r in results if r.get("_unmapped")]

        assert len(mapped) == 2
        assert len(unmapped) == 1
        assert "minecraft:behavior.melee_attack" in mapped[0]
        assert "minecraft:behavior.wander" in mapped[1]

    def test_goal_count_matches_registered(self):
        """Test that output goal count equals registered goal count."""
        registered_goals = [
            {"type": "look_at_player", "priority": 5},
            {"type": "melee_attack", "priority": 3},
            {"type": "wander", "priority": 7},
            {"type": "custom_goal", "priority": 2},
        ]

        output_components = {}
        for goal in registered_goals:
            result = convert_java_goal_to_bedrock(goal)
            for key, val in result.items():
                if key != "_unmapped":
                    output_components[key] = val

        assert len(output_components) == len(registered_goals)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
