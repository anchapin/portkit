"""
Pattern Selector for Test-Time Scaling

Selects optimal reasoning patterns for conversion tasks at test-time,
enabling dynamic pattern selection based on the specific conversion context.
"""

import logging
from typing import Dict, List, Optional

from .reasoning_pattern import (
    ReasoningPattern,
    ReasoningStep,
    FeatureType,
    HANDCRAFTED_PATTERNS,
)
from .pattern_discovery import PatternDiscoveryEngine

logger = logging.getLogger(__name__)


class PatternSelector:
    """
    Selects optimal reasoning patterns at test-time.

    Uses the discovered patterns from PatternDiscoveryEngine to dynamically
    select the best pattern for each conversion task based on feature
    type detection and contextual analysis.
    """

    def __init__(
        self,
        discovery_engine: Optional[PatternDiscoveryEngine] = None,
    ):
        """
        Initialize pattern selector.

        Args:
            discovery_engine: Optional discovery engine with learned patterns
        """
        self.discovery_engine = discovery_engine
        self.patterns_by_type: Dict[FeatureType, List[ReasoningPattern]] = {
            ft: [] for ft in FeatureType
        }
        self._initialize_defaults()
        self._load_discovered_patterns()

    def _initialize_defaults(self) -> None:
        """Initialize with handcrafted default patterns."""
        for pattern in HANDCRAFTED_PATTERNS:
            self.patterns_by_type[pattern.feature_type].append(pattern)

    def _load_discovered_patterns(self) -> None:
        """Load patterns from discovery engine if available."""
        if self.discovery_engine:
            discovered = self.discovery_engine.get_all_patterns()
            for feature_type, patterns in discovered.items():
                if patterns:
                    existing = {p.id for p in self.patterns_by_type[feature_type]}
                    for pattern in patterns:
                        if pattern.id not in existing:
                            self.patterns_by_type[feature_type].append(pattern)

    def detect_feature_type(self, java_code: str) -> FeatureType:
        """
        Detect the feature type from Java code.

        Args:
            java_code: Java source code to analyze

        Returns:
            Detected feature type
        """
        code_lower = java_code.lower()

        nbt_indicators = ["nbt", "compoundtag", "listtag", "saveadditional", "load", "getitemtag"]
        if any(ind in code_lower for ind in nbt_indicators):
            return FeatureType.NBT_LOGIC

        gui_indicators = [
            "guihandler",
            "screen",
            "button",
            "textfield",
            "container",
            "slot",
            "inventory",
        ]
        if any(ind in code_lower for ind in gui_indicators):
            return FeatureType.GUI

        entity_indicators = [
            "entitytype",
            "pathfindermob",
            "goal_selector",
            "ai_goal",
            "entityspawn",
            "livingentity",
        ]
        if any(ind in code_lower for ind in entity_indicators):
            return FeatureType.ENTITY

        block_indicators = [
            "block",
            "blockstate",
            "blockentity",
            "statedefinition",
            "stateproperties",
        ]
        if any(ind in code_lower for ind in block_indicators):
            return FeatureType.BLOCK

        item_indicators = ["item", "itemstack", "itemproperties", "itebehavior", "durability"]
        if any(ind in code_lower for ind in item_indicators):
            return FeatureType.ITEM

        recipe_indicators = [
            "recipe",
            "shapedrecipe",
            "shapelessrecipe",
            "cookingrecipe",
            "recipebuilder",
        ]
        if any(ind in code_lower for ind in recipe_indicators):
            return FeatureType.RECIPE

        event_indicators = [
            "subscribeevent",
            "eventlistener",
            "eventhandler",
            "onattach",
            "@SubscribeEvent",
        ]
        if any(ind in code_lower for ind in event_indicators):
            return FeatureType.EVENT

        network_indicators = [
            "packet",
            "network",
            " FriendlyByteBuf",
            "encode",
            "decode",
            "CustomPayload",
        ]
        if any(ind in code_lower for ind in network_indicators):
            return FeatureType.NETWORK

        capability_indicators = [
            "capability",
            "iitemhandler",
            "ifluidhandler",
            "provider",
            "getCapability",
        ]
        if any(ind in code_lower for ind in capability_indicators):
            return FeatureType.CAPABILITY

        dimension_indicators = ["dimension", "worldgen", "biome", "chunkgenerator", "dimensiontype"]
        if any(ind in code_lower for ind in dimension_indicators):
            return FeatureType.DIMENSION

        particle_indicators = ["particle", "particleoption", "ParticleType", "ParticleEmitter"]
        if any(ind in code_lower for ind in particle_indicators):
            return FeatureType.PARTICLE

        sound_indicators = ["sound", "soundevent", "SoundType", "audio", "music"]
        if any(ind in code_lower for ind in sound_indicators):
            return FeatureType.SOUND

        rendering_indicators = ["model", "texture", "render", "mesh", "shader", "material"]
        if any(ind in code_lower for ind in rendering_indicators):
            return FeatureType.RENDERING

        command_indicators = ["command", "CommandDispatcher", "ArgumentTypes", "commandbuilder"]
        if any(ind in code_lower for ind in command_indicators):
            return FeatureType.COMMAND

        return FeatureType.UNKNOWN

    def select_pattern(
        self,
        feature_type: FeatureType,
        context: Optional[Dict] = None,
    ) -> ReasoningPattern:
        """
        Select the best pattern for a feature type.

        Args:
            feature_type: The detected or specified feature type
            context: Optional context for selection (e.g., complexity, prior failures)

        Returns:
            Selected reasoning pattern
        """
        patterns = self.patterns_by_type.get(feature_type, [])

        if not patterns:
            patterns = self.patterns_by_type.get(FeatureType.UNKNOWN, [])

        if not patterns:
            return self._get_fallback_pattern()

        context = context or {}
        complexity = context.get("complexity", "medium")

        if complexity == "high" or context.get("high_stakes", False):
            selected = max(patterns, key=lambda p: p.success_threshold)
            logger.info(
                f"High-stakes selection: {selected.id} (threshold={selected.success_threshold})"
            )
            return selected

        scored_patterns = []
        for pattern in patterns:
            score = self._calculate_pattern_score(pattern, context)
            scored_patterns.append((pattern, score))

        scored_patterns.sort(key=lambda x: x[1], reverse=True)
        selected = scored_patterns[0][0]

        logger.info(f"Selected pattern: {selected.id} (score={scored_patterns[0][1]:.4f})")
        return selected

    def _calculate_pattern_score(
        self,
        pattern: ReasoningPattern,
        context: Dict,
    ) -> float:
        """
        Calculate selection score for a pattern.

        Args:
            pattern: Pattern to score
            context: Selection context

        Returns:
            Pattern score (higher is better)
        """
        base_score = 0.5

        if pattern.is_discovered:
            base_score += 0.2

        base_score += pattern.success_threshold * 0.3

        if self.discovery_engine:
            perf_key = f"{pattern.id}_{pattern.feature_type.value}"
            cached = self.discovery_engine.performance_cache.get(perf_key)
            if cached:
                base_score += cached.get_score() * 0.3

        complexity = context.get("complexity", "medium")
        if complexity == "simple" and len(pattern.steps) > 5:
            base_score -= 0.1
        elif complexity == "complex" and len(pattern.steps) < 4:
            base_score += 0.1

        return base_score

    def _get_fallback_pattern(self) -> ReasoningPattern:
        """Get fallback pattern when no patterns available."""
        for pattern in HANDCRAFTED_PATTERNS:
            if pattern.feature_type == FeatureType.UNKNOWN:
                return pattern

        return ReasoningPattern(
            id="fallback_default",
            name="Default Pattern",
            description="Fallback pattern when no specific pattern is available",
            feature_type=FeatureType.UNKNOWN,
            steps=[
                ReasoningStep(
                    1, "Analyze Structure", "Identify the main components and their relationships"
                ),
                ReasoningStep(
                    2, "Map to Bedrock", "Find appropriate Bedrock equivalents for each component"
                ),
                ReasoningStep(
                    3, "Implement Conversion", "Convert the Java logic to Bedrock JavaScript"
                ),
                ReasoningStep(4, "Validate", "Verify the conversion works correctly"),
            ],
            is_handcrafted=True,
        )

    def get_reasoning_prompt(
        self,
        feature_type: FeatureType,
        context: Optional[Dict] = None,
    ) -> str:
        """
        Get the full reasoning prompt for a conversion task.

        Args:
            feature_type: Feature type to get prompt for
            context: Optional context for pattern selection

        Returns:
            Full reasoning prompt for the agent
        """
        pattern = self.select_pattern(feature_type, context)
        return pattern.to_prompt()

    def record_outcome(
        self,
        feature_type: FeatureType,
        pattern_id: str,
        success: bool,
        reward: float,
        confidence: float,
    ) -> None:
        """
        Record conversion outcome for pattern improvement.

        Args:
            feature_type: The feature type that was converted
            pattern_id: ID of the pattern that was used
            success: Whether the conversion succeeded
            reward: Reward score
            confidence: Confidence score
        """
        if self.discovery_engine:
            self.discovery_engine.record_conversion_result(
                pattern_id, feature_type, success, reward, confidence
            )

    def get_pattern_stats(self) -> Dict:
        """Get statistics about available patterns."""
        stats = {
            "total_patterns": 0,
            "by_feature_type": {},
            "discovered_count": 0,
            "handcrafted_count": 0,
        }

        for feature_type, patterns in self.patterns_by_type.items():
            if patterns:
                stats["by_feature_type"][feature_type.value] = len(patterns)
                stats["total_patterns"] += len(patterns)
                stats["discovered_count"] += sum(1 for p in patterns if p.is_discovered)
                stats["handcrafted_count"] += sum(1 for p in patterns if p.is_handcrafted)

        return stats


def create_pattern_selector(
    discovery_engine: Optional[PatternDiscoveryEngine] = None,
) -> PatternSelector:
    """
    Create a configured pattern selector.

    Args:
        discovery_engine: Optional discovery engine with learned patterns

    Returns:
        Configured PatternSelector instance
    """
    return PatternSelector(discovery_engine=discovery_engine)
