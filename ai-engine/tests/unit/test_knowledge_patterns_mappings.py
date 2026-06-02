"""
Unit tests for knowledge/patterns/mappings.py
Tests PatternMapping dataclass and PatternMappingRegistry.
"""

import pytest
from knowledge.patterns.mappings import (
    PatternMapping,
    PatternMappingRegistry,
    MappingConfidence,
)


class TestPatternMappingInit:
    """Tests for PatternMapping dataclass initialization and validation."""

    def test_pattern_mapping_creation_with_all_fields(self):
        """Test creating PatternMapping with all fields specified."""
        mapping = PatternMapping(
            java_pattern_id="java_test_pattern",
            bedrock_pattern_id="bedrock_test_pattern",
            confidence=0.85,
            notes="Test notes here",
            limitations=["limitation 1", "limitation 2"],
            requires_manual_review=True,
        )
        assert mapping.java_pattern_id == "java_test_pattern"
        assert mapping.bedrock_pattern_id == "bedrock_test_pattern"
        assert mapping.confidence == 0.85
        assert mapping.notes == "Test notes here"
        assert mapping.limitations == ["limitation 1", "limitation 2"]
        assert mapping.requires_manual_review is True

    def test_pattern_mapping_creation_with_defaults(self):
        """Test creating PatternMapping with only required fields."""
        mapping = PatternMapping(
            java_pattern_id="java_minimal",
            bedrock_pattern_id="bedrock_minimal",
            confidence=0.75,
        )
        assert mapping.java_pattern_id == "java_minimal"
        assert mapping.bedrock_pattern_id == "bedrock_minimal"
        assert mapping.confidence == 0.75
        assert mapping.notes == ""
        assert mapping.limitations == []
        assert mapping.requires_manual_review is False

    def test_pattern_mapping_validation_empty_java_id(self):
        """Test that empty java_pattern_id raises ValueError."""
        with pytest.raises(ValueError, match="Java pattern ID cannot be empty"):
            PatternMapping(
                java_pattern_id="",
                bedrock_pattern_id="bedrock_id",
                confidence=0.5,
            )

    def test_pattern_mapping_validation_empty_bedrock_id(self):
        """Test that empty bedrock_pattern_id raises ValueError."""
        with pytest.raises(ValueError, match="Bedrock pattern ID cannot be empty"):
            PatternMapping(
                java_pattern_id="java_id",
                bedrock_pattern_id="",
                confidence=0.5,
            )

    def test_pattern_mapping_validation_confidence_below_zero(self):
        """Test that confidence < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
            PatternMapping(
                java_pattern_id="java_id",
                bedrock_pattern_id="bedrock_id",
                confidence=-0.1,
            )

    def test_pattern_mapping_validation_confidence_above_one(self):
        """Test that confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
            PatternMapping(
                java_pattern_id="java_id",
                bedrock_pattern_id="bedrock_id",
                confidence=1.5,
            )

    def test_pattern_mapping_validation_confidence_boundary_zero(self):
        """Test that confidence = 0.0 is valid."""
        mapping = PatternMapping(
            java_pattern_id="java_id",
            bedrock_pattern_id="bedrock_id",
            confidence=0.0,
        )
        assert mapping.confidence == 0.0

    def test_pattern_mapping_validation_confidence_boundary_one(self):
        """Test that confidence = 1.0 is valid."""
        mapping = PatternMapping(
            java_pattern_id="java_id",
            bedrock_pattern_id="bedrock_id",
            confidence=1.0,
        )
        assert mapping.confidence == 1.0

    def test_pattern_mapping_to_dict(self):
        """Test converting PatternMapping to dictionary."""
        mapping = PatternMapping(
            java_pattern_id="java_dict",
            bedrock_pattern_id="bedrock_dict",
            confidence=0.8,
            notes="Dict test notes",
            limitations=["limit 1"],
            requires_manual_review=True,
        )
        result = mapping.to_dict()
        assert result["java_pattern_id"] == "java_dict"
        assert result["bedrock_pattern_id"] == "bedrock_dict"
        assert result["confidence"] == 0.8
        assert result["notes"] == "Dict test notes"
        assert result["limitations"] == ["limit 1"]
        assert result["requires_manual_review"] is True

    def test_pattern_mapping_from_dict(self):
        """Test creating PatternMapping from dictionary."""
        data = {
            "java_pattern_id": "java_from_dict",
            "bedrock_pattern_id": "bedrock_from_dict",
            "confidence": 0.7,
            "notes": "From dict notes",
            "limitations": ["from dict limit"],
            "requires_manual_review": True,
        }
        mapping = PatternMapping.from_dict(data)
        assert mapping.java_pattern_id == "java_from_dict"
        assert mapping.bedrock_pattern_id == "bedrock_from_dict"
        assert mapping.confidence == 0.7
        assert mapping.notes == "From dict notes"
        assert mapping.limitations == ["from dict limit"]
        assert mapping.requires_manual_review is True

    def test_pattern_mapping_from_dict_with_missing_optional_fields(self):
        """Test from_dict handles missing optional fields with defaults."""
        data = {
            "java_pattern_id": "java_minimal",
            "bedrock_pattern_id": "bedrock_minimal",
            "confidence": 0.5,
        }
        mapping = PatternMapping.from_dict(data)
        assert mapping.notes == ""
        assert mapping.limitations == []
        assert mapping.requires_manual_review is False

    def test_pattern_mapping_to_dict_roundtrip(self):
        """Test to_dict and from_dict are inverses."""
        original = PatternMapping(
            java_pattern_id="java_roundtrip",
            bedrock_pattern_id="bedrock_roundtrip",
            confidence=0.92,
            notes="Roundtrip test",
            limitations=["limit a", "limit b"],
            requires_manual_review=True,
        )
        recovered = PatternMapping.from_dict(original.to_dict())
        assert recovered.java_pattern_id == original.java_pattern_id
        assert recovered.bedrock_pattern_id == original.bedrock_pattern_id
        assert recovered.confidence == original.confidence
        assert recovered.notes == original.notes
        assert recovered.limitations == original.limitations
        assert recovered.requires_manual_review == original.requires_manual_review


