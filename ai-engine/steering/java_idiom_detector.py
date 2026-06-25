"""
Java Idiom Heuristics for Feature Detection.

This module provides heuristic-based Java idiom detection when an SAE model
is not available. It identifies common Java patterns that should be suppressed
during Bedrock code generation.

These heuristics serve as a fallback for the SAE feature detection pipeline
and also provide training data for future SAE-based approaches.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class IdiomPattern:
    """A detected idiom pattern"""

    pattern_id: int
    pattern_name: str
    confidence: float  # 0.0 to 1.0
    matched_text: str
    line_number: int
    suppression_priority: int  # Higher = more important to suppress


class JavaIdiomHeuristics:
    """
    Heuristic detector for common Java modding idioms.

    Detects patterns like:
    - Java class declarations (extends, implements)
    - Forge event handlers (@SubscribeEvent)
    - Java API calls (Minecraft.getInstance(), level.isClientSide())
    - Registry patterns (register())
    - Capability patterns (IItemHandler)

    Maps these to feature indices that correspond to the SAE feature space.
    """

    def __init__(self):
        self.patterns = self._compile_patterns()
        self._stats = {"total_calls": 0, "detections": {}}

    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile all regex patterns for idiom detection"""
        return {
            # Class declarations
            "extends_item": re.compile(r"\bextends\s+Item\b", re.IGNORECASE),
            "extends_block": re.compile(r"\bextends\s+Block\b", re.IGNORECASE),
            "extends_entity": re.compile(
                r"\bextends\s+(Entity|Mob|PathfinderMob)\b", re.IGNORECASE
            ),
            "extends_tile": re.compile(r"\bextends\s+(BlockEntity|TileEntity)\b", re.IGNORECASE),
            "implements_interface": re.compile(r"\bimplements\s+\w+", re.IGNORECASE),
            # Annotations
            "subscribe_event": re.compile(r"@SubscribeEvent\b", re.IGNORECASE),
            "mod_init": re.compile(r"@Mod\b", re.IGNORECASE),
            "event_handler": re.compile(r"@EventBusSubscriber\b", re.IGNORECASE),
            # Forge API patterns
            "minecraft_server": re.compile(r"Minecraft\.getInstance\(\)", re.IGNORECASE),
            "is_client_side": re.compile(r"\.isClientSide\(\)", re.IGNORECASE),
            "is_server_side": re.compile(r"\.isServerSide\(\)", re.IGNORECASE),
            "add_fresh_entity": re.compile(r"\.addFreshEntity\(", re.IGNORECASE),
            "level_get_block_state": re.compile(r"\.getBlockState\(", re.IGNORECASE),
            "blockpos_pattern": re.compile(r"new\s+BlockPos\(", re.IGNORECASE),
            "itemstack_pattern": re.compile(r"new\s+ItemStack\(", re.IGNORECASE),
            # Registry patterns
            "register_recipe": re.compile(r"\.register\([^)]\)", re.IGNORECASE),
            "register_entity": re.compile(r"EntityType\.register\b", re.IGNORECASE),
            "registry_holder": re.compile(r"ForgeRegistries\b", re.IGNORECASE),
            # Capability patterns
            "capability_item_handler": re.compile(r"IItemHandler\b", re.IGNORECASE),
            "capability_fluid_handler": re.compile(r"IFluidHandler\b", re.IGNORECASE),
            "capability_energy": re.compile(r"IEnergyStorage\b", re.IGNORECASE),
            # Java-specific constructs
            "public_class": re.compile(r"\bpublic\s+class\s+\w+", re.IGNORECASE),
            "private_field": re.compile(r"\bprivate\s+\w+\s+\w+;", re.IGNORECASE),
            "synchronized": re.compile(r"\bsynchronized\b", re.IGNORECASE),
            # Import patterns (indicators)
            "forge_import": re.compile(r"import\s+net\.minecraftforge", re.IGNORECASE),
            "mojang_import": re.compile(r"import\s+com\.mojang\.crafting", re.IGNORECASE),
        }

    def detect_features(self, text: str) -> Dict[int, float]:
        """
        Detect Java idiom features in text.

        Returns:
            Dict mapping feature_id -> confidence (0.0 to 1.0)

        Feature IDs follow the convention in sae.py:
        - 1000-1999: Java Forge patterns
        - 2000-2999: Java class patterns
        - 3000-3999: Java API patterns
        """
        self._stats["total_calls"] += 1

        features: Dict[int, float] = {}
        lines = text.split("\n")

        for line_num, line in enumerate(lines, 1):
            for pattern_name, pattern in self.patterns.items():
                if pattern.search(line):
                    feature_id = self._pattern_to_feature_id(pattern_name)
                    confidence = self._calculate_confidence(pattern_name, line, text)

                    if feature_id in features:
                        features[feature_id] = max(features[feature_id], confidence)
                    else:
                        features[feature_id] = confidence

                    self._update_stats(pattern_name)

        return features

    def _pattern_to_feature_id(self, pattern_name: str) -> int:
        """Map pattern name to SAE feature ID"""
        mapping = {
            # Forge patterns -> 1000-1099
            "minecraft_server": 1003,
            "is_client_side": 1004,
            "is_server_side": 1005,
            "add_fresh_entity": 1006,
            "level_get_block_state": 1007,
            "subscribe_event": 1008,
            "register_recipe": 1009,
            "register_entity": 1010,
            "forge_import": 1011,
            "capability_item_handler": 1012,
            "capability_fluid_handler": 1013,
            # Class patterns -> 2000-2099
            "extends_item": 2000,
            "extends_block": 2001,
            "extends_entity": 2002,
            "extends_tile": 2003,
            "implements_interface": 2004,
            "public_class": 2005,
            "private_field": 2006,
            "synchronized": 2007,
            "mod_init": 2008,
            # API patterns -> 3000-3099
            "blockpos_pattern": 3000,
            "itemstack_pattern": 3001,
            "mojang_import": 3002,
            "registry_holder": 3003,
            "is_client_side": 3004,  # Deliberate overlap for weighting
            "is_server_side": 3005,
            "client_side_handlers": 3006,
            "server_side_handlers": 3007,
        }
        return mapping.get(pattern_name, 999)  # Default to 999 for unknown

    def _calculate_confidence(self, pattern_name: str, line: str, full_text: str) -> float:
        """Calculate detection confidence based on context"""
        base_confidence = 0.7

        # Increase confidence for multiple matches
        all_matches = list(self.patterns[pattern_name].finditer(full_text))
        if len(all_matches) > 2:
            base_confidence = min(0.95, 0.7 + (len(all_matches) * 0.05))

        # Increase for class-level declarations
        if "public class" in line and pattern_name == "public_class":
            base_confidence = 0.9

        # Increase for @SubscribeEvent (high-confidence event handling)
        if pattern_name == "subscribe_event":
            base_confidence = 0.95

        return base_confidence

    def _update_stats(self, pattern_name: str) -> None:
        """Update detection statistics"""
        if pattern_name not in self._stats["detections"]:
            self._stats["detections"][pattern_name] = 0
        self._stats["detections"][pattern_name] += 1

    def get_stats(self) -> Dict:
        """Get detection statistics"""
        return self._stats.copy()

    def analyze_java_code(self, java_code: str) -> List[IdiomPattern]:
        """
        Analyze Java code and return list of detected idiom patterns.

        Returns:
            List of IdiomPattern objects sorted by suppression priority
        """
        features = self.detect_features(java_code)

        patterns = []
        for feature_id, confidence in features.items():
            pattern_name = self._feature_id_to_pattern_name(feature_id)
            matched_text = self._find_matching_snippet(java_code, pattern_name)

            patterns.append(
                IdiomPattern(
                    pattern_id=feature_id,
                    pattern_name=pattern_name,
                    confidence=confidence,
                    matched_text=matched_text,
                    line_number=self._find_line_number(java_code, matched_text),
                    suppression_priority=self._get_suppression_priority(feature_id),
                )
            )

        # Sort by suppression priority (highest first)
        patterns.sort(key=lambda p: -p.suppression_priority)
        return patterns

    def _feature_id_to_pattern_name(self, feature_id: int) -> str:
        """Reverse map feature ID to pattern name"""
        mapping = {
            1003: "minecraft_server",
            1004: "is_client_side",
            1005: "is_server_side",
            1006: "add_fresh_entity",
            1007: "level_get_block_state",
            1008: "subscribe_event",
            1009: "register_recipe",
            1010: "register_entity",
            2000: "extends_item",
            2001: "extends_block",
            2002: "extends_entity",
            2003: "extends_tile",
            2004: "implements_interface",
            2005: "public_class",
        }
        return mapping.get(feature_id, "unknown")

    def _find_matching_snippet(self, text: str, pattern_name: str) -> str:
        """Extract the matching text snippet"""
        if pattern_name not in self.patterns:
            return ""
        match = self.patterns[pattern_name].search(text)
        if match:
            # Return surrounding context
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            return text[start:end]
        return ""

    def _find_line_number(self, text: str, snippet: str) -> int:
        """Find line number of snippet in text"""
        if not snippet:
            return 0
        lines = text.split("\n")
        for i, line in enumerate(lines, 1):
            if snippet[:30] in line:
                return i
        return 0

    def _get_suppression_priority(self, feature_id: int) -> int:
        """Get suppression priority for a feature"""
        # Higher priority = more important to suppress
        if 1000 <= feature_id < 1100:
            return 10  # Forge patterns - highest priority
        elif 2000 <= feature_id < 2100:
            return 7  # Class patterns
        elif 3000 <= feature_id < 3100:
            return 8  # API patterns
        return 5  # Default


def detect_java_idioms(text: str) -> List[Tuple[int, float]]:
    """Convenience function to detect Java idioms in text"""
    detector = JavaIdiomHeuristics()
    features = detector.detect_features(text)
    return list(features.items())
