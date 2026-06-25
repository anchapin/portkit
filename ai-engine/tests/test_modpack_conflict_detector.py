"""
Unit tests for ModpackConflictDetector

Tests the ModpackConflictDetector class for detecting API conflicts (Forge + Fabric mods),
identifying shared asset namespace collisions, calculating load order dependencies,
generating conflict resolution suggestions, and creating final mod load order lists.

Issue: #499 - Implement Modpack Conflict Detection & Load Order (Phase 5d)
"""

import pytest
from agents.modpack.conflict_detector import (
    ModpackConflictDetector,
    ModLoader,
    ConflictType,
    Severity,
    ModMetadata,
    NamespaceInfo,
    Conflict,
    LoadOrderEntry,
    ConflictDetectionResult,
)


# Sample mods for testing
SAMPLE_MODS = [
    {"id": "1", "name": "FabricAPI", "version": "1.0.0", "loader": "fabric"},
    {"id": "2", "name": "TestMod", "version": "1.0.0", "loader": "fabric"},
    {"id": "3", "name": "AnotherMod", "version": "2.0.0", "loader": "fabric"},
]

# Mods with Forge + Fabric conflict
FORGE_FABRIC_MODS = [
    {"id": "1", "name": "ForgeMod", "version": "1.0.0", "loader": "forge"},
    {"id": "2", "name": "FabricMod", "version": "1.0.0", "loader": "fabric"},
]

# Mods with known conflicts
CONFLICTING_MODS = [
    {"id": "1", "name": "JEI", "version": "1.0.0", "loader": "forge"},
    {"id": "2", "name": "REI", "version": "1.0.0", "loader": "forge"},
]

# Mods with explicit conflicts
EXPLICIT_CONFLICT_MODS = [
    {"id": "1", "name": "ModA", "version": "1.0.0", "conflicts_with": ["ModB"]},
    {"id": "2", "name": "ModB", "version": "1.0.0"},
]

# Mods with load order hints
LOAD_ORDER_MODS = [
    {"id": "1", "name": "CoreMod", "version": "1.0.0", "load_after": []},
    {"id": "2", "name": "ExtensionMod", "version": "1.0.0", "load_after": ["CoreMod"]},
]


class TestModpackConflictDetector:
    """Tests for ModpackConflictDetector class."""

    def test_detect_conflicts_empty(self):
        """Test detecting conflicts with empty mod list."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts([])

        assert result.success is True
        assert len(result.conflicts) == 0

    def test_detect_conflicts_fabric_only(self):
        """Test detecting conflicts with Fabric-only mods."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(SAMPLE_MODS)

        assert result.success is True
        # Should have no API conflicts
        assert len(result.api_conflicts) == 0

    def test_detect_forge_fabric_conflict(self):
        """Test detecting Forge + Fabric API conflict."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(FORGE_FABRIC_MODS)

        assert result.success is True
        assert len(result.api_conflicts) > 0
        assert result.critical_count > 0

        # Check it's a critical API conflict
        api_conflict = result.api_conflicts[0]
        assert api_conflict.conflict_type == ConflictType.API_CONFLICT
        assert api_conflict.severity == Severity.CRITICAL

    def test_detect_known_conflicts(self):
        """Test detecting known mod conflicts (JEI vs REI)."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(CONFLICTING_MODS)

        assert result.success is True
        # Should detect JEI vs REI conflict
        conflicts = [c for c in result.conflicts if c.conflict_type == ConflictType.API_CONFLICT]
        assert len(conflicts) > 0

    def test_detect_explicit_conflicts(self):
        """Test detecting explicit conflicts."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(EXPLICIT_CONFLICT_MODS)

        assert result.success is True
        dep_conflicts = [
            c for c in result.conflicts if c.conflict_type == ConflictType.DEPENDENCY_CONFLICT
        ]
        assert len(dep_conflicts) > 0

    def test_calculate_load_order(self):
        """Test calculating load order."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(LOAD_ORDER_MODS)

        assert result.success is True
        assert len(result.load_order) > 0

        # Check load order positions
        positions = {entry.position: entry.mod_name for entry in result.load_order}
        assert 1 in positions  # First mod should have position 1

    def test_generate_recommendations(self):
        """Test generating recommendations."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(FORGE_FABRIC_MODS)

        assert result.success is True
        assert len(result.recommendations) > 0

        # Should recommend removing incompatible mods
        assert any("CRITICAL" in r or "Remove" in r for r in result.recommendations)

    def test_generate_conflict_report(self):
        """Test generating a conflict report."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(SAMPLE_MODS)

        report = detector.generate_conflict_report(result)

        assert "success" in report
        assert "summary" in report
        assert "conflicts" in report
        assert "load_order" in report


class TestModLoader:
    """Tests for ModLoader enum."""

    def test_mod_loaders(self):
        """Test all mod loaders exist."""
        assert ModLoader.FORGE.value == "forge"
        assert ModLoader.FABRIC.value == "fabric"
        assert ModLoader.QUILT.value == "quilt"
        assert ModLoader.NEOFORGE.value == "neoforge"
        assert ModLoader.RIFT.value == "rift"
        assert ModLoader.UNKNOWN.value == "unknown"