class TestMappingConfidence:
    """Tests for MappingConfidence enum."""

    def test_mapping_confidence_values(self):
        """Test MappingConfidence enum has expected values."""
        assert MappingConfidence.HIGH.value == "high"
        assert MappingConfidence.MEDIUM.value == "medium"
        assert MappingConfidence.LOW.value == "low"
        assert MappingConfidence.EXPERIMENTAL.value == "experimental"

    def test_mapping_confidence_is_enum(self):
        """Test MappingConfidence is a proper Enum."""
        assert hasattr(MappingConfidence, "HIGH")
        assert hasattr(MappingConfidence, "MEDIUM")
        assert hasattr(MappingConfidence, "LOW")
        assert hasattr(MappingConfidence, "EXPERIMENTAL")


class TestPatternMappingRegistry:
    """Tests for PatternMappingRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh PatternMappingRegistry for each test."""
        return PatternMappingRegistry()

    def test_registry_is_pre_populated(self, registry):
        """Test that registry is initialized with pre-populated mappings."""
        assert len(registry.mappings) >= 20

    def test_registry_has_expected_known_mappings(self, registry):
        """Test that registry contains specific known mappings."""
        known_mappings = [
            "java_simple_item",
            "java_item_properties",
            "java_food_item",
            "java_ranged_weapon",
            "java_simple_block",
            "java_block_properties",
            "java_rotatable_block",
            "java_simple_entity",
            "java_entity_attributes",
            "java_shaped_recipe",
            "java_shapeless_recipe",
            "java_smelting_recipe",
            "java_player_interact",
            "java_block_break",
            "java_entity_join",
            "java_item_handler",
            "java_fluid_handler",
            "java_tile_entity",
            "java_ticking_tile",
            "java_network_packet",
        ]
        for mapping_id in known_mappings:
            assert mapping_id in registry.mappings, f"Missing mapping: {mapping_id}"


