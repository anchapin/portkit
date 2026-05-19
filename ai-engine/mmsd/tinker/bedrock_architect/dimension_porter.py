"""Dimension Porter — Biome and dimension porting logic for Bedrock conversion.

Provides functions for porting Java dimension and biome features to Bedrock,
including compatibility validation and warning generation.

Issue #1620 — Extracted from bedrock_architect.py for single responsibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DimensionType(Enum):
    """Classification of dimension types."""

    OVERWORLD = "overworld"
    NETHER = "nether"
    END = "end"
    CUSTOM = "custom"


class BiomeCategory(Enum):
    """Classification of biome categories."""

    PLAINS = "plains"
    FOREST = "forest"
    DESERT = "desert"
    MOUNTAIN = "mountain"
    OCEAN = "ocean"
    TAIGA = "taiga"
    JUNGLE = "jungle"
    SAVANNA = "savanna"
    SNOW = "snow"
    SWAMP = "swamp"
    MUSHROOM = "mushroom"
    JUNGLE_EDGE = "jungle_edge"
    BEACH = "beach"
    RIVER = "river"
    CUSTOM = "custom"


@dataclass
class PortingWarning:
    """A warning generated during dimension/biome porting."""

    code: str
    message: str
    severity: str = "warning"  # "info", "warning", "error"
    suggestion: Optional[str] = None


@dataclass
class DimensionPortingResult:
    """Result of dimension porting operation."""

    is_compatible: bool
    bedrock_dimension_id: str
    warnings: List[PortingWarning] = field(default_factory=list)
    converted_structure: Optional[Dict[str, Any]] = None


@dataclass
class BiomePortingResult:
    """Result of biome porting operation."""

    is_compatible: bool
    bedrock_biome_id: str
    warnings: List[PortingWarning] = field(default_factory=list)
    converted_features: List[str] = field(default_factory=list)


# Dimension mapping: Java dimension class patterns to Bedrock dimension IDs
DIMENSION_MAPPING: Dict[str, str] = {
    "net.minecraft.world.WorldProvider": "overworld",
    "net.minecraft.world.WorldProviderHell": "nether",
    "net.minecraft.world.WorldProviderEnd": "the_end",
    "net.minecraftforge.common.WorldProviderEnd": "the_end",
}

# Biome mapping: Java biome registry names to Bedrock biome IDs
BIOME_MAPPING: Dict[str, str] = {
    "minecraft:plains": "plains",
    "minecraft:desert": "desert",
    "minecraft:forest": "forest",
    "minecraft:taiga": "taiga",
    "minecraft:extreme_hills": "mountain",
    "minecraft:jungle": "jungle",
    "minecraft:birch_forest": "birch_forest",
    "minecraft:snowy_tundra": "ice_plains",
    "minecraft:swampland": "swamp",
    "minecraft:savanna": "savanna",
    "minecraft:beach": "beach",
    "minecraft:ocean": "ocean",
    "minecraft:river": "river",
    "minecraft:deep_ocean": "deep_ocean",
    "minecraft:mushroom_island": "mushroom_island",
    "minecraft:mesa": "mesa",
    "minecraft:mountain_edge": "mountain_edge",
}

# Dimension features that can be ported
PORTABLE_DIMENSION_FEATURES = {
    "world_height",
    "sea_level",
    "skylight",
    "ambient_light",
    "has_skyscape",
    "has_fog",
}

# Dimension features that cannot be ported (require劝 workarounds)
NON_PORTABLE_DIMENSION_FEATURES = {
    "custom_generation",
    "dynamic_storage",
    "player_spawn",
    "custom_portal",
    "biome_source_type",
}


def identify_dimension_type(java_provider_class: str) -> DimensionType:
    """Identify the type of dimension from Java provider class.

    Args:
        java_provider_class: Fully qualified Java class name.

    Returns:
        DimensionType enum value.
    """
    for pattern, dim_type in DIMENSION_MAPPING.items():
        if pattern in java_provider_class:
            try:
                return DimensionType(dim_type)
            except ValueError:
                pass

    # Check for common patterns
    java_lower = java_provider_class.lower()
    if "hell" in java_lower or "nether" in java_lower:
        return DimensionType.NETHER
    if "end" in java_lower:
        return DimensionType.END
    if "surface" in java_lower or "overworld" in java_lower:
        return DimensionType.OVERWORLD

    return DimensionType.CUSTOM


def map_java_biome(java_biome_id: str) -> str:
    """Map a Java biome ID to a Bedrock biome ID.

    Args:
        java_biome_id: Java biome identifier (e.g., "minecraft:plains").

    Returns:
        Bedrock biome identifier or original if no mapping found.
    """
    normalized = java_biome_id.lower()
    return BIOME_MAPPING.get(normalized, java_biome_id)


def identify_biome_category(java_biome_class: str) -> BiomeCategory:
    """Identify biome category from Java class name.

    Args:
        java_biome_class: Java biome class name.

    Returns:
        BiomeCategory enum value.
    """
    class_lower = java_biome_class.lower()

    if "plains" in class_lower or "sunflower" in class_lower:
        return BiomeCategory.PLAINS
    if "forest" in class_lower or "birch" in class_lower or "rooftree" in class_lower:
        return BiomeCategory.FOREST
    if "desert" in class_lower:
        return BiomeCategory.DESERT
    if "extreme_hills" in class_lower or "mountain" in class_lower or "taiga" in class_lower:
        return BiomeCategory.MOUNTAIN
    if "ocean" in class_lower or "deep" in class_lower:
        return BiomeCategory.OCEAN
    if "taiga" in class_lower:
        return BiomeCategory.TAIGA
    if "jungle" in class_lower:
        return BiomeCategory.JUNGLE
    if "savanna" in class_lower or "mesa" in class_lower:
        return BiomeCategory.SAVANNA
    if "snow" in class_lower or "tundra" in class_lower or "ice" in class_lower:
        return BiomeCategory.SNOW
    if "swamp" in class_lower or "mushroom" in class_lower:
        return BiomeCategory.SWAMP
    if "beach" in class_lower or "shore" in class_lower:
        return BiomeCategory.BEACH
    if "river" in class_lower:
        return BiomeCategory.RIVER

    return BiomeCategory.CUSTOM


def validate_dimension_compatibility(dimension_data: Dict[str, Any]) -> List[PortingWarning]:
    """Validate dimension data for Bedrock compatibility.

    Args:
        dimension_data: Dictionary with dimension feature data.

    Returns:
        List of PortingWarning objects.
    """
    warnings: List[PortingWarning] = []

    # Check for non-portable features
    features = dimension_data.get("features", [])
    if isinstance(features, list):
        for feature in features:
            feature_type = feature if isinstance(feature, str) else feature.get("type", "")
            if feature_type in NON_PORTABLE_DIMENSION_FEATURES:
                warnings.append(
                    PortingWarning(
                        code="NON_PORTABLE_FEATURE",
                        message=f"Feature '{feature_type}' cannot be directly ported to Bedrock",
                        severity="warning",
                        suggestion="Convert to static structure or use alternative approach",
                    )
                )

    # Check for custom generation settings
    if dimension_data.get("custom_generation"):
        warnings.append(
            PortingWarning(
                code="CUSTOM_GENERATION",
                message="Custom dimension generation will be lost",
                severity="warning",
                suggestion="Consider creating static structure variants",
            )
        )

    # Check for portal restrictions
    if dimension_data.get("has_custom_portal", False):
        warnings.append(
            PortingWarning(
                code="CUSTOM_PORTAL",
                message="Custom portal mechanics cannot be ported",
                severity="warning",
                suggestion="Use standard nether portal or custom trigger",
            )
        )

    return warnings


def validate_biome_compatibility(biome_data: Dict[str, Any]) -> List[PortingWarning]:
    """Validate biome data for Bedrock compatibility.

    Args:
        biome_data: Dictionary with biome feature data.

    Returns:
        List of PortingWarning objects.
    """
    warnings: List[PortingWarning] = []

    # Check for custom vegetation
    if biome_data.get("custom_vegetation"):
        warnings.append(
            PortingWarning(
                code="CUSTOM_VEGETATION",
                message="Custom vegetation placement cannot be preserved",
                severity="info",
                suggestion="Use standard feature placement rules",
            )
        )

    # Check for custom ore generation
    if biome_data.get("custom_ore_generation"):
        warnings.append(
            PortingWarning(
                code="CUSTOM_ORE_GEN",
                message="Custom ore generation will use standard rules",
                severity="info",
                suggestion="Review ore distribution in converted world",
            )
        )

    # Check for custom biome decorators
    if biome_data.get("custom_decorators"):
        warnings.append(
            PortingWarning(
                code="CUSTOM_DECORATORS",
                message="Custom biome decorators cannot be ported",
                severity="warning",
                suggestion="Use feature rules for decoration",
            )
        )

    return warnings


def port_dimension(dimension_data: Dict[str, Any]) -> DimensionPortingResult:
    """Port a Java dimension to Bedrock format.

    Args:
        dimension_data: Dictionary with dimension information.

    Returns:
        DimensionPortingResult with conversion results and warnings.
    """
    java_provider = dimension_data.get("provider_class", "")
    dimension_type = identify_dimension_type(java_provider)

    bedrock_id = dimension_type.value
    warnings = validate_dimension_compatibility(dimension_data)

    # Generate conversion warnings for dimension type
    if dimension_type == DimensionType.CUSTOM:
        warnings.append(
            PortingWarning(
                code="CUSTOM_DIMENSION",
                message="Custom dimension converted to static structure",
                severity="warning",
                suggestion="Dynamic generation features will be lost",
            )
        )

    # Build converted structure
    converted: Dict[str, Any] = {
        "dimension_id": bedrock_id,
        "type": dimension_type.value,
        "environment": {
            "has_skylight": dimension_data.get("has_skylight", True),
            "has_fog": dimension_data.get("has_fog", False),
            "ambient_light": dimension_data.get("ambient_light", 0.0),
        },
    }

    return DimensionPortingResult(
        is_compatible=len([w for w in warnings if w.severity == "error"]) == 0,
        bedrock_dimension_id=bedrock_id,
        warnings=warnings,
        converted_structure=converted,
    )


def port_biome(biome_data: Dict[str, Any]) -> BiomePortingResult:
    """Port a Java biome to Bedrock format.

    Args:
        biome_data: Dictionary with biome information.

    Returns:
        BiomePortingResult with conversion results and warnings.
    """
    java_biome_id = biome_data.get("biome_id", "")
    bedrock_biome_id = map_java_biome(java_biome_id)

    warnings = validate_biome_compatibility(biome_data)

    # Track converted features
    converted_features: List[str] = []

    # Basic biome properties
    if biome_data.get("temperature"):
        converted_features.append("minecraft:temperature")

    if biome_data.get("has_precipitation"):
        converted_features.append("minecraft:precipitation")

    if biome_data.get("grass_color"):
        converted_features.append("minecraft:grass_color")

    return BiomePortingResult(
        is_compatible=True,  # Most biomes are compatible
        bedrock_biome_id=bedrock_biome_id,
        warnings=warnings,
        converted_features=converted_features,
    )


class DimensionPorter:
    """High-level porter for converting dimensions and biomes.

    Use this class to batch-process dimension and biome conversions
    with consistent configuration.
    """

    def __init__(self) -> None:
        """Initialize the dimension porter."""
        self._dimension_results: List[DimensionPortingResult] = []
        self._biome_results: List[BiomePortingResult] = []

    def port_dimension(self, dimension_data: Dict[str, Any]) -> DimensionPortingResult:
        """Port a dimension and store result.

        Args:
            dimension_data: Dimension data to port.

        Returns:
            DimensionPortingResult.
        """
        result = port_dimension(dimension_data)
        self._dimension_results.append(result)
        return result

    def port_biome(self, biome_data: Dict[str, Any]) -> BiomePortingResult:
        """Port a biome and store result.

        Args:
            biome_data: Biome data to port.

        Returns:
            BiomePortingResult.
        """
        result = port_biome(biome_data)
        self._biome_results.append(result)
        return result

    def get_dimension_results(self) -> List[DimensionPortingResult]:
        """Get all dimension conversion results."""
        return self._dimension_results.copy()

    def get_biome_results(self) -> List[BiomePortingResult]:
        """Get all biome conversion results."""
        return self._biome_results.copy()

    def get_all_warnings(self) -> List[PortingWarning]:
        """Get all warnings from all conversions."""
        warnings: List[PortingWarning] = []
        for result in self._dimension_results:
            warnings.extend(result.warnings)
        for result in self._biome_results:
            warnings.extend(result.warnings)
        return warnings

    def clear(self) -> None:
        """Clear all stored results."""
        self._dimension_results.clear()
        self._biome_results.clear()
