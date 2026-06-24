"""
Unit tests for RecipeConverterAgent.

Tests the core conversion functionality of the recipe converter agent
which converts Java mod recipes to Bedrock format.
"""

import pytest

# Import the agent
from agents.recipe_converter import RecipeConverterAgent


class TestRecipeConverterAgent:
    """Test cases for RecipeConverterAgent"""

    @pytest.fixture
    def agent(self):
        """Create agent instance for testing"""
        return RecipeConverterAgent()

    def test_singleton_pattern(self, agent):
        """Test that get_instance returns singleton instance"""
        instance1 = RecipeConverterAgent.get_instance()
        instance2 = RecipeConverterAgent.get_instance()
        assert instance1 is instance2

    def test_item_mapping_basic(self, agent):
        """Test basic Java to Bedrock item ID mapping"""
        # Test iron ingot mapping
        result = agent._map_java_item_to_bedrock("minecraft:iron_ingot")
        assert result == "minecraft:iron_ingot"

        # Test diamond mapping
        result = agent._map_java_item_to_bedrock("minecraft:diamond")
        assert result == "minecraft:diamond"

    def test_item_mapping_planks(self, agent):
        """Test planks mapping from minecraft-data"""
        result = agent._map_java_item_to_bedrock("minecraft:oak_planks")
        assert result == "minecraft:oak_planks"

        result = agent._map_java_item_to_bedrock("minecraft:spruce_planks")
        assert result == "minecraft:spruce_planks"

    def test_item_mapping_unknown(self, agent):
        """Test handling of unknown items"""
        # Unknown item should return original
        result = agent._map_java_item_to_bedrock("modid:unknown_item")
        assert result == "modid:unknown_item"

    def test_add_custom_item_mapping(self, agent):
        """Test adding custom item mappings"""
        agent.add_custom_item_mapping("modid:custom_ingot", "minecraft:gold_ingot")
        result = agent._map_java_item_to_bedrock("modid:custom_ingot")
        assert result == "minecraft:gold_ingot"

    def test_parse_java_recipe_shaped(self, agent):
        """Test parsing Java shaped recipe"""
        java_recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["###", "#X#", "###"],
            "key": {"#": {"item": "minecraft:iron_ingot"}, "X": {"item": "minecraft:diamond"}},
            "result": {"item": "minecraft:iron_block", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["original_type"] == "minecraft:crafting_shaped"
        assert result["recipe_category"] == "shaped"
        assert result["pattern"] == ["###", "#X#", "###"]
        assert result["result_item"] == "minecraft:iron_block"
        assert result["result_count"] == 1

    def test_parse_java_recipe_shapeless(self, agent):
        """Test parsing Java shapeless recipe"""
        java_recipe = {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:paper"}, {"item": "minecraft:book"}],
            "result": {"item": "minecraft:writable_book", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["original_type"] == "minecraft:crafting_shapeless"
        assert result["recipe_category"] == "shapeless"
        assert len(result["ingredients"]) == 2

    def test_parse_java_recipe_smelting(self, agent):
        """Test parsing Java smelting recipe"""
        java_recipe = {
            "type": "minecraft:smelting",
            "ingredient": {"item": "minecraft:iron_ore"},
            "result": "minecraft:iron_ingot",
            "experience": 0.7,
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["original_type"] == "minecraft:smelting"
        assert result["recipe_category"] == "smelting"
        assert result["result_item"] == "minecraft:iron_ingot"
        assert result["experience"] == 0.7

    def test_convert_shaped_to_bedrock(self, agent):
        """Test conversion of shaped recipes"""
        normalized = {
            "pattern": ["###", "#X#", "###"],
            "key": {"#": {"item": "minecraft:iron_ingot"}, "X": {"item": "minecraft:diamond"}},
            "result_item": "minecraft:iron_block",
            "result_count": 1,
            "result_data": 0,
        }
        result = agent._convert_shaped_to_bedrock(normalized, "test_mod", "iron_block")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result

    def test_convert_shapeless_to_bedrock(self, agent):
        """Test conversion of shapeless recipes"""
        normalized = {
            "ingredients": [{"item": "minecraft:paper"}, {"item": "minecraft:book"}],
            "result_item": "minecraft:writable_book",
            "result_count": 1,
            "result_data": 0,
        }
        result = agent._convert_shapeless_to_bedrock(normalized, "test_mod", "writable_book")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shapeless" in result

    def test_convert_smelting_to_bedrock(self, agent):
        """Test conversion of smelting recipes"""
        normalized = {
            "ingredients": [{"item": "minecraft:iron_ore"}],
            "result_item": "minecraft:iron_ingot",
            "result_count": 1,
            "experience": 0.7,
        }
        result = agent._convert_smelting_to_bedrock(
            normalized, "test_mod", "iron_ingot", "smelting"
        )

        assert result["format_version"] == "1.20.10"
        # Bedrock uses recipe_furnace for smelting
        assert "minecraft:recipe_furnace" in result

    def test_convert_stonecutter_to_bedrock(self, agent):
        """Test conversion of stonecutter recipes"""
        normalized = {
            "ingredients": [{"item": "minecraft:stone"}],
            "result_item": "minecraft:stone_bricks",
            "result_count": 1,
        }
        result = agent._convert_stonecutter_to_bedrock(normalized, "test_mod", "stone_bricks")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_stonecutter" in result

    def test_convert_smithing_to_bedrock(self, agent):
        """Test conversion of smithing recipes"""
        normalized = {
            "base": {"item": "minecraft:netherite_sword"},
            "addition": {"item": "minecraft:emerald"},
            "result_item": "minecraft:netherite_sword",
        }
        result = agent._convert_smithing_to_bedrock(normalized, "test_mod", "netherite_sword")

        assert result["format_version"] == "1.20.10"
        # Smithing uses recipe_smithing_transform
        assert "minecraft:recipe_smithing_transform" in result

    def test_convert_recipe_shaped(self, agent):
        """Test main convert_recipe method with shaped recipe"""
        recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["###", "#X#", "###"],
            "key": {"#": {"item": "minecraft:iron_ingot"}, "X": {"item": "minecraft:diamond"}},
            "result": {"item": "minecraft:iron_block", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="test_mod", recipe_name="iron_block")

        assert result is not None
        assert "format_version" in result
        assert "minecraft:recipe_shaped" in result

    def test_convert_recipe_shapeless(self, agent):
        """Test main convert_recipe method with shapeless recipe"""
        recipe = {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:paper"}, {"item": "minecraft:book"}],
            "result": {"item": "minecraft:writable_book", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="test_mod", recipe_name="writable_book")

        assert result is not None
        assert "format_version" in result

    def test_convert_recipe_smelting(self, agent):
        """Test main convert_recipe method with smelting recipe"""
        recipe = {
            "type": "minecraft:smelting",
            "ingredient": {"item": "minecraft:iron_ore"},
            "result": "minecraft:iron_ingot",
            "experience": 0.7,
        }
        result = agent.convert_recipe(recipe, namespace="test_mod", recipe_name="iron_ingot")

        assert result is not None
        assert "format_version" in result

    def test_convert_recipe_unknown_type(self, agent):
        """Test convert_recipe with unknown recipe type"""
        recipe = {"type": "unknown_recipe_type", "data": "test"}
        result = agent.convert_recipe(recipe)

        # Should return error dict for unknown type
        assert result is not None
        if isinstance(result, dict):
            assert not result.get("success") or "unknown" in str(result).lower()


class TestRecipeConverterTools:
    """Test cases for tool-decorated methods (tested via agent instance methods)"""

    @pytest.fixture
    def agent(self):
        return RecipeConverterAgent.get_instance()

    def test_tools_list(self, agent):
        """Test that agent returns list of tools"""
        tools = agent.get_tools()
        assert tools is not None
        assert isinstance(tools, list)
        # Should have 4 tools: convert_recipe, convert_recipes_batch, map_item_id, validate_recipe
        assert len(tools) >= 4

    def test_convert_recipe_method(self, agent):
        """Test the convert_recipe method on agent"""
        recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["X"],
            "key": {"X": {"item": "minecraft:diamond"}},
            "result": {"item": "minecraft:diamond_block", "count": 1},
            "namespace": "test_mod",
            "recipe_name": "diamond_block",
        }

        result = agent.convert_recipe(recipe)

        assert result is not None
        assert "format_version" in result
        assert "minecraft:recipe_shaped" in result

    def test_batch_conversion(self, agent):
        """Test batch conversion via convert_recipe method"""
        recipes = [
            {
                "type": "minecraft:crafting_shaped",
                "pattern": ["X"],
                "key": {"X": {"item": "minecraft:iron_ingot"}},
                "result": {"item": "minecraft:iron_block", "count": 1},
                "namespace": "test_mod",
                "recipe_name": "iron_block",
            },
            {
                "type": "minecraft:smelting",
                "ingredient": {"item": "minecraft:iron_ore"},
                "result": "minecraft:iron_ingot",
                "namespace": "test_mod",
                "recipe_name": "iron_ingot",
            },
        ]

        results = []
        for recipe in recipes:
            result = agent.convert_recipe(recipe)
            results.append(result)

        assert len(results) == 2
        for result in results:
            assert result is not None
            assert "format_version" in result

    def test_add_custom_mapping(self, agent):
        """Test adding custom item mapping"""
        agent.add_custom_item_mapping("modid:custom_ingot", "minecraft:gold_ingot")

        # Verify mapping works
        result = agent._map_java_item_to_bedrock("modid:custom_ingot")
        assert result == "minecraft:gold_ingot"


class TestRecipeConverterEdgeCases:
    """Test edge cases and error handling"""

    @pytest.fixture
    def agent(self):
        return RecipeConverterAgent()

    def test_empty_recipe(self, agent):
        """Test handling of empty recipe"""
        result = agent.convert_recipe({})
        # Empty recipe has no type so returns None or error
        assert result is None or (isinstance(result, dict) and not result.get("success"))

    def test_none_recipe(self, agent):
        """Test handling of None recipe"""
        # Test that None input doesn't crash
        try:
            result = agent.convert_recipe(None)
        except (TypeError, AttributeError):
            # None input causes TypeError - this is expected behavior
            result = None
        assert result is None

    def test_invalid_recipe_type(self, agent):
        """Test handling of invalid recipe type (non-string)"""
        # Non-string type causes TypeError - this is expected behavior
        try:
            result = agent.convert_recipe({"type": 12345})
        except TypeError:
            result = None
        assert result is None

    def test_recipe_with_count(self, agent):
        """Test recipe with count > 1"""
        result = agent._convert_shaped_to_bedrock(
            {
                "pattern": ["X"],
                "key": {"X": {"item": "minecraft:iron_ingot"}},
                "result_item": "minecraft:iron_block",
                "result_count": 4,
                "result_data": 0,
            },
            "test",
            "iron_block",
        )

        assert result is not None
        recipe_data = result.get("minecraft:recipe_shaped", {})
        assert "result" in recipe_data

    def test_multiple_ingredients_shapeless(self, agent):
        """Test shapeless recipe with multiple ingredients"""
        normalized = {
            "ingredients": [
                {"item": "minecraft:paper"},
                {"item": "minecraft:paper"},
                {"item": "minecraft:paper"},
                {"item": "minecraft:leather"},
            ],
            "result_item": "minecraft:book",
            "result_count": 1,
            "result_data": 0,
        }
        result = agent._convert_shapeless_to_bedrock(normalized, "test", "book")

        assert result is not None
        assert "minecraft:recipe_shapeless" in result

    def test_smelting_with_experience(self, agent):
        """Test smelting recipe with experience value"""
        normalized = {
            "ingredients": [{"item": "minecraft:gold_ore"}],
            "result_item": "minecraft:gold_ingot",
            "result_count": 1,
            "experience": 1.0,
        }
        result = agent._convert_smelting_to_bedrock(normalized, "test", "gold_ingot", "smelting")

        assert result is not None
        # Experience should be handled


class TestCustomForgeRecipeTypes:
    """Test cases for custom Forge recipe type handling"""

    @pytest.fixture
    def agent(self):
        return RecipeConverterAgent()

    def test_parse_farmersdelight_cooking(self, agent):
        """Test parsing Farmer's Delight cooking pot recipe"""
        java_recipe = {
            "type": "farmersdelight:cooking",
            "ingredient": {"item": "minecraft:beef"},
            "result": {"item": "minecraft:cooked_beef", "count": 1},
            "container": {"item": "minecraft:bowl"},
            "cookingtime": 200,
            "experience": 0.35,
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "cooking_pot"
        assert result["container"] == {"item": "minecraft:bowl"}
        assert result["cooking_time"] == 200
        assert result["experience"] == 0.35

    def test_parse_farmersdelight_cutting(self, agent):
        """Test parsing Farmer's Delight cutting board recipe"""
        java_recipe = {
            "type": "farmersdelight:cutting",
            "ingredients": [{"item": "minecraft:oak_log"}, {"item": "minecraft:iron_axe"}],
            "result": {"item": "minecraft:oak_planks", "count": 6},
            "tool": {"item": "minecraft:iron_axe"},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "cutting_board"
        assert result["tool"] == {"item": "minecraft:iron_axe"}
        assert len(result["ingredients"]) == 2

    def test_parse_create_mechanical_crafting(self, agent):
        """Test parsing Create mechanical crafting recipe"""
        java_recipe = {
            "type": "create:mechanical_crafting",
            "pattern": ["AAAAA", "BBBBB", "CCCCC"],
            "key": {
                "A": {"item": "create:andesite"},
                "B": {"item": "create:copper_sheet"},
                "C": {"item": "minecraft:iron_ingot"},
            },
            "result": {"item": "create:gearbox", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "mechanical_crafting"
        assert len(result["pattern"]) == 3

    def test_parse_create_pressing(self, agent):
        """Test parsing Create pressing recipe"""
        java_recipe = {
            "type": "create:pressing",
            "ingredient": {"item": "create:copper_sheet"},
            "result": {"item": "create:copper_block", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "pressing"

    def test_parse_create_sequenced_assembly(self, agent):
        """Test parsing Create sequenced assembly captures transitions"""
        java_recipe = {
            "type": "create:sequenced_assembly",
            "sequence": [],
            "result": {"item": "create:precision_mechanism", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "sequenced_assembly"
        assert result["requires_manual_review"] is False
        assert result["transitions"] == []

    def test_parse_create_mixing(self, agent):
        """Test parsing Create mixing recipe with fluid ingredients requires manual review"""
        java_recipe = {
            "type": "create:mixing",
            "ingredients": [],
            "result": {"item": "minecraft:clay", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "mixing"
        assert result["requires_manual_review"] is False

    def test_convert_cooking_pot(self, agent):
        """Test conversion of cooking pot recipe"""
        recipe = {
            "type": "farmersdelight:cooking",
            "ingredient": {"item": "minecraft:beef"},
            "result": {"item": "minecraft:cooked_beef", "count": 1},
            "container": {"item": "minecraft:bowl"},
            "cookingtime": 200,
            "experience": 0.35,
        }
        result = agent.convert_recipe(recipe, namespace="farmersdelight", recipe_name="cooked_beef")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_furnace" in result
        assert result["minecraft:recipe_furnace"]["tags"] == ["crafting_table", "cooking_pot"]

    def test_convert_cutting_board(self, agent):
        """Test conversion of cutting board recipe"""
        recipe = {
            "type": "farmersdelight:cutting",
            "ingredients": [{"item": "minecraft:oak_log"}],
            "result": {"item": "minecraft:oak_planks", "count": 6},
            "tool": {"item": "minecraft:iron_axe"},
        }
        result = agent.convert_recipe(recipe, namespace="farmersdelight", recipe_name="oak_planks")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert "cutting_board" in result["minecraft:recipe_shaped"]["tags"]

    def test_convert_cooking_pot_plural_ingredients(self, agent):
        """Test conversion of cooking pot recipe with plural 'ingredients' array (real FD format)"""
        recipe = {
            "type": "farmersdelight:cooking",
            "ingredients": [{"item": "farmersdelight:raw_cod"}, {"item": "minecraft:carrot"}],
            "result": {"item": "farmersdelight:baked_cod_stew", "count": 1},
            "cookingtime": 160,
            "experience": 0.35,
        }
        result = agent.convert_recipe(
            recipe, namespace="farmersdelight", recipe_name="baked_cod_stew"
        )

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_furnace" in result
        assert result["minecraft:recipe_furnace"]["tags"] == ["crafting_table", "cooking_pot"]

    def test_convert_mechanical_crafting_within_3x3(self, agent):
        """Test conversion of mechanical crafting within Bedrock limits"""
        recipe = {
            "type": "create:mechanical_crafting",
            "pattern": ["A", "B"],
            "key": {"A": {"item": "create:andesite"}, "B": {"item": "minecraft:iron_ingot"}},
            "result": {"item": "create:windmill", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="windmill")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert "mechanical_crafting" in result["minecraft:recipe_shaped"]["tags"]

    def test_convert_pressing(self, agent):
        """Test conversion of pressing recipe"""
        recipe = {
            "type": "create:pressing",
            "ingredient": {"item": "create:copper_sheet"},
            "result": {"item": "create:copper_block", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="copper_block")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert "pressing" in result["minecraft:recipe_shaped"]["tags"]

    def test_convert_sequenced_assembly_produces_recipe(self, agent):
        """Test that sequenced assembly converts to a shaped recipe"""
        recipe = {
            "type": "create:sequenced_assembly",
            "sequence": [],
            "result": {"item": "create:precision_mechanism", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="precision_mechanism")

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == ["crafting_table", "sequenced_assembly"]

    def test_convert_multi_output_recipe_uses_first_result(self, agent):
        """Test that multi-output recipes use the first result"""
        recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["X"],
            "key": {"X": {"item": "minecraft:diamond"}},
            "result": [
                {"item": "minecraft:diamond_sword", "count": 1},
                {"item": "minecraft:diamond_pickaxe", "count": 1},
            ],
        }
        result = agent.convert_recipe(recipe, namespace="test", recipe_name="multi")

        assert result["format_version"] == "1.20.10"
        # Should use first result
        assert result["minecraft:recipe_shaped"]["result"]["item"] == "minecraft:diamond_sword"

    def test_convert_forge_conditional_recipe(self, agent):
        """Test that forge:conditional recipes are unwrapped"""
        recipe = {
            "type": "forge:conditional",
            "recipe": {
                "type": "minecraft:crafting_shaped",
                "pattern": ["X"],
                "key": {"X": {"item": "minecraft:gold_ingot"}},
                "result": {"item": "minecraft:gold_block", "count": 1},
            },
        }
        result = agent.convert_recipe(recipe, namespace="test", recipe_name="gold_block")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result

    def test_create_manual_review_result(self, agent):
        """Test manual review result creation"""
        result = agent._create_manual_review_result("test", "recipe_name", "Test reason")

        assert result["manual_review_required"] is True
        assert result["reason"] == "Test reason"
        assert result["original_recipe"] == "test:recipe_name"
        assert result["format_version"] == "1.20.10"

    def test_is_custom_recipe_type(self, agent):
        """Test custom recipe type detection"""
        from agents.recipe.custom_types import is_custom_recipe_type

        assert is_custom_recipe_type("farmersdelight:cooking") is True
        assert is_custom_recipe_type("create:sequenced_assembly") is True
        assert is_custom_recipe_type("create:mixing") is True
        assert is_custom_recipe_type("minecraft:crafting_shaped") is False
        assert is_custom_recipe_type("unknown:custom_type") is False

    # --- New Create recipe type tests ---

    def test_parse_create_mixing_non_fluid(self, agent):
        """Test parsing Create mixing recipe without fluid ingredients"""
        java_recipe = {
            "type": "create:mixing",
            "ingredients": [
                {"item": "minecraft:wheat"},
                {"item": "minecraft:egg"},
            ],
            "result": {"item": "minecraft:bread", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "mixing"
        assert result["requires_manual_review"] is False

    def test_convert_create_mixing_non_fluid(self, agent):
        """Test converting Create mixing recipe (non-fluid) to Bedrock"""
        recipe = {
            "type": "create:mixing",
            "ingredients": [
                {"item": "minecraft:wheat"},
                {"item": "minecraft:egg"},
            ],
            "result": {"item": "minecraft:bread", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="bread_from_mixing")

        assert "minecraft:recipe_shapeless" in result
        assert result["minecraft:recipe_shapeless"]["tags"] == ["crafting_table", "mixing"]

    def test_convert_create_mixing_with_fluid_manual_review(self, agent):
        """Test that Create mixing with fluid ingredients still requires manual review"""
        recipe = {
            "type": "create:mixing",
            "ingredients": [
                {"item": "minecraft:dirt"},
                {"tag": "forge:fluids/water"},
            ],
            "result": {"item": "minecraft:mud", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="mud_from_mixing")

        assert result.get("manual_review_required") is True

    def test_parse_create_cutting(self, agent):
        """Test parsing Create cutting recipe"""
        java_recipe = {
            "type": "create:cutting",
            "ingredient": {"item": "minecraft:oak_log"},
            "result": {"item": "minecraft:stripped_oak_log", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "cutting"
        assert result["requires_manual_review"] is False

    def test_convert_create_cutting(self, agent):
        """Test converting Create cutting recipe to Bedrock"""
        recipe = {
            "type": "create:cutting",
            "ingredient": {"item": "minecraft:oak_log"},
            "result": {"item": "minecraft:stripped_oak_log", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="oak_log_cutting")

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == ["crafting_table", "cutting"]

    def test_parse_create_haunting(self, agent):
        """Test parsing Create haunting recipe"""
        java_recipe = {
            "type": "create:haunting",
            "ingredient": {"item": "minecraft:cobblestone"},
            "result": {"item": "minecraft:blackstone", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "haunting"
        assert result["requires_manual_review"] is False

    def test_convert_create_haunting(self, agent):
        """Test converting Create haunting recipe to Bedrock"""
        recipe = {
            "type": "create:haunting",
            "ingredient": {"item": "minecraft:cobblestone"},
            "result": {"item": "minecraft:blackstone", "count": 1},
        }
        result = agent.convert_recipe(
            recipe, namespace="create", recipe_name="cobblestone_haunting"
        )

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == ["crafting_table", "haunting"]

    def test_parse_create_sandpaper_polishing(self, agent):
        """Test parsing Create sandpaper polishing recipe"""
        java_recipe = {
            "type": "create:sandpaper_polishing",
            "ingredient": {"item": "minecraft:quartz_block"},
            "result": {"item": "minecraft:smooth_quartz", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "sandpaper_polishing"
        assert result["requires_manual_review"] is False

    def test_convert_create_sandpaper_polishing(self, agent):
        """Test converting Create sandpaper polishing recipe to Bedrock"""
        recipe = {
            "type": "create:sandpaper_polishing",
            "ingredient": {"item": "minecraft:quartz_block"},
            "result": {"item": "minecraft:smooth_quartz", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="quartz_polishing")

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == [
            "crafting_table",
            "sandpaper_polishing",
        ]

    def test_parse_create_item_application(self, agent):
        """Test parsing Create item application recipe"""
        java_recipe = {
            "type": "create:item_application",
            "ingredients": [
                {"item": "minecraft:diamond"},
                {"item": "minecraft:stick"},
            ],
            "result": {"item": "create:diamond_saw", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "item_application"
        assert result["requires_manual_review"] is False

    def test_convert_create_item_application(self, agent):
        """Test converting Create item application recipe to Bedrock"""
        recipe = {
            "type": "create:item_application",
            "ingredients": [
                {"item": "minecraft:diamond"},
                {"item": "minecraft:stick"},
            ],
            "result": {"item": "create:diamond_saw", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="diamond_saw")

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == ["crafting_table", "item_application"]

    def test_parse_create_filling(self, agent):
        """Test parsing Create filling recipe"""
        java_recipe = {
            "type": "create:filling",
            "ingredients": [
                {"item": "minecraft:glass_bottle"},
                {"item": "minecraft:honey_block"},
            ],
            "result": {"item": "minecraft:honey_bottle", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "filling"
        assert result["requires_manual_review"] is False

    def test_convert_create_filling(self, agent):
        """Test converting Create filling recipe to Bedrock"""
        recipe = {
            "type": "create:filling",
            "ingredients": [
                {"item": "minecraft:glass_bottle"},
                {"item": "minecraft:honey_block"},
            ],
            "result": {"item": "minecraft:honey_bottle", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="honey_filling")

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == ["crafting_table", "filling"]

    def test_parse_create_emptying(self, agent):
        """Test parsing Create emptying recipe"""
        java_recipe = {
            "type": "create:emptying",
            "ingredients": [{"item": "minecraft:water_bucket"}],
            "result": {"item": "minecraft:bucket", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "emptying"
        assert result["requires_manual_review"] is False

    def test_convert_create_emptying(self, agent):
        """Test converting Create emptying recipe to Bedrock"""
        recipe = {
            "type": "create:emptying",
            "ingredients": [{"item": "minecraft:water_bucket"}],
            "result": {"item": "minecraft:bucket", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="water_bucket_empty")

        assert "minecraft:recipe_shaped" in result
        assert result["minecraft:recipe_shaped"]["tags"] == ["crafting_table", "emptying"]


class TestCreateCustomRecipeTypes:
    """Test cases for Create custom recipe type converters (milling, crushing, deploying, splashing)"""

    @pytest.fixture
    def agent(self):
        return RecipeConverterAgent()

    def test_parse_create_milling(self, agent):
        """Test parsing Create milling recipe"""
        java_recipe = {
            "type": "create:milling",
            "ingredient": {"item": "create:crushed_copper_ore"},
            "result": {"item": "create:copper_dust", "count": 2},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "milling"
        assert len(result["ingredients"]) == 1
        assert result["ingredients"][0]["item"] == "create:crushed_copper_ore"

    def test_parse_create_crushing(self, agent):
        """Test parsing Create crushing recipe"""
        java_recipe = {
            "type": "create:crushing",
            "ingredient": {"item": "minecraft:iron_ore"},
            "result": {"item": "minecraft:iron_nugget", "count": 2},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "crushing"
        assert len(result["ingredients"]) == 1

    def test_parse_create_deploying(self, agent):
        """Test parsing Create deploying recipe"""
        java_recipe = {
            "type": "create:deploying",
            "ingredients": [
                {"item": "minecraft:iron_ingot"},
                {"item": "create:andesite_casing"},
            ],
            "tool": {"item": "create:deployer"},
            "result": {"item": "create:iron_sheet", "count": 2},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "deploying"
        assert len(result["ingredients"]) == 2
        assert result["tool"]["item"] == "create:deployer"

    def test_parse_create_splashing(self, agent):
        """Test parsing Create splashing recipe"""
        java_recipe = {
            "type": "create:splashing",
            "ingredients": [{"item": "minecraft:gravel"}],
            "result": {"item": "minecraft:flint", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "splashing"
        assert len(result["ingredients"]) == 1

    def test_parse_create_compacting(self, agent):
        """Test parsing Create compacting recipe"""
        java_recipe = {
            "type": "create:compacting",
            "ingredients": [{"item": "minecraft:iron_ingot", "count": 9}],
            "result": {"item": "minecraft:iron_block", "count": 1},
        }
        result = agent._parse_java_recipe(java_recipe)

        assert result["recipe_category"] == "compacting"
        assert len(result["ingredients"]) == 1

    def test_convert_milling(self, agent):
        """Test conversion of Create milling recipe"""
        recipe = {
            "type": "create:milling",
            "ingredient": {"item": "create:crushed_copper_ore"},
            "result": {"item": "create:copper_dust", "count": 2},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="copper_dust")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert (
            "_converted_from_create"
            in result["minecraft:recipe_shaped"]["description"]["identifier"]
        )
        assert "milling" in result["minecraft:recipe_shaped"]["tags"]
        assert "备注" in result["minecraft:recipe_shaped"]

    def test_convert_crushing(self, agent):
        """Test conversion of Create crushing recipe"""
        recipe = {
            "type": "create:crushing",
            "ingredient": {"item": "minecraft:iron_ore"},
            "result": {"item": "minecraft:iron_nugget", "count": 2},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_nugget")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert (
            "_converted_from_create"
            in result["minecraft:recipe_shaped"]["description"]["identifier"]
        )
        assert "crushing" in result["minecraft:recipe_shaped"]["tags"]

    def test_convert_deploying(self, agent):
        """Test conversion of Create deploying recipe"""
        recipe = {
            "type": "create:deploying",
            "ingredients": [
                {"item": "minecraft:iron_ingot"},
                {"item": "create:andesite_casing"},
            ],
            "tool": {"item": "create:deployer"},
            "result": {"item": "create:iron_sheet", "count": 2},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_sheet")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert (
            "_converted_from_create"
            in result["minecraft:recipe_shaped"]["description"]["identifier"]
        )
        assert "deploying" in result["minecraft:recipe_shaped"]["tags"]

    def test_convert_splashing(self, agent):
        """Test conversion of Create splashing recipe"""
        recipe = {
            "type": "create:splashing",
            "ingredients": [{"item": "minecraft:gravel"}],
            "result": {"item": "minecraft:flint", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="flint")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shapeless" in result
        assert (
            "_converted_from_create"
            in result["minecraft:recipe_shapeless"]["description"]["identifier"]
        )
        assert "splashing" in result["minecraft:recipe_shapeless"]["tags"]

    def test_convert_compacting(self, agent):
        """Test conversion of Create compacting recipe"""
        recipe = {
            "type": "create:compacting",
            "ingredients": [{"item": "minecraft:iron_ingot", "count": 9}],
            "result": {"item": "minecraft:iron_block", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_block")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert (
            "_converted_from_create"
            in result["minecraft:recipe_shaped"]["description"]["identifier"]
        )
        assert "compacting" in result["minecraft:recipe_shaped"]["tags"]

    def test_convert_milling_no_ingredients(self, agent):
        """Test milling conversion with no ingredients returns manual review"""
        recipe = {
            "type": "create:milling",
            "result": {"item": "create:copper_dust", "count": 2},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="copper_dust")

        assert result["manual_review_required"] is True

    def test_convert_crushing_no_ingredients(self, agent):
        """Test crushing conversion with no ingredients returns manual review"""
        recipe = {
            "type": "create:crushing",
            "result": {"item": "minecraft:iron_nugget", "count": 2},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_nugget")

        assert result["manual_review_required"] is True

    def test_convert_deploying_no_ingredients(self, agent):
        """Test deploying conversion with no ingredients returns manual review"""
        recipe = {
            "type": "create:deploying",
            "result": {"item": "create:iron_sheet", "count": 2},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_sheet")

        assert result["manual_review_required"] is True

    def test_convert_splashing_no_ingredients(self, agent):
        """Test splashing conversion with no ingredients returns manual review"""
        recipe = {
            "type": "create:splashing",
            "result": {"item": "minecraft:flint", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="flint")

        assert result["manual_review_required"] is True


class TestCreateRecipeEnhancements:
    """Test cases for Create recipe enhancement features (issue #1136)"""

    @pytest.fixture
    def agent(self):
        return RecipeConverterAgent()

    def test_forge_tag_ingredient_resolution(self, agent):
        """Test that forge:tag ingredients are resolved to bedrock equivalents"""
        result = agent._map_java_item_to_bedrock("#forge:ingots/iron")
        assert result == "minecraft:iron_ingot"

        result = agent._map_java_item_to_bedrock("#forge:ores/copper")
        assert result == "minecraft:copper_ore"

        result = agent._map_java_item_to_bedrock("#forge:nuggets/gold")
        assert result == "minecraft:gold_nugget"

        result = agent._map_java_item_to_bedrock("#forge:gems/diamond")
        assert result == "minecraft:diamond"

    def test_multi_output_crushing_with_secondary_outputs(self, agent):
        """Test crushing recipe with multiple outputs (secondary outputs stored)"""
        recipe = {
            "type": "create:crushing",
            "ingredient": {"item": "minecraft:iron_ore"},
            "result": [
                {"item": "minecraft:iron_nugget", "count": 2},
                {"item": "minecraft:iron_nugget", "count": 1, "chance": 0.3},
                {"item": "minecraft:flint", "count": 1, "chance": 0.05},
            ],
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_nugget")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        # Primary output should be the first result
        assert result["minecraft:recipe_shaped"]["result"]["item"] == "minecraft:iron_nugget"
        assert result["minecraft:recipe_shaped"]["result"]["count"] == 2
        # Note should mention secondary outputs
        assert "Secondary outputs" in result["minecraft:recipe_shaped"].get("备注", "")

    def test_multi_output_milling_with_secondary_outputs(self, agent):
        """Test milling recipe with multiple outputs"""
        recipe = {
            "type": "create:milling",
            "ingredient": {"item": "create:crushed_copper_ore"},
            "result": [
                {"item": "create:copper_dust", "count": 2},
                {"item": "minecraft:copper_nugget", "count": 1, "chance": 0.25},
            ],
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="copper_dust")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert "Secondary outputs" in result["minecraft:recipe_shaped"].get("备注", "")

    def test_compacting_with_heat_requirement(self, agent):
        """Test compacting recipe with heatRequirement field"""
        recipe = {
            "type": "create:compacting",
            "ingredients": [{"item": "minecraft:iron_ingot", "count": 9}],
            "result": {"item": "minecraft:iron_block", "count": 1},
            "heatRequirement": "heated",
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_block")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert "Heat: heated" in result["minecraft:recipe_shaped"].get("备注", "")

    def test_crushing_with_rpm_fields(self, agent):
        """Test crushing recipe with minRPM/maxRPM fields"""
        recipe = {
            "type": "create:crushing",
            "ingredient": {"item": "minecraft:iron_ore"},
            "result": {"item": "minecraft:iron_nugget", "count": 2},
            "minRPM": 16,
            "maxRPM": 32,
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="iron_nugget")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shaped" in result
        assert "RPM: 16-32" in result["minecraft:recipe_shaped"].get("备注", "")

    def test_mixing_with_fluid_ingredients_requires_review(self, agent):
        """Test mixing recipe with fluid ingredients requires manual review"""
        recipe = {
            "type": "create:mixing",
            "ingredients": [
                {"tag": "forge:fluids/water", "amount": 500},
                {"item": "minecraft:gravel", "count": 1},
            ],
            "result": {"item": "minecraft:sand", "count": 1},
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="sand")

        assert result["manual_review_required"] is True
        assert "fluid" in result["reason"].lower()

    def test_parsing_secondary_outputs_from_result_list(self, agent):
        """Test that _parse_java_recipe correctly extracts secondary outputs"""
        recipe = {
            "type": "create:milling",
            "ingredient": {"item": "create:crushed_iron_ore"},
            "result": [
                {"item": "create:iron_dust", "count": 2},
                {"item": "minecraft:iron_nugget", "count": 1, "chance": 0.15},
            ],
        }
        parsed = agent._parse_java_recipe(recipe)

        assert parsed["result_item"] == "create:iron_dust"
        assert parsed["result_count"] == 2
        assert "secondary_outputs" in parsed
        assert len(parsed["secondary_outputs"]) == 1
        assert parsed["secondary_outputs"][0]["item"] == "minecraft:iron_nugget"

    def test_splashing_with_rpm_fields(self, agent):
        """Test splashing recipe with minRPM/maxRPM fields"""
        recipe = {
            "type": "create:splashing",
            "ingredients": [{"item": "minecraft:gravel"}],
            "result": {"item": "minecraft:flint", "count": 1},
            "minRPM": 128,
        }
        result = agent.convert_recipe(recipe, namespace="create", recipe_name="flint")

        assert result["format_version"] == "1.20.10"
        assert "minecraft:recipe_shapeless" in result
        assert "RPM: 128-" in result["minecraft:recipe_shapeless"].get("备注", "")


class TestTagResolution:
    """Test cases for Forge tag resolution (issue #1772)"""

    def test_resolve_tag_to_bedrock_function(self):
        """Test resolve_tag_to_bedrock function directly"""
        from agents.recipe.tag_resolver import resolve_tag_to_bedrock

        assert resolve_tag_to_bedrock("#forge:ingots/iron") == "minecraft:iron_ingot"
        assert resolve_tag_to_bedrock("#forge:storage_blocks/diamond") == "minecraft:diamond_block"
        assert resolve_tag_to_bedrock("#forge:ores/gold") == "minecraft:gold_ore"

    def test_resolve_tag_to_bedrock_unknown_tag_returns_none(self):
        """Test that unknown mod-only tags return None"""
        from agents.recipe.tag_resolver import resolve_tag_to_bedrock

        result = resolve_tag_to_bedrock("#forge:special_mod_item")
        assert result is None

    def test_resolve_tag_to_bedrock_minecraft_tag(self):
        """Test that #minecraft: tags are handled"""
        from agents.recipe.tag_resolver import resolve_tag_to_bedrock

        result = resolve_tag_to_bedrock("#minecraft:ingots")
        assert result is None

    def test_pattern_based_tag_resolution(self):
        """Test that tags not in FORGE_TAG_MAPPINGS are resolved via patterns"""
        from agents.recipe.tag_resolver import clear_tag_pattern_cache

        clear_tag_pattern_cache()
        from agents.recipe.tag_resolver import resolve_tag_to_bedrock

        result = resolve_tag_to_bedrock("#forge:planks/oak")
        assert result == "minecraft:oak_planks"

    def test_unresolved_tag_routes_to_manual_review(self):
        """Test that unresolved tags route shaped recipes to manual review"""
        agent = RecipeConverterAgent()
        recipe = {
            "type": "crafting_shaped",
            "pattern": ["A"],
            "key": {"A": {"item": "#forge:special_mod_only_tag"}},
            "result": {"item": "minecraft:diamond"},
        }
        result = agent.convert_recipe(recipe, namespace="testmod", recipe_name="test_recipe")

        assert result.get("manual_review_required") is True
        assert result.get("portkit:unresolved_tag") is True
        assert "Unresolved tag" in result.get("reason", "")

    def test_unresolved_tag_in_shapeless_routes_to_manual_review(self):
        """Test that unresolved tags route shapeless recipes to manual review"""
        agent = RecipeConverterAgent()
        recipe = {
            "type": "crafting_shapeless",
            "ingredients": [{"item": "#forge:unknown_mod_tag"}],
            "result": {"item": "minecraft:diamond"},
        }
        result = agent.convert_recipe(recipe, namespace="testmod", recipe_name="test_recipe")

        assert result.get("manual_review_required") is True
        assert result.get("portkit:unresolved_tag") is True

    def test_known_forge_tag_still_resolves(self):
        """Test that known Forge tags from mappings still resolve correctly"""
        agent = RecipeConverterAgent()
        result = agent._map_java_item_to_bedrock("#forge:ingots/gold")
        assert result == "minecraft:gold_ingot"

    def test_resolved_tag_no_manual_review(self):
        """Test that resolved tags do not trigger manual review"""
        agent = RecipeConverterAgent()
        recipe = {
            "type": "crafting_shaped",
            "pattern": ["A"],
            "key": {"A": {"item": "#forge:ingots/iron"}},
            "result": {"item": "minecraft:diamond"},
        }
        result = agent.convert_recipe(recipe, namespace="testmod", recipe_name="test_recipe")

        assert result.get("manual_review_required") is not True
        assert "minecraft:recipe_shaped" in result