class TestPatternMappingRegistryAddMapping:
    """Tests for PatternMappingRegistry.add_mapping method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_add_mapping_success(self, registry):
        """Test adding a new mapping to the registry."""
        new_mapping = PatternMapping(
            java_pattern_id="java_custom_add",
            bedrock_pattern_id="bedrock_custom_add",
            confidence=0.88,
            notes="Custom mapping added in test",
        )
        registry.add_mapping(new_mapping)
        result = registry.get_bedrock_equivalent("java_custom_add")
        assert result is not None
        assert result.bedrock_pattern_id == "bedrock_custom_add"
        assert result.confidence == 0.88

    def test_add_mapping_duplicate_raises_error(self, registry):
        """Test that adding duplicate java_pattern_id raises ValueError."""
        existing_mapping = registry.get_bedrock_equivalent("java_simple_item")
        duplicate = PatternMapping(
            java_pattern_id="java_simple_item",
            bedrock_pattern_id="bedrock_different",
            confidence=0.5,
        )
        with pytest.raises(ValueError, match="java_simple_item already exists"):
            registry.add_mapping(duplicate)

    def test_add_mapping_multiple_new_mappings(self, registry):
        """Test adding multiple new mappings."""
        mapping1 = PatternMapping("java_new_1", "bedrock_new_1", 0.9)
        mapping2 = PatternMapping("java_new_2", "bedrock_new_2", 0.85)
        mapping3 = PatternMapping("java_new_3", "bedrock_new_3", 0.8)

        initial_count = len(registry.mappings)
        registry.add_mapping(mapping1)
        registry.add_mapping(mapping2)
        registry.add_mapping(mapping3)

        assert len(registry.mappings) == initial_count + 3
        assert registry.get_bedrock_equivalent("java_new_1") is not None
        assert registry.get_bedrock_equivalent("java_new_2") is not None
        assert registry.get_bedrock_equivalent("java_new_3") is not None


class TestPatternMappingRegistryGetBedrockEquivalent:
    """Tests for PatternMappingRegistry.get_bedrock_equivalent method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_get_bedrock_equivalent_existing_mapping(self, registry):
        """Test getting an existing mapping returns correct data."""
        result = registry.get_bedrock_equivalent("java_simple_item")
        assert result is not None
        assert isinstance(result, PatternMapping)
        assert result.bedrock_pattern_id == "bedrock_simple_item"
        assert result.confidence == 0.95

    def test_get_bedrock_equivalent_nonexistent(self, registry):
        """Test getting a nonexistent mapping returns None."""
        result = registry.get_bedrock_equivalent("java_nonexistent_pattern")
        assert result is None

    def test_get_bedrock_equivalent_empty_string(self, registry):
        """Test getting mapping with empty string returns None."""
        result = registry.get_bedrock_equivalent("")
        assert result is None

    def test_get_bedrock_equivalent_returns_correct_confidence(self, registry):
        """Test different mappings return their correct confidence values."""
        test_cases = [
            ("java_simple_item", 0.95),
            ("java_item_properties", 0.90),
            ("java_ranged_weapon", 0.75),
            ("java_fluid_handler", 0.60),
            ("java_network_packet", 0.60),
        ]
        for java_id, expected_confidence in test_cases:
            result = registry.get_bedrock_equivalent(java_id)
            assert result is not None, f"Mapping {java_id} not found"
            assert result.confidence == expected_confidence, (
                f"Expected confidence {expected_confidence} for {java_id}, "
                f"got {result.confidence}"
            )


class TestPatternMappingRegistryGetByConfidence:
    """Tests for PatternMappingRegistry.get_by_confidence method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_get_by_confidence_returns_mappings_at_threshold(self, registry):
        """Test that get_by_confidence returns mappings at exactly the threshold."""
        results = registry.get_by_confidence(0.95)
        for mapping in results:
            assert mapping.confidence >= 0.95

    def test_get_by_confidence_high_threshold(self, registry):
        """Test get_by_confidence with high threshold returns fewer results."""
        high_results = registry.get_by_confidence(0.95)
        low_results = registry.get_by_confidence(0.5)
        assert len(high_results) <= len(low_results)

    def test_get_by_confidence_zero_threshold(self, registry):
        """Test get_by_confidence with 0.0 threshold returns all mappings."""
        results = registry.get_by_confidence(0.0)
        assert len(results) == len(registry.mappings)

    def test_get_by_confidence_boundary_values(self, registry):
        """Test get_by_confidence with boundary confidence values."""
        item_mapping = registry.get_bedrock_equivalent("java_simple_item")
        exact_confidence = item_mapping.confidence
        results = registry.get_by_confidence(exact_confidence)
        assert any(m.java_pattern_id == "java_simple_item" for m in results)

    def test_get_by_confidence_returns_list(self, registry):
        """Test that get_by_confidence returns a list."""
        results = registry.get_by_confidence(0.8)
        assert isinstance(results, list)

    def test_get_by_confidence_empty_result_for_impossible_threshold(self, registry):
        """Test that impossible threshold returns empty list."""
        results = registry.get_by_confidence(1.1)
        assert len(results) == 0


class TestPatternMappingRegistrySearchMappings:
    """Tests for PatternMappingRegistry.search_mappings method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_search_mappings_returns_list(self, registry):
        """Test that search_mappings returns a list."""
        results = registry.search_mappings("item")
        assert isinstance(results, list)

    def test_search_mappings_by_java_pattern_id(self, registry):
        """Test searching by Java pattern ID returns matches."""
        results = registry.search_mappings("item")
        assert len(results) > 0
        assert any("item" in m.java_pattern_id.lower() for m in results)

    def test_search_mappings_by_notes_content(self, registry):
        """Test searching by notes content."""
        results = registry.search_mappings("Script API")
        assert len(results) > 0

    def test_search_mappings_with_min_confidence(self, registry):
        """Test search_mappings respects min_confidence filter."""
        results = registry.search_mappings("entity", min_confidence=0.8)
        for mapping in results:
            assert mapping.confidence >= 0.8

    def test_search_mappings_with_feature_type(self, registry):
        """Test search_mappings with feature_type filter."""
        results = registry.search_mappings("block", feature_type="block")
        assert len(results) > 0

    def test_search_mappings_empty_query(self, registry):
        """Test search_mappings with empty query returns empty list."""
        results = registry.search_mappings("")
        assert len(results) == 0

    def test_search_mappings_nonexistent_pattern(self, registry):
        """Test search_mappings for nonexistent pattern."""
        results = registry.search_mappings("xyznonexistent12345")
        assert len(results) == 0

    def test_search_mappings_sorted_by_relevance(self, registry):
        """Test that results are sorted by relevance score."""
        results = registry.search_mappings("recipe")
        if len(results) >= 2:
            assert results[0].confidence >= results[-1].confidence