class TestConflictType:
    """Tests for ConflictType enum."""

    def test_conflict_types(self):
        """Test all conflict types exist."""
        assert ConflictType.API_CONFLICT.value == "api_conflict"
        assert ConflictType.NAMESPACE_COLLISION.value == "namespace_collision"
        assert ConflictType.ASSET_CONFLICT.value == "asset_conflict"
        assert ConflictType.VERSION_CONFLICT.value == "version_conflict"
        assert ConflictType.DEPENDENCY_CONFLICT.value == "dependency_conflict"
        assert ConflictType.LOAD_ORDER_CONFLICT.value == "load_order_conflict"


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_levels(self):
        """Test all severity levels exist."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


class TestModMetadata:
    """Tests for ModMetadata class."""

    def test_mod_metadata_creation(self):
        """Test creating ModMetadata."""
        metadata = ModMetadata(mod_id="1", name="TestMod", version="1.0.0", loader=ModLoader.FABRIC)

        assert metadata.mod_id == "1"
        assert metadata.name == "TestMod"
        assert metadata.version == "1.0.0"
        assert metadata.loader == ModLoader.FABRIC


class TestNamespaceInfo:
    """Tests for NamespaceInfo class."""

    def test_namespace_info_creation(self):
        """Test creating NamespaceInfo."""
        ns = NamespaceInfo(namespace="textures", mods=["ModA", "ModB"], resource_types={"textures"})

        assert ns.namespace == "textures"
        assert len(ns.mods) == 2
        assert "textures" in ns.resource_types


class TestConflict:
    """Tests for Conflict class."""

    def test_conflict_creation(self):
        """Test creating a Conflict."""
        conflict = Conflict(
            conflict_type=ConflictType.API_CONFLICT,
            severity=Severity.CRITICAL,
            mods_involved=["ModA", "ModB"],
            description="Test conflict",
            suggestion="Remove one mod",
            resolution="Remove ModB",
        )

        assert conflict.conflict_type == ConflictType.API_CONFLICT
        assert conflict.severity == Severity.CRITICAL
        assert len(conflict.mods_involved) == 2


class TestLoadOrderEntry:
    """Tests for LoadOrderEntry class."""

    def test_load_order_entry_creation(self):
        """Test creating a LoadOrderEntry."""
        entry = LoadOrderEntry(
            mod_id="1", mod_name="TestMod", position=1, reason="No dependencies", dependencies=[]
        )

        assert entry.mod_id == "1"
        assert entry.mod_name == "TestMod"
        assert entry.position == 1


class TestConflictDetectionResult:
    """Tests for ConflictDetectionResult class."""

    def test_default_values(self):
        """Test default values for result."""
        result = ConflictDetectionResult(success=True)

        assert result.success is True
        assert len(result.conflicts) == 0
        assert len(result.load_order) == 0
        assert result.critical_count == 0
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_count_severity(self):
        """Test counting severity levels."""
        result = ConflictDetectionResult(success=True)

        # Add some conflicts
        result.conflicts.append(
            Conflict(ConflictType.API_CONFLICT, Severity.CRITICAL, [], "Test", "Test", None)
        )
        result.conflicts.append(
            Conflict(ConflictType.VERSION_CONFLICT, Severity.ERROR, [], "Test", "Test", None)
        )
        result.conflicts.append(
            Conflict(ConflictType.LOAD_ORDER_CONFLICT, Severity.WARNING, [], "Test", "Test", None)
        )

        # Manually update counts
        for conflict in result.conflicts:
            if conflict.severity == Severity.CRITICAL:
                result.critical_count += 1
            elif conflict.severity == Severity.ERROR:
                result.error_count += 1
            elif conflict.severity == Severity.WARNING:
                result.warning_count += 1

        assert result.critical_count == 1
        assert result.error_count == 1
        assert result.warning_count == 1


class TestResolveConflicts:
    """Tests for conflict resolution."""

    def test_resolve_conflicts(self):
        """Test resolving conflicts by excluding mods."""
        detector = ModpackConflictDetector()
        result = detector.detect_conflicts(CONFLICTING_MODS)

        exclude = detector.resolve_conflicts(result)

        assert isinstance(exclude, list)


class TestDetectLoader:
    """Tests for loader detection."""

    def test_detect_forge_loader(self):
        """Test detecting Forge loader."""
        detector = ModpackConflictDetector()

        assert detector._detect_loader({"name": "ForgeMod", "loader": "forge"}) == ModLoader.FORGE
        assert (
            detector._detect_loader({"name": "MinecraftForge", "loader": "minecraftforge"})
            == ModLoader.FORGE
        )

    def test_detect_fabric_loader(self):
        """Test detecting Fabric loader."""
        detector = ModpackConflictDetector()

        assert (
            detector._detect_loader({"name": "FabricMod", "loader": "fabric"}) == ModLoader.FABRIC
        )
        assert (
            detector._detect_loader({"name": "fabric-api", "loader": "fabric"}) == ModLoader.FABRIC
        )

    def test_detect_quilt_loader(self):
        """Test detecting Quilt loader."""
        detector = ModpackConflictDetector()

        assert detector._detect_loader({"name": "QuiltMod", "loader": "quilt"}) == ModLoader.QUILT

    def test_detect_unknown_loader(self):
        """Test detecting unknown loader."""
        detector = ModpackConflictDetector()

        assert (
            detector._detect_loader({"name": "SomeMod", "loader": "unknown"}) == ModLoader.UNKNOWN
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
