"""
Modpack Conflict Detector for modpack conversion support.

Detects API conflicts (Forge + Fabric mods), identifies shared asset namespace
collisions, calculates load order dependencies, generates conflict resolution
suggestions, and creates final mod load order lists.

Issue: #499 - Implement Modpack Conflict Detection & Load Order (Phase 5d)

Moved into agents/modpack/ subpackage per issue #1729.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ModLoader(Enum):
    """Minecraft mod loaders."""

    FORGE = "forge"
    FABRIC = "fabric"
    QUILT = "quilt"
    NEOFORGE = "neoforge"
    RIFT = "rift"
    UNKNOWN = "unknown"


class ConflictType(Enum):
    """Types of conflicts between mods."""

    API_CONFLICT = "api_conflict"  # Forge vs Fabric
    NAMESPACE_COLLISION = "namespace_collision"
    ASSET_CONFLICT = "asset_conflict"
    VERSION_CONFLICT = "version_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    LOAD_ORDER_CONFLICT = "load_order_conflict"


class Severity(Enum):
    """Severity levels for conflicts."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ModMetadata:
    """Metadata about a mod."""

    mod_id: str
    name: str
    version: Optional[str] = None
    loader: ModLoader = ModLoader.UNKNOWN
    minecraft_version: Optional[str] = None
    source: str = "unknown"  # curseforge, modrinth
    file_id: Optional[int] = None
    url: Optional[str] = None
    provides: List[str] = field(default_factory=list)  # What this mod provides
    conflicts_with: List[str] = field(default_factory=list)  # Explicit conflicts
    load_before: List[str] = field(default_factory=list)  # Load before these mods
    load_after: List[str] = field(default_factory=list)  # Load after these mods


@dataclass
class NamespaceInfo:
    """Information about a namespace used by mods."""

    namespace: str
    mods: List[str] = field(default_factory=list)
    resource_types: Set[str] = field(default_factory=set)


@dataclass
class Conflict:
    """Represents a detected conflict between mods."""

    conflict_type: ConflictType
    severity: Severity
    mods_involved: List[str]
    description: str
    suggestion: str
    resolution: Optional[str] = None


@dataclass
class LoadOrderEntry:
    """Entry in the load order."""

    mod_id: str
    mod_name: str
    position: int
    reason: str
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ConflictDetectionResult:
    """Result of conflict detection analysis."""

    success: bool = True
    error_message: Optional[str] = None

    conflicts: List[Conflict] = field(default_factory=list)
    load_order: List[LoadOrderEntry] = field(default_factory=list)

    namespace_collisions: Dict[str, NamespaceInfo] = field(default_factory=dict)
    api_conflicts: List[Conflict] = field(default_factory=list)

    critical_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    recommendations: List[str] = field(default_factory=list)