class TestPatternMappingRegistryGetStats:
    """Tests for PatternMappingRegistry.get_stats method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_get_stats_returns_dict(self, registry):
        """Test that get_stats returns a dictionary."""
        stats = registry.get_stats()
        assert isinstance(stats, dict)

    def test_get_stats_has_required_keys(self, registry):
        """Test that stats contains required keys."""
        stats = registry.get_stats()
        assert "total" in stats
        assert "by_confidence" in stats
        assert "requires_manual_review" in stats

    def test_get_stats_total_matches_mapping_count(self, registry):
        """Test that total in stats matches actual mapping count."""
        stats = registry.get_stats()
        assert stats["total"] == len(registry.mappings)

    def test_get_stats_by_confidence_structure(self, registry):
        """Test by_confidence has expected structure."""
        stats = registry.get_stats()
        by_conf = stats["by_confidence"]
        assert "high" in by_conf
        assert "medium" in by_conf
        assert "low" in by_conf

    def test_get_stats_by_confidence_values(self, registry):
        """Test that by_confidence counts are consistent."""
        stats = registry.get_stats()
        by_conf = stats["by_confidence"]
        total_categorized = by_conf["high"] + by_conf["medium"] + by_conf["low"]
        assert total_categorized == stats["total"]

    def test_get_stats_high_confidence_correct(self, registry):
        """Test high confidence count (>= 0.8)."""
        stats = registry.get_stats()
        expected_high = len([m for m in registry.mappings.values() if m.confidence >= 0.8])
        assert stats["by_confidence"]["high"] == expected_high

    def test_get_stats_medium_confidence_correct(self, registry):
        """Test medium confidence count (0.5 <= x < 0.8)."""
        stats = registry.get_stats()
        expected_medium = len([
            m for m in registry.mappings.values()
            if 0.5 <= m.confidence < 0.8
        ])
        assert stats["by_confidence"]["medium"] == expected_medium

    def test_get_stats_low_confidence_correct(self, registry):
        """Test low confidence count (< 0.5)."""
        stats = registry.get_stats()
        expected_low = len([m for m in registry.mappings.values() if m.confidence < 0.5])
        assert stats["by_confidence"]["low"] == expected_low

    def test_get_stats_manual_review_count(self, registry):
        """Test manual review count is accurate."""
        stats = registry.get_stats()
        expected_review = len([
            m for m in registry.mappings.values()
            if m.requires_manual_review
        ])
        assert stats["requires_manual_review"] == expected_review


class TestPatternMappingRegistryGetAllMappings:
    """Tests for PatternMappingRegistry.get_all_mappings method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_get_all_mappings_returns_list(self, registry):
        """Test that get_all_mappings returns a list."""
        results = registry.get_all_mappings()
        assert isinstance(results, list)

    def test_get_all_mappings_count_matches(self, registry):
        """Test that count matches registry mappings."""
        results = registry.get_all_mappings()
        assert len(results) == len(registry.mappings)

    def test_get_all_mappings_contains_all_mappings(self, registry):
        """Test that all mappings are returned."""
        results = registry.get_all_mappings()
        for mapping in registry.mappings.values():
            assert mapping in results


