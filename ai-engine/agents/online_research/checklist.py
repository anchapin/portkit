"""Feature checklist generation for the Online Research agent.

:class:`FeatureChecklistGenerator` turns research data (descriptions,
categories, metadata) into a list of :class:`~online_research.models.FeatureChecklistItem`
entries used to validate converted Bedrock addons (issue #1730).
"""

from __future__ import annotations

import logging
from typing import Dict, List

from .models import FeatureChecklistItem, SourceType

logger = logging.getLogger(__name__)


class FeatureChecklistGenerator:
    """Generates feature checklists from research data."""

    def __init__(self):
        self.feature_categories = {
            "blocks": ["custom block", "tile entity", "block state"],
            "items": ["custom item", "tool", "armor", "food", "potion"],
            "entities": ["mob", "entity", "projectile", "vehicle"],
            "world": ["dimension", "biome", "structure", "ore generation"],
            "mechanics": ["crafting", "smelting", "breeding", "enchanting"],
            "ui": ["gui", "screen", "inventory", "hud"],
            "audio": ["sound", "music", "ambient"],
            "visuals": ["particle", "effect", "texture", "model"],
        }

    def generate_checklist(
        self, research_data: Dict, source_type: SourceType
    ) -> List[FeatureChecklistItem]:
        """Generate a feature checklist from research data."""
        print("Generating feature checklist...")

        checklist = []

        # Extract features from different sources
        features = []

        # From description
        description = research_data.get("description", "")
        features.extend(self._extract_features_from_text(description))

        # From categories
        categories = research_data.get("categories", [])
        features.extend(self._categorize_features(categories))

        # From additional metadata
        metadata_features = research_data.get("features", [])
        features.extend(metadata_features)

        # Deduplicate and create checklist items
        seen_features = set()
        for feature in features:
            if feature not in seen_features:
                seen_features.add(feature)

                # Determine category
                category = self._determine_category(feature)
                priority = self._determine_priority(feature)

                item = FeatureChecklistItem(
                    feature_name=feature,
                    description=f"Feature detected: {feature}",
                    category=category,
                    priority=priority,
                    detected=True,
                    evidence=["Source analysis"],
                    validation_status="unclear",
                )
                checklist.append(item)

        # Add default checklist items if empty
        if not checklist:
            checklist = self._create_default_checklist()

        print(f"Generated checklist with {len(checklist)} items")
        return checklist

    def _extract_features_from_text(self, text: str) -> List[str]:
        """Extract features from text."""
        features = []

        # Simple keyword extraction
        text_lower = text.lower()

        for category, keywords in self.feature_categories.items():
            for keyword in keywords:
                if keyword in text_lower:
                    features.append(keyword)

        return features

    def _categorize_features(self, categories: List[str]) -> List[str]:
        """Map categories to features."""
        features = []

        category_mapping = {
            "mechanics": ["crafting", "smelting", "breeding"],
            "tools": ["tool", "utility"],
            "adventure": ["dimension", "biome", "structure"],
            "mobs": ["entity", "mob", "spawning"],
            "magic": ["spell", "effect", "potion"],
            "technology": ["machine", "automation", "energy"],
        }

        # Normalize categories: handle both dicts (CurseForge) and strings (Modrinth)
        normalized_categories = []
        for cat in categories:
            if isinstance(cat, dict):
                # CurseForge format: {"name": "Mechanics"}
                normalized_categories.append(cat.get("name", "").lower())
            elif isinstance(cat, str):
                # Modrinth format: "mechanics"
                normalized_categories.append(cat.lower())

        for category in normalized_categories:
            if category in category_mapping:
                features.extend(category_mapping[category])

        return features

    def _determine_category(self, feature: str) -> str:
        """Determine the category of a feature."""
        feature_lower = feature.lower()

        for category, keywords in self.feature_categories.items():
            if any(kw in feature_lower for kw in keywords):
                return category

        return "general"

    def _determine_priority(self, feature: str) -> str:
        """Determine the priority of a feature."""
        feature_lower = feature.lower()

        high_priority = ["dimension", "entity", "custom block", "custom item"]
        medium_priority = ["biome", "structure", "crafting", "recipe"]

        if any(hp in feature_lower for hp in high_priority):
            return "high"
        elif any(mp in feature_lower for mp in medium_priority):
            return "medium"

        return "low"

    def _create_default_checklist(self) -> List[FeatureChecklistItem]:
        """Create a default checklist for unknown mods."""
        return [
            FeatureChecklistItem(
                feature_name="custom blocks",
                description="Custom block definitions",
                category="blocks",
                priority="high",
                detected=True,
                evidence=["Default assumption"],
                validation_status="unclear",
            ),
            FeatureChecklistItem(
                feature_name="custom items",
                description="Custom item definitions",
                category="items",
                priority="high",
                detected=True,
                evidence=["Default assumption"],
                validation_status="unclear",
            ),
            FeatureChecklistItem(
                feature_name="crafting recipes",
                description="Custom crafting recipes",
                category="mechanics",
                priority="medium",
                detected=True,
                evidence=["Default assumption"],
                validation_status="unclear",
            ),
        ]