class ModpackConflictDetector:
    """
    Detects conflicts in modpacks and calculates load order.

    Identifies:
    - API conflicts (Forge vs Fabric)
    - Asset namespace collisions
    - Version conflicts
    - Dependency conflicts
    - Load order requirements
    """

    # Mods that are known to be incompatible with each other
    KNOWN_CONFLICTS = {
        # Forge-only mods / Item Viewers
        "jei": ["roughlyenoughitems", "emi", "rei"],
        "justenoughitems": ["roughlyenoughitems", "emi", "rei"],
        "rei": ["roughlyenoughitems", "emi", "jei", "justenoughitems"],
        "roughlyenoughitems": ["jei", "justenoughitems", "rei", "emi"],
        "emi": ["jei", "justenoughitems", "rei", "roughlyenoughitems"],
        # Energy conflicts
        "ic2": ["thermalexpansion", "immersiveengineering"],
        # Inventory conflicts
        "refinedstorage": ["ae2", "storagevault"],
    }

    # Namespace prefixes that indicate specific resource types
    NAMESPACES = {
        "textures": "textures/",
        "models": "models/",
        "sounds": "sounds/",
        "lang": "texts/",
        "recipes": "recipes/",
        "advancements": "advancements/",
        "loot_tables": "loot_tables/",
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def detect_conflicts(
        self, mods: List[Dict[str, Any]], dependency_graph: Optional[Dict[str, List[str]]] = None
    ) -> ConflictDetectionResult:
        """
        Detect all conflicts in a modpack.

        Args:
            mods: List of mod dictionaries with metadata
            dependency_graph: Optional pre-computed dependency graph

        Returns:
            ConflictDetectionResult with all detected conflicts
        """
        try:
            result = ConflictDetectionResult()

            # Parse mod metadata
            mod_metadata = self._parse_mod_metadata(mods)

            # Detect API conflicts (Forge vs Fabric)
            api_conflicts = self._detect_api_conflicts(mod_metadata)
            result.api_conflicts = api_conflicts
            result.conflicts.extend(api_conflicts)

            # Detect namespace collisions
            namespace_issues = self._detect_namespace_collisions(mod_metadata)
            result.namespace_collisions = namespace_issues

            for ns_info in namespace_issues.values():
                if len(ns_info.mods) > 1:
                    conflict = Conflict(
                        conflict_type=ConflictType.NAMESPACE_COLLISION,
                        severity=Severity.WARNING,
                        mods_involved=ns_info.mods,
                        description=f"Namespace '{ns_info.namespace}' used by multiple mods",
                        suggestion="Resolve which mod should provide the namespace",
                        resolution=self._suggest_namespace_resolution(ns_info),
                    )
                    result.conflicts.append(conflict)

            # Detect known mod conflicts
            known_conflicts = self._detect_known_conflicts(mod_metadata)
            result.conflicts.extend(known_conflicts)

            # Calculate severity counts
            for conflict in result.conflicts:
                if conflict.severity == Severity.CRITICAL:
                    result.critical_count += 1
                elif conflict.severity == Severity.ERROR:
                    result.error_count += 1
                elif conflict.severity == Severity.WARNING:
                    result.warning_count += 1
                elif conflict.severity == Severity.INFO:
                    result.info_count += 1

            # Calculate load order
            result.load_order = self._calculate_load_order(
                mod_metadata, dependency_graph, api_conflicts
            )

            # Generate recommendations
            result.recommendations = self._generate_recommendations(result, mod_metadata)

            result.success = True
            return result

        except Exception as e:
            self.logger.error(f"Error detecting conflicts: {e}")
            return ConflictDetectionResult(success=False, error_message=str(e))

    def _parse_mod_metadata(self, mods: List[Dict[str, Any]]) -> Dict[str, ModMetadata]:
        """Parse mod metadata from mod list."""
        metadata = {}

        for mod_data in mods:
            mod_id = str(mod_data.get("id", mod_data.get("modId", "")))
            name = mod_data.get("name", f"mod_{mod_id}").lower()

            # Determine loader
            loader = self._detect_loader(mod_data)

            # Get version
            version = mod_data.get("version")

            # Get Minecraft version
            mc_version = mod_data.get("minecraft_version") or mod_data.get("game_version")

            mod = ModMetadata(
                mod_id=mod_id,
                name=name,
                version=version,
                loader=loader,
                minecraft_version=mc_version,
                source=mod_data.get("source", "unknown"),
                file_id=mod_data.get("file_id"),
                url=mod_data.get("url"),
                provides=mod_data.get("provides", []),
                conflicts_with=mod_data.get("conflicts_with", []),
                load_before=mod_data.get("load_before", []),
                load_after=mod_data.get("load_after", []),
            )

            metadata[mod_id] = mod
            # Also index by name for easier lookup
            metadata[name] = mod

        return metadata

    def _detect_loader(self, mod_data: Dict[str, Any]) -> ModLoader:
        """Detect which loader a mod is for."""
        # Check explicit loader field
        if "loader" in mod_data:
            loader_str = mod_data["loader"].lower()
            if "fabric" in loader_str:
                return ModLoader.FABRIC
            elif "quilt" in loader_str:
                return ModLoader.QUILT
            elif "neoforge" in loader_str:
                return ModLoader.NEOFORGE
            elif "forge" in loader_str:
                return ModLoader.FORGE
            elif "rift" in loader_str:
                return ModLoader.RIFT

        # Check mod ID or name for known loaders
        name = mod_data.get("name", "").lower()
        mod_id = str(mod_data.get("id", "")).lower()

        # Fabric-specific mods
        fabric_mods = [
            "fabric",
            "fabric-api",
            "fabric-language-kotlin",
            "fabricloader",
            "cardinal-components",
        ]

        # Forge-specific mods

        # Quilt-specific
        quilt_mods = ["quilt", "quilt-loader"]

        for fm in fabric_mods:
            if fm in name or fm in mod_id:
                return ModLoader.FABRIC

        for qm in quilt_mods:
            if qm in name or qm in mod_id:
                return ModLoader.QUILT

        # Check for "fabric" or "forge" in description/tags
        tags = mod_data.get("tags", [])
        if isinstance(tags, list):
            tags_str = " ".join(tags).lower()
            if "fabric" in tags_str and "forge" not in tags_str:
                return ModLoader.FABRIC
            elif "quilt" in tags_str:
                return ModLoader.QUILT

        return ModLoader.UNKNOWN

    def _detect_api_conflicts(self, metadata: Dict[str, ModMetadata]) -> List[Conflict]:
        """Detect Forge vs Fabric API conflicts."""
        conflicts = []

        # Get loaders present in the modpack
        loaders_present: Dict[ModLoader, List[str]] = defaultdict(list)

        for mod_id, mod in metadata.items():
            if isinstance(mod, ModMetadata):
                loaders_present[mod.loader].append(mod.name)

        # Check for Forge + Fabric mix
        has_forge = ModLoader.FORGE in loaders_present or ModLoader.NEOFORGE in loaders_present
        has_fabric = ModLoader.FABRIC in loaders_present
        has_quilt = ModLoader.QUILT in loaders_present

        if has_forge and (has_fabric or has_quilt):
            # Critical conflict - can't mix Forge and Fabric
            forge_mods = loaders_present.get(ModLoader.FORGE, []) + loaders_present.get(
                ModLoader.NEOFORGE, []
            )
            fabric_mods = loaders_present.get(ModLoader.FABRIC, [])
            quilt_mods = loaders_present.get(ModLoader.QUILT, [])

            conflict = Conflict(
                conflict_type=ConflictType.API_CONFLICT,
                severity=Severity.CRITICAL,
                mods_involved=forge_mods + fabric_mods + quilt_mods,
                description=(
                    f"Cannot mix Forge/Neoforge mods ({len(forge_mods)} mods) "
                    f"with Fabric/Quilt mods ({len(fabric_mods) + len(quilt_mods)} mods)"
                ),
                suggestion=(
                    "Choose one modloader (Forge/Neoforge OR Fabric/Quilt) "
                    "and ensure all mods are compatible with that loader"
                ),
                resolution="Remove incompatible mods",
            )
            conflicts.append(conflict)

        # Check for specific incompatible mods
        for mod_id, mod in metadata.items():
            if isinstance(mod, ModMetadata):
                for conflict_name, incompatible_with in self.KNOWN_CONFLICTS.items():
                    if conflict_name in mod.name:
                        # Check if any incompatible mods are present
                        for other_id, other_mod in metadata.items():
                            if isinstance(other_mod, ModMetadata):
                                for inc in incompatible_with:
                                    if inc in other_mod.name:
                                        conflict = Conflict(
                                            conflict_type=ConflictType.API_CONFLICT,
                                            severity=Severity.ERROR,
                                            mods_involved=[mod.name, other_mod.name],
                                            description=f"{mod.name} conflicts with {other_mod.name}",
                                            suggestion=f"Remove one of: {mod.name} or {other_mod.name}",
                                            resolution=f"Keep {mod.name}, remove {other_mod.name}",
                                        )
                                        conflicts.append(conflict)

        return conflicts

    def _detect_namespace_collisions(
        self, metadata: Dict[str, ModMetadata]
    ) -> Dict[str, NamespaceInfo]:
        """Detect namespace collisions between mods."""
        namespaces: Dict[str, NamespaceInfo] = defaultdict(NamespaceInfo)

        for mod_id, mod in metadata.items():
            if not isinstance(mod, ModMetadata):
                continue

            # Check provided namespaces
            for ns in mod.provides:
                if ns not in namespaces:
                    namespaces[ns] = NamespaceInfo(namespace=ns)
                namespaces[ns].mods.append(mod.name)
                namespaces[ns].resource_types.add("custom")

        return dict(namespaces)

    def _detect_known_conflicts(self, metadata: Dict[str, ModMetadata]) -> List[Conflict]:
        """Detect conflicts from known incompatible mod pairs."""
        conflicts = []

        mod_names = set()
        for mod in metadata.values():
            if isinstance(mod, ModMetadata):
                mod_names.add(mod.name.lower())

        for mod_id, mod in metadata.items():
            if not isinstance(mod, ModMetadata):
                continue

            # Check explicit conflicts
            for conflict_name in mod.conflicts_with:
                if conflict_name.lower() in mod_names:
                    conflict = Conflict(
                        conflict_type=ConflictType.DEPENDENCY_CONFLICT,
                        severity=Severity.ERROR,
                        mods_involved=[mod.name, conflict_name],
                        description=f"{mod.name} explicitly conflicts with {conflict_name}",
                        suggestion="Remove one of the conflicting mods",
                        resolution=None,
                    )
                    conflicts.append(conflict)

        return conflicts

    def _suggest_namespace_resolution(self, ns_info: NamespaceInfo) -> str:
        """Suggest resolution for namespace collision."""
        if len(ns_info.mods) <= 1:
            return "No resolution needed"

        # Suggest keeping the first mod, disabling others
        kept = ns_info.mods[0]
        removed = ns_info.mods[1:]

        return f"Keep {kept}, disable: {', '.join(removed)}"

    def _calculate_load_order(
        self,
        metadata: Dict[str, ModMetadata],
        dependency_graph: Optional[Dict[str, List[str]]],
        api_conflicts: List[Conflict],
    ) -> List[LoadOrderEntry]:
        """Calculate optimal load order for mods."""
        load_order = []

        # If there are critical API conflicts, we can't determine load order
        has_critical = any(c.severity == Severity.CRITICAL for c in api_conflicts)
        if has_critical:
            return load_order

        # Build a graph of load order requirements
        before: Dict[str, Set[str]] = defaultdict(set)  # mod -> mods that must load before it
        after: Dict[str, Set[str]] = defaultdict(set)  # mod -> mods that must load after it

        # Add explicit load order hints
        for mod_id, mod in metadata.items():
            if not isinstance(mod, ModMetadata):
                continue

            for lb in mod.load_before:
                # This mod must load before lb
                before[lb].add(mod.name)
                after[mod.name].add(lb)

            for la in mod.load_after:
                # This mod must load after la
                before[mod.name].add(la)
                after[la].add(mod.name)

        # Use topological sort with load order hints
        # For now, use a simple ordering based on dependencies

        # Get mods with no dependencies first
        independent = []
        dependent = []

        for mod_id, mod in metadata.items():
            if not isinstance(mod, ModMetadata):
                continue

            # Check if has dependencies
            has_dependency = bool(mod.load_after or mod.load_before)

            if not has_dependency:
                independent.append((mod.name, mod_id))
            else:
                dependent.append((mod.name, mod_id))

        # Sort alphabetically within each group
        independent.sort(key=lambda x: x[0])
        dependent.sort(key=lambda x: x[0])

        # Combine: independent mods first, then dependent ones
        position = 1
        for name, mod_id in independent + dependent:
            load_order.append(
                LoadOrderEntry(
                    mod_id=mod_id,
                    mod_name=name,
                    position=position,
                    reason="No specific load order requirements"
                    if position <= len(independent)
                    else "Has load order dependencies",
                    dependencies=list(after.get(name, set())),
                )
            )
            position += 1

        return load_order

    def _generate_recommendations(
        self, result: ConflictDetectionResult, metadata: Dict[str, ModMetadata]
    ) -> List[str]:
        """Generate recommendations based on detected conflicts."""
        recommendations = []

        if result.critical_count > 0:
            recommendations.append(
                f"CRITICAL: {result.critical_count} critical conflict(s) must be resolved"
            )

        if result.error_count > 0:
            recommendations.append(
                f"Resolve {result.error_count} error-level conflict(s) before proceeding"
            )

        if result.warning_count > 0:
            recommendations.append(f"Review {result.warning_count} warning(s) for potential issues")

        # Specific recommendations
        if result.api_conflicts:
            # Check if we need to choose a loader
            loaders = set()
            for mod in metadata.values():
                if isinstance(mod, ModMetadata):
                    loaders.add(mod.loader)

            if ModLoader.FORGE in loaders or ModLoader.NEOFORGE in loaders:
                recommendations.append(
                    "Use Forge/Neoforge-only mods. Remove any Fabric/Quilt mods."
                )
            elif ModLoader.FABRIC in loaders or ModLoader.QUILT in loaders:
                recommendations.append(
                    "Use Fabric/Quilt-only mods. Remove any Forge/Neoforge mods."
                )

        if not result.load_order:
            recommendations.append("Cannot determine load order - resolve conflicts first")

        return recommendations

    def generate_conflict_report(self, result: ConflictDetectionResult) -> Dict[str, Any]:
        """Generate a human-readable conflict report."""
        report = {
            "success": result.success,
            "summary": {
                "total_conflicts": len(result.conflicts),
                "critical": result.critical_count,
                "errors": result.error_count,
                "warnings": result.warning_count,
                "info": result.info_count,
            },
            "conflicts": [],
            "load_order": [],
            "recommendations": result.recommendations,
        }

        if not result.success:
            report["error"] = result.error_message
            return report

        # Add conflicts
        for conflict in result.conflicts:
            report["conflicts"].append(
                {
                    "type": conflict.conflict_type.value,
                    "severity": conflict.severity.value,
                    "mods": conflict.mods_involved,
                    "description": conflict.description,
                    "suggestion": conflict.suggestion,
                    "resolution": conflict.resolution,
                }
            )

        # Add load order
        for entry in result.load_order:
            report["load_order"].append(
                {
                    "position": entry.position,
                    "mod_id": entry.mod_id,
                    "mod_name": entry.mod_name,
                    "reason": entry.reason,
                    "dependencies": entry.dependencies,
                }
            )

        return report

    def resolve_conflicts(
        self, result: ConflictDetectionResult, exclude_mods: Optional[List[str]] = None
    ) -> List[str]:
        """
        Resolve conflicts by excluding incompatible mods.

        Args:
            result: The conflict detection result
            exclude_mods: Optional list of mods to exclude

        Returns:
            List of mod IDs to exclude to resolve all conflicts
        """
        exclude = exclude_mods or []

        for conflict in result.conflicts:
            if conflict.severity in [Severity.CRITICAL, Severity.ERROR]:
                # For critical/errors, exclude all but the first mod
                if conflict.resolution and "Remove" in conflict.resolution:
                    # Parse the resolution to get mods to remove
                    resolution = conflict.resolution.lower()
                    for mod in conflict.mods_involved:
                        if mod.lower() not in resolution:
                            exclude.append(mod)

        # Remove duplicates
        return list(set(exclude))


# Singleton instance
modpack_conflict_detector = ModpackConflictDetector()