class TestPatternMappingRegistryGetManualReviewRequired:
    """Tests for PatternMappingRegistry.get_manual_review_required method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_get_manual_review_required_returns_list(self, registry):
        """Test that get_manual_review_required returns a list."""
        results = registry.get_manual_review_required()
        assert isinstance(results, list)

    def test_get_manual_review_required_all_require_review(self, registry):
        """Test that all returned mappings require manual review."""
        results = registry.get_manual_review_required()
        for mapping in results:
            assert mapping.requires_manual_review is True

    def test_get_manual_review_required_has_expected_mappings(self, registry):
        """Test that expected mappings requiring review are returned."""
        results = registry.get_manual_review_required()
        known_review_mappings = [
            "java_ranged_weapon",
            "java_rotatable_block",
            "java_simple_entity",
            "java_player_interact",
        ]
        result_ids = [m.java_pattern_id for m in results]
        for mapping_id in known_review_mappings:
            if mapping_id in registry.mappings:
                assert mapping_id in result_ids, f"{mapping_id} should require manual review"


class TestPatternMappingRegistryGetMappingsForFeatureType:
    """Tests for PatternMappingRegistry.get_mappings_for_feature_type method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_get_mappings_for_feature_type_block(self, registry):
        """Test getting block-related mappings."""
        results = registry.get_mappings_for_feature_type("block")
        assert len(results) > 0
        expected_ids = [
            "java_simple_block",
            "java_block_properties",
            "java_rotatable_block",
            "java_tile_entity",
            "java_ticking_tile",
        ]
        result_ids = [m.java_pattern_id for m in results]
        for pid in expected_ids:
            assert pid in result_ids

    def test_get_mappings_for_feature_type_item(self, registry):
        """Test getting item-related mappings."""
        results = registry.get_mappings_for_feature_type("item")
        assert len(results) > 0
        expected_ids = [
            "java_simple_item",
            "java_item_properties",
            "java_food_item",
            "java_ranged_weapon",
        ]
        result_ids = [m.java_pattern_id for m in results]
        for pid in expected_ids:
            assert pid in result_ids

    def test_get_mappings_for_feature_type_entity(self, registry):
        """Test getting entity-related mappings."""
        results = registry.get_mappings_for_feature_type("entity")
        assert len(results) >= 2
        result_ids = [m.java_pattern_id for m in results]
        assert "java_simple_entity" in result_ids
        assert "java_entity_attributes" in result_ids

    def test_get_mappings_for_feature_type_case_insensitive(self, registry):
        """Test that feature type is case insensitive."""
        lower_results = registry.get_mappings_for_feature_type("block")
        upper_results = registry.get_mappings_for_feature_type("BLOCK")
        mixed_results = registry.get_mappings_for_feature_type("Block")
        assert len(lower_results) == len(upper_results) == len(mixed_results)

    def test_get_mappings_for_feature_type_unknown(self, registry):
        """Test unknown feature type returns empty list."""
        results = registry.get_mappings_for_feature_type("unknown_feature_xyz")
        assert len(results) == 0


class TestPatternMappingRegistryToIndexableDocuments:
    """Tests for PatternMappingRegistry.to_indexable_documents method."""

    @pytest.fixture
    def registry(self):
        return PatternMappingRegistry()

    def test_to_indexable_documents_returns_list(self, registry):
        """Test that to_indexable_documents returns a list."""
        results = registry.to_indexable_documents()
        assert isinstance(results, list)

    def test_to_indexable_documents_count_matches(self, registry):
        """Test that document count matches mapping count."""
        results = registry.to_indexable_documents()
        assert len(results) == len(registry.mappings)

    def test_to_indexable_documents_has_required_keys(self, registry):
        """Test that each document has required keys."""
        results = registry.to_indexable_documents()
        for doc in results:
            assert "content" in doc
            assert "source" in doc
            assert "metadata" in doc

    def test_to_indexable_documents_source_format(self, registry):
        """Test that source field has expected format."""
        results = registry.to_indexable_documents()
        for doc in results:
            assert doc["source"].startswith("pattern_mapping:")
            java_id = doc["source"].replace("pattern_mapping:", "")
            assert java_id in registry.mappings

    def test_to_indexable_documents_metadata_matches_mapping(self, registry):
        """Test that metadata matches original mapping."""
        results = registry.to_indexable_documents()
        for doc in results:
            java_id = doc["source"].replace("pattern_mapping:", "")
            original = registry.mappings[java_id]
            assert doc["metadata"]["java_pattern_id"] == original.java_pattern_id
            assert doc["metadata"]["bedrock_pattern_id"] == original.bedrock_pattern_id
            assert doc["metadata"]["confidence"] == original.confidence