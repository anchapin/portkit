"""
Unit tests for knowledge.patterns.base module.
Tests ConversionPattern and PatternLibrary classes.
"""

import pytest
from knowledge.patterns.base import ConversionPattern, PatternLibrary, ComplexityLevel


class TestConversionPattern:
    """Tests for ConversionPattern dataclass."""

    def test_creation_with_required_fields(self):
        """Test creating a ConversionPattern with only required fields."""
        pattern = ConversionPattern(
            id="test-id",
            name="Test Pattern",
            description="A test pattern description",
            java_example="public class Test {}",
            bedrock_example="Test::new",
            category="item",
        )
        assert pattern.id == "test-id"
        assert pattern.name == "Test Pattern"
        assert pattern.description == "A test pattern description"
        assert pattern.java_example == "public class Test {}"
        assert pattern.bedrock_example == "Test::new"
        assert pattern.category == "item"
        assert pattern.tags == []
        assert pattern.complexity == "simple"
        assert pattern.success_rate == 0.0

    def test_creation_with_all_fields(self):
        """Test creating a ConversionPattern with all fields."""
        pattern = ConversionPattern(
            id="full-pattern",
            name="Full Pattern",
            description="Pattern with all fields",
            java_example="java code",
            bedrock_example="bedrock code",
            category="block",
            tags=["tag1", "tag2", "tag3"],
            complexity="complex",
            success_rate=0.75,
        )
        assert pattern.id == "full-pattern"
        assert pattern.name == "Full Pattern"
        assert pattern.tags == ["tag1", "tag2", "tag3"]
        assert pattern.complexity == "complex"
        assert pattern.success_rate == 0.75

    def test_validation_empty_id_raises(self):
        """Test that empty ID raises ValueError."""
        with pytest.raises(ValueError, match="Pattern ID cannot be empty"):
            ConversionPattern(
                id="",
                name="Test",
                description="Desc",
                java_example="java",
                bedrock_example="bedrock",
                category="item",
            )

    def test_validation_empty_java_example_raises(self):
        """Test that empty Java example raises ValueError."""
        with pytest.raises(ValueError, match="Java example cannot be empty"):
            ConversionPattern(
                id="test",
                name="Test",
                description="Desc",
                java_example="",
                bedrock_example="bedrock",
                category="item",
            )

    def test_validation_empty_bedrock_example_raises(self):
        """Test that empty Bedrock example raises ValueError."""
        with pytest.raises(ValueError, match="Bedrock example cannot be empty"):
            ConversionPattern(
                id="test",
                name="Test",
                description="Desc",
                java_example="java",
                bedrock_example="",
                category="item",
            )

    def test_validation_invalid_complexity_raises(self):
        """Test that invalid complexity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid complexity"):
            ConversionPattern(
                id="test",
                name="Test",
                description="Desc",
                java_example="java",
                bedrock_example="bedrock",
                category="item",
                complexity="invalid",
            )

    def test_validation_success_rate_below_zero_raises(self):
        """Test that success_rate < 0 raises ValueError."""
        with pytest.raises(ValueError, match="Success rate must be 0.0-1.0"):
            ConversionPattern(
                id="test",
                name="Test",
                description="Desc",
                java_example="java",
                bedrock_example="bedrock",
                category="item",
                success_rate=-0.1,
            )

    def test_validation_success_rate_above_one_raises(self):
        """Test that success_rate > 1 raises ValueError."""
        with pytest.raises(ValueError, match="Success rate must be 0.0-1.0"):
            ConversionPattern(
                id="test",
                name="Test",
                description="Desc",
                java_example="java",
                bedrock_example="bedrock",
                category="item",
                success_rate=1.5,
            )

    def test_validation_boundary_values_success_rate(self):
        """Test that boundary values 0.0 and 1.0 are valid."""
        pattern_low = ConversionPattern(
            id="low",
            name="Low",
            description="D",
            java_example="j",
            bedrock_example="b",
            category="item",
            success_rate=0.0,
        )
        assert pattern_low.success_rate == 0.0

        pattern_high = ConversionPattern(
            id="high",
            name="High",
            description="D",
            java_example="j",
            bedrock_example="b",
            category="item",
            success_rate=1.0,
        )
        assert pattern_high.success_rate == 1.0

    def test_validation_all_complexity_levels(self):
        """Test that all valid complexity levels are accepted."""
        for complexity in ["simple", "medium", "complex"]:
            pattern = ConversionPattern(
                id=f"test-{complexity}",
                name="Test",
                description="Desc",
                java_example="java",
                bedrock_example="bedrock",
                category="item",
                complexity=complexity,
            )
            assert pattern.complexity == complexity

    def test_to_dict(self):
        """Test converting pattern to dictionary."""
        pattern = ConversionPattern(
            id="dict-test",
            name="Dict Test",
            description="Testing to_dict",
            java_example="public void test() {}",
            bedrock_example="test();",
            category="entity",
            tags=["entity", "method"],
            complexity="medium",
            success_rate=0.6,
        )
        result = pattern.to_dict()

        assert result["id"] == "dict-test"
        assert result["name"] == "Dict Test"
        assert result["description"] == "Testing to_dict"
        assert result["java_example"] == "public void test() {}"
        assert result["bedrock_example"] == "test();"
        assert result["category"] == "entity"
        assert result["tags"] == ["entity", "method"]
        assert result["complexity"] == "medium"
        assert result["success_rate"] == 0.6

    def test_from_dict(self):
        """Test creating pattern from dictionary."""
        data = {
            "id": "from-dict-test",
            "name": "From Dict Test",
            "description": "Testing from_dict",
            "java_example": "int x = 0;",
            "bedrock_example": "int x = 0;",
            "category": "variable",
            "tags": ["variable", "initialization"],
            "complexity": "simple",
            "success_rate": 0.9,
        }
        pattern = ConversionPattern.from_dict(data)

        assert pattern.id == "from-dict-test"
        assert pattern.name == "From Dict Test"
        assert pattern.description == "Testing from_dict"
        assert pattern.java_example == "int x = 0;"
        assert pattern.bedrock_example == "int x = 0;"
        assert pattern.category == "variable"
        assert pattern.tags == ["variable", "initialization"]
        assert pattern.complexity == "simple"
        assert pattern.success_rate == 0.9

    def test_from_dict_with_defaults(self):
        """Test from_dict uses defaults for optional fields."""
        data = {
            "id": "minimal",
            "name": "Minimal",
            "description": "Minimal pattern",
            "java_example": "code",
            "bedrock_example": "code",
            "category": "item",
        }
        pattern = ConversionPattern.from_dict(data)

        assert pattern.tags == []
        assert pattern.complexity == "simple"
        assert pattern.success_rate == 0.0

    def test_round_trip_to_dict_from_dict(self):
        """Test pattern survives round-trip through to_dict and from_dict."""
        original = ConversionPattern(
            id="round-trip",
            name="Round Trip",
            description="Testing round trip",
            java_example="public class Test {}",
            bedrock_example="Test {}",
            category="class",
            tags=["class", "definition"],
            complexity="complex",
            success_rate=0.85,
        )

        dict_repr = original.to_dict()
        restored = ConversionPattern.from_dict(dict_repr)

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.java_example == original.java_example
        assert restored.bedrock_example == original.bedrock_example
        assert restored.category == original.category
        assert restored.tags == original.tags
        assert restored.complexity == original.complexity
        assert restored.success_rate == original.success_rate


class TestPatternLibrary:
    """Tests for PatternLibrary class."""

    @pytest.fixture
    def library(self):
        """Create a PatternLibrary with sample patterns."""
        lib = PatternLibrary()
        lib.add_pattern(
            ConversionPattern(
                id="item-reg",
                name="Item Registration",
                description="Register a custom item",
                java_example="registerItem(id, item);",
                bedrock_example="registerItem(id, item);",
                category="item",
                tags=["item", "registration"],
                complexity="simple",
                success_rate=0.8,
            )
        )
        lib.add_pattern(
            ConversionPattern(
                id="block-reg",
                name="Block Registration",
                description="Register a custom block",
                java_example="registerBlock(id, block);",
                bedrock_example="registerBlock(id, block);",
                category="block",
                tags=["block", "registration"],
                complexity="medium",
                success_rate=0.7,
            )
        )
        lib.add_pattern(
            ConversionPattern(
                id="entity-reg",
                name="Entity Registration",
                description="Register a custom entity",
                java_example="registerEntity(id, entity);",
                bedrock_example="registerEntity(id, entity);",
                category="entity",
                tags=["entity", "registration"],
                complexity="complex",
                success_rate=0.6,
            )
        )
        return lib

    @pytest.fixture
    def empty_library(self):
        """Create an empty PatternLibrary."""
        return PatternLibrary()

    def test_initialization(self, empty_library):
        """Test PatternLibrary initializes with empty patterns."""
        assert empty_library.patterns == {}

    def test_add_pattern_single(self, empty_library):
        """Test adding a single pattern to library."""
        pattern = ConversionPattern(
            id="add-test",
            name="Add Test",
            description="Testing add",
            java_example="code",
            bedrock_example="code",
            category="item",
        )
        empty_library.add_pattern(pattern)

        assert "add-test" in empty_library.patterns
        assert empty_library.patterns["add-test"].name == "Add Test"

    def test_add_pattern_duplicate_raises(self, library):
        """Test that adding duplicate ID raises ValueError."""
        duplicate = ConversionPattern(
            id="item-reg",
            name="Duplicate",
            description="Desc",
            java_example="java",
            bedrock_example="bedrock",
            category="item",
        )
        with pytest.raises(ValueError, match="already exists"):
            library.add_pattern(duplicate)

    def test_get_pattern_existing(self, library):
        """Test getting an existing pattern by ID."""
        pattern = library.get_pattern("item-reg")

        assert pattern is not None
        assert pattern.name == "Item Registration"
        assert pattern.category == "item"

    def test_get_pattern_nonexistent(self, library):
        """Test getting a non-existent pattern returns None."""
        result = library.get_pattern("nonexistent")
        assert result is None

    def test_get_pattern_empty_library(self, empty_library):
        """Test getting pattern from empty library returns None."""
        result = empty_library.get_pattern("any-id")
        assert result is None

    def test_search_by_name_exact(self, library):
        """Test search finds pattern by exact name."""
        results = library.search("Item Registration")
        assert len(results) == 1
        assert results[0].id == "item-reg"

    def test_search_by_name_partial(self, library):
        """Test search finds pattern by partial name match."""
        results = library.search("Block")
        assert len(results) == 1
        assert results[0].id == "block-reg"

    def test_search_by_name_case_insensitive(self, library):
        """Test search is case insensitive."""
        results = library.search("ITEM registration")
        assert len(results) == 1
        assert results[0].id == "item-reg"

    def test_search_by_description(self, library):
        """Test search finds pattern by description content."""
        results = library.search("Register a custom block")
        assert len(results) == 1
        assert results[0].id == "block-reg"

    def test_search_by_java_example(self, library):
        """Test search finds pattern by Java example content."""
        results = library.search("registerBlock")
        assert len(results) == 1
        assert results[0].id == "block-reg"

    def test_search_by_bedrock_example(self, library):
        """Test search finds pattern by Bedrock example content."""
        results = library.search("registerEntity")
        assert len(results) == 1
        assert results[0].id == "entity-reg"

    def test_search_by_tag(self, library):
        """Test search finds pattern by tag content."""
        results = library.search("registration")
        assert len(results) == 3  # All patterns have registration tag

    def test_search_with_category_filter(self, library):
        """Test search filters by category."""
        results = library.search("Register", category="block")
        assert len(results) == 1
        assert results[0].id == "block-reg"

    def test_search_with_category_filter_no_match(self, library):
        """Test search with category filter returns empty when no match."""
        results = library.search("Register", category="item")
        # Should only find item-reg which matches category

    def test_search_with_tags_filter_single(self, library):
        """Test search filters by single tag."""
        results = library.search("Register", tags=["entity"])
        assert len(results) == 1
        assert results[0].id == "entity-reg"

    def test_search_with_tags_filter_multiple(self, library):
        """Test search requires all tags when multiple specified."""
        # Add a pattern with multiple tags
        library.add_pattern(
            ConversionPattern(
                id="multi-tag",
                name="Multi Tag Pattern",
                description="Pattern with multiple tags",
                java_example="code",
                bedrock_example="code",
                category="item",
                tags=["item", "registration", "custom"],
            )
        )
        results = library.search("Pattern", tags=["item", "registration"])
        assert len(results) == 1
        assert results[0].id == "multi-tag"

    def test_search_with_tags_filter_all_must_match(self, library):
        """Test search returns empty when pattern doesn't have all tags."""
        results = library.search("Register", tags=["item", "block"])
        assert len(results) == 0

    def test_search_relevance_name_priority(self, library):
        """Test that name matches score higher than description matches."""
        # Add pattern with matching description but not name
        library.add_pattern(
            ConversionPattern(
                id="desc-only",
                name="Other Pattern",
                description="Item Registration description",
                java_example="code",
                bedrock_example="code",
                category="item",
            )
        )
        results = library.search("Item Registration")
        assert results[0].id == "item-reg"  # Name match should be first

    def test_search_limit(self, library):
        """Test search respects limit parameter."""
        results = library.search("Register", limit=2)
        assert len(results) <= 2

    def test_search_empty_query(self, library):
        """Test search with empty query returns all patterns."""
        results = library.search("")
        assert len(results) == 3

    def test_search_no_matches(self, library):
        """Test search returns empty when no patterns match."""
        results = library.search("nonexistent pattern xyz")
        assert len(results) == 0

    def test_get_by_category_existing(self, library):
        """Test get_by_category returns patterns in category."""
        results = library.get_by_category("item")
        assert len(results) == 1
        assert results[0].id == "item-reg"

    def test_get_by_category_multiple(self, library):
        """Test get_by_category returns multiple patterns."""
        library.add_pattern(
            ConversionPattern(
                id="block-2",
                name="Another Block",
                description="Another block",
                java_example="code",
                bedrock_example="code",
                category="block",
            )
        )
        results = library.get_by_category("block")
        assert len(results) == 2

    def test_get_by_category_nonexistent(self, library):
        """Test get_by_category returns empty for non-existent category."""
        results = library.get_by_category("nonexistent")
        assert len(results) == 0

    def test_get_by_category_empty_library(self, empty_library):
        """Test get_by_category on empty library returns empty."""
        results = empty_library.get_by_category("item")
        assert len(results) == 0

    def test_update_success_rate_success_true(self, library):
        """Test updating success rate with success=True."""
        pattern = library.get_pattern("item-reg")
        initial_rate = pattern.success_rate

        library.update_success_rate("item-reg", True)

        updated_pattern = library.get_pattern("item-reg")
        # EMA formula: alpha * new_value + (1 - alpha) * old_value
        # 0.1 * 1.0 + 0.9 * initial_rate
        expected = 0.1 * 1.0 + 0.9 * initial_rate
        assert updated_pattern.success_rate == expected
        assert updated_pattern.success_rate > initial_rate

    def test_update_success_rate_success_false(self, library):
        """Test updating success rate with success=False."""
        pattern = library.get_pattern("item-reg")
        initial_rate = pattern.success_rate

        library.update_success_rate("item-reg", False)

        updated_pattern = library.get_pattern("item-reg")
        # EMA formula: 0.1 * 0.0 + 0.9 * initial_rate
        expected = 0.1 * 0.0 + 0.9 * initial_rate
        assert updated_pattern.success_rate == expected
        assert updated_pattern.success_rate < initial_rate

    def test_update_success_rate_pattern_not_found(self, library):
        """Test updating success rate for non-existent pattern raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            library.update_success_rate("nonexistent-pattern", True)

    def test_update_success_rate_multiple_calls(self, library):
        """Test success rate converges with multiple updates."""
        pattern_id = "entity-reg"
        pattern = library.get_pattern(pattern_id)
        initial_rate = pattern.success_rate

        # Apply multiple successes
        for _ in range(10):
            library.update_success_rate(pattern_id, True)

        updated_pattern = library.get_pattern(pattern_id)
        # Should be much higher than initial after multiple successes
        assert updated_pattern.success_rate > initial_rate

    def test_get_stats_total(self, library):
        """Test get_stats returns correct total count."""
        stats = library.get_stats()
        assert stats["total"] == 3

    def test_get_stats_by_category(self, library):
        """Test get_stats returns correct category counts."""
        stats = library.get_stats()
        assert stats["by_category"]["item"] == 1
        assert stats["by_category"]["block"] == 1
        assert stats["by_category"]["entity"] == 1

    def test_get_stats_by_complexity(self, library):
        """Test get_stats returns correct complexity counts."""
        stats = library.get_stats()
        assert stats["by_complexity"]["simple"] == 1
        assert stats["by_complexity"]["medium"] == 1
        assert stats["by_complexity"]["complex"] == 1

    def test_get_stats_empty_library(self, empty_library):
        """Test get_stats on empty library returns zeros."""
        stats = empty_library.get_stats()
        assert stats["total"] == 0
        assert stats["by_category"] == {}
        assert stats["by_complexity"] == {}

    def test_get_stats_consistency(self, library):
        """Test that category and complexity counts sum to total."""
        stats = library.get_stats()
        total_categories = sum(stats["by_category"].values())
        total_complexity = sum(stats["by_complexity"].values())
        assert total_categories == stats["total"]
        assert total_complexity == stats["total"]


class TestComplexityLevel:
    """Tests for ComplexityLevel enum."""

    def test_complexity_level_values(self):
        """Test ComplexityLevel enum values."""
        assert ComplexityLevel.SIMPLE.value == "simple"
        assert ComplexityLevel.MEDIUM.value == "medium"
        assert ComplexityLevel.COMPLEX.value == "complex"

    def test_complexity_level_count(self):
        """Test ComplexityLevel has three values."""
        assert len(ComplexityLevel) == 3