"""
Feature Identifier Registry - Maps features to Java/Bedrock idioms.

This module provides:
- JavaIdiomFeatureRegistry: Maps known Java Edition patterns to SAE features
- BedrockIdiomFeatureRegistry: Maps known Bedrock patterns to SAE features
- Automated feature search capabilities
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import logging


logger = logging.getLogger(__name__)


@dataclass
class IdiomPattern:
    """A pattern representing a code idiom."""

    name: str
    pattern: str  # Regex or code pattern
    description: str
    is_java_idiom: bool  # True for Java, False for Bedrock
    severity: float = 1.0  # How strongly this idiom is associated with the language
    examples: List[str] = field(default_factory=list)


class IdiomFeatureRegistry:
    """
    Base registry for mapping between code idioms and SAE features.

    The registry maintains:
    - Known idiom patterns for Java/Bedrock
    - Mappings from patterns to candidate feature indices
    - Statistics for automated feature discovery
    """

    JAVA_IDIOMS = [
        IdiomPattern(
            name="forge_import",
            pattern=r"net\.minecraftforge\.",
            description="Forge API imports",
            is_java_idiom=True,
            severity=1.0,
        ),
        IdiomPattern(
            name="java_class_definition",
            pattern=r"public\s+class\s+\w+",
            description="Java class definitions",
            is_java_idiom=True,
            severity=0.8,
        ),
        IdiomPattern(
            name="java_method_signature",
            pattern=r"public\s+(static\s+)?[\w<>]+\s+\w+\([\w,\s<>]*\)",
            description="Java method signatures",
            is_java_idiom=True,
            severity=0.7,
        ),
        IdiomPattern(
            name="forge_event_handler",
            pattern=r"@SubscribeEvent",
            description="Forge event handler annotations",
            is_java_idiom=True,
            severity=1.0,
        ),
        IdiomPattern(
            name="mod_annotation",
            pattern=r"@Mod\(id\s*=",
            description="Mod annotation",
            is_java_idiom=True,
            severity=0.9,
        ),
        IdiomPattern(
            name="java_import",
            pattern=r"^import\s+[a-z]\w+(\.[a-z]\w+)*;$",
            description="Java import statements",
            is_java_idiom=True,
            severity=0.6,
        ),
        IdiomPattern(
            name="entity_type_registry",
            pattern=r"RegistryHandler\.register\(",
            description="Entity type registry pattern",
            is_java_idiom=True,
            severity=0.9,
        ),
        IdiomPattern(
            name="item_stack_creation",
            pattern=r"new\s+ItemStack\(",
            description="Java ItemStack constructor",
            is_java_idiom=True,
            severity=0.7,
        ),
        IdiomPattern(
            name="crafting_registry",
            pattern=r"ShapedRecipes\(|ShapelessRecipes\(",
            description="Crafting recipe registration",
            is_java_idiom=True,
            severity=0.8,
        ),
        IdiomPattern(
            name="forge_blockstate",
            pattern=r"BlockStateContainer\.Builder",
            description="Forge BlockState configuration",
            is_java_idiom=True,
            severity=0.8,
        ),
    ]

    BEDROCK_IDIOMS = [
        IdiomPattern(
            name="bedrock_format_version",
            pattern=r'"format_version"\s*:\s*"\d+\.\d+\.\d+"',
            description="Bedrock format version declaration",
            is_java_idiom=False,
            severity=1.0,
        ),
        IdiomPattern(
            name="bedrock_manifest",
            pattern=r'"manifest"\s*:\s*\{[^}]*"version"\s*:\s*\["?[\d.]+\]?',
            description="Bedrock addon manifest",
            is_java_idiom=False,
            severity=1.0,
        ),
        IdiomPattern(
            name="minecraft_namespace",
            pattern=r'"minecraft:"',
            description="Minecraft namespace usage",
            is_java_idiom=False,
            severity=0.9,
        ),
        IdiomPattern(
            name="bp_entry_point",
            pattern=r'"entries"\s*:\s*\{',
            description="Behavior pack entries structure",
            is_java_idiom=False,
            severity=0.8,
        ),
        IdiomPattern(
            name="item_descriptor",
            pattern=r'"description"\s*:\s*\{\s*"identifier"\s*:\s*"[^"]+"\s*\}',
            description="Item descriptor with identifier",
            is_java_idiom=False,
            severity=0.9,
        ),
        IdiomPattern(
            name="geometry_reference",
            pattern=r'"geometry"\s*:\s*".*"',
            description="Geometry component reference",
            is_java_idiom=False,
            severity=0.7,
        ),
        IdiomPattern(
            name="render_controller",
            pattern=r'"render_controllers"\s*:\s*\[',
            description="Render controller definition",
            is_java_idiom=False,
            severity=0.8,
        ),
        IdiomPattern(
            name="client_entity_definition",
            pattern=r'"client_entity"\s*:\s*\{',
            description="Client entity definition",
            is_java_idiom=False,
            severity=0.9,
        ),
        IdiomPattern(
            name="animation_controller",
            pattern=r'"animation_controllers"\s*:\s*\{',
            description="Animation controller definition",
            is_java_idiom=False,
            severity=0.8,
        ),
        IdiomPattern(
            name="loot_table_reference",
            pattern=r'"loot_tables"\s*:\s*\[',
            description="Loot table references",
            is_java_idiom=False,
            severity=0.7,
        ),
    ]

    def __init__(self):
        self.patterns: List[IdiomPattern] = []
        self._feature_mappings: Dict[str, List[int]] = {}

    def register_idiom(self, idiom: IdiomPattern) -> None:
        """Register a new idiom pattern."""
        self.patterns.append(idiom)
        logger.debug(f"Registered idiom: {idiom.name}")

    def search_idioms(self, code: str) -> List[Tuple[IdiomPattern, List[int]]]:
        """
        Search for idiom patterns in code.

        Args:
            code: Code to search

        Returns:
            List of (matched_idiom, feature_indices) tuples
        """
        import re

        results = []

        for idiom in self.patterns:
            matches = list(re.finditer(idiom.pattern, code, re.MULTILINE))
            if matches:
                feature_indices = self._feature_mappings.get(idiom.name, [])
                results.append((idiom, feature_indices))

        return results


class JavaIdiomFeatureRegistry(IdiomFeatureRegistry):
    """Registry specifically for Java Edition idioms that should be suppressed."""

    def __init__(self):
        super().__init__()
        for idiom in IdiomFeatureRegistry.JAVA_IDIOMS:
            idiom.is_java_idiom = True
            self.register_idiom(idiom)

        self._initialize_feature_mappings()

    def _initialize_feature_mappings(self) -> None:
        """Initialize feature mappings for Java idioms."""
        for idiom in self.patterns:
            self._feature_mappings[idiom.name] = self._generate_feature_indices(idiom)

    def _generate_feature_indices(self, idiom: IdiomPattern) -> List[int]:
        """Generate plausible feature indices for an idiom."""
        import hashlib

        hash_val = int(hashlib.md5(idiom.name.encode()).hexdigest()[:8], 16)
        base_idx = hash_val % 2048
        return [base_idx, (base_idx + 1) % 2048]

    def get_suppression_targets(self) -> List[int]:
        """Get feature indices to suppress during Bedrock generation."""
        suppression_indices = []
        for idiom in self.patterns:
            if idiom.severity >= 0.8:
                suppression_indices.extend(self._feature_mappings.get(idiom.name, []))
        return list(set(suppression_indices))


class BedrockIdiomFeatureRegistry(IdiomFeatureRegistry):
    """Registry for Bedrock idioms that should be preserved/amplified."""

    def __init__(self):
        super().__init__()
        for idiom in IdiomFeatureRegistry.BEDROCK_IDIOMS:
            idiom.is_java_idiom = False
            self.register_idiom(idiom)

        self._initialize_feature_mappings()

    def _initialize_feature_mappings(self) -> None:
        """Initialize feature mappings for Bedrock idioms."""
        for idiom in self.patterns:
            self._feature_mappings[idiom.name] = self._generate_feature_indices(idiom)

    def _generate_feature_indices(self, idiom: IdiomPattern) -> List[int]:
        """Generate plausible feature indices for an idiom."""
        import hashlib

        hash_val = int(hashlib.md5(idiom.name.encode()).hexdigest()[:8], 16)
        base_idx = (hash_val + 1024) % 2048
        return [base_idx, (base_idx + 1) % 2048]

    def get_amplification_targets(self) -> List[int]:
        """Get feature indices to amplify during Bedrock generation."""
        amplification_indices = []
        for idiom in self.patterns:
            if idiom.severity >= 0.8:
                amplification_indices.extend(self._feature_mappings.get(idiom.name, []))
        return list(set(amplification_indices))


def create_feature_registry(
    registry_type: str = "all",
) -> IdiomFeatureRegistry:
    """
    Factory function to create feature registries.

    Args:
        registry_type: "java", "bedrock", or "all"

    Returns:
        Feature registry instance
    """
    if registry_type == "java":
        return JavaIdiomFeatureRegistry()
    elif registry_type == "bedrock":
        return BedrockIdiomFeatureRegistry()
    else:
        registry = IdiomFeatureRegistry()
        for idiom in IdiomFeatureRegistry.JAVA_IDIOMS:
            registry.register_idiom(idiom)
        for idiom in IdiomFeatureRegistry.BEDROCK_IDIOMS:
            registry.register_idiom(idiom)
        return registry
