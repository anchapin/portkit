"""
Domain-specific query expander for Minecraft modding.

``MinecraftDomainExpander`` understands Minecraft-specific terminology and
concepts to add relevant domain terms to queries.
Extracted from the original ``search/query_expansion.py`` monolith (issue #1731).
"""

import logging
from typing import Any, Dict, List

from .models import ExpansionStrategy, ExpansionTerm

logger = logging.getLogger(__name__)


class MinecraftDomainExpander:
    """
    Domain-specific query expander for Minecraft modding.

    This expander understands Minecraft-specific terminology and concepts
    to add relevant domain terms to queries.
    """

    def __init__(self):
        self.domain_knowledge = self._load_domain_knowledge()
        self.concept_hierarchy = self._build_concept_hierarchy()
        self.version_mappings = self._load_version_mappings()

    def _load_domain_knowledge(self) -> Dict[str, Dict[str, Any]]:
        """Load Minecraft domain knowledge base."""
        return {
            "blocks": {
                "synonyms": ["block", "blocks", "tile", "cube"],
                "related": ["material", "hardness", "tool", "drop", "state"],
                "concepts": ["placement", "breaking", "interaction", "properties"],
                "examples": ["stone", "wood", "dirt", "iron_ore", "diamond_block"],
            },
            "items": {
                "synonyms": ["item", "items", "object", "thing"],
                "related": ["inventory", "stack", "durability", "enchantment"],
                "concepts": ["crafting", "usage", "obtaining", "properties"],
                "examples": ["sword", "pickaxe", "food", "potion", "book"],
            },
            "entities": {
                "synonyms": ["entity", "entities", "mob", "mobs", "creature"],
                "related": ["ai", "behavior", "spawn", "health", "drops"],
                "concepts": ["movement", "combat", "interaction", "breeding"],
                "examples": ["zombie", "villager", "cow", "dragon", "player"],
            },
            "recipes": {
                "synonyms": ["recipe", "recipes", "crafting", "craft"],
                "related": ["ingredients", "pattern", "result", "shapeless"],
                "concepts": ["crafting_table", "furnace", "brewing", "smithing"],
                "examples": ["shaped_recipe", "smelting_recipe", "brewing_recipe"],
            },
            "world_generation": {
                "synonyms": ["worldgen", "generation", "terrain"],
                "related": ["biome", "structure", "ore", "feature"],
                "concepts": ["noise", "placement", "decoration", "population"],
                "examples": ["village", "dungeon", "ore_vein", "tree", "lake"],
            },
            "redstone": {
                "synonyms": ["redstone", "circuit", "wiring", "automation"],
                "related": ["power", "signal", "component", "logic"],
                "concepts": ["activation", "transmission", "gates", "timing"],
                "examples": ["repeater", "comparator", "piston", "dispenser"],
            },
            "modding": {
                "synonyms": ["mod", "mods", "modification", "addon"],
                "related": ["forge", "fabric", "api", "library", "framework"],
                "concepts": ["loading", "compatibility", "dependencies", "events"],
                "examples": ["mod_loader", "mixins", "asm", "coremod"],
            },
        }

    def _build_concept_hierarchy(self) -> Dict[str, List[str]]:
        """Build hierarchical relationships between concepts."""
        return {
            "gameplay": ["blocks", "items", "entities", "recipes", "combat"],
            "technical": ["modding", "redstone", "world_generation", "performance"],
            "content": ["blocks", "items", "entities", "structures", "biomes"],
            "systems": ["crafting", "enchanting", "brewing", "trading", "experience"],
        }

    def _load_version_mappings(self) -> Dict[str, List[str]]:
        """Load version-specific terminology mappings."""
        return {
            "1.19": ["caves_and_cliffs", "deep_dark", "warden", "sculk"],
            "1.20": ["trails_and_tales", "archaeology", "sniffer", "cherry"],
            "bedrock": ["behavior_packs", "resource_packs", "mcaddon", "script_api"],
            "forge": ["mod_bus", "event_handler", "capability", "registry"],
            "fabric": ["mixin", "fabric_api", "mod_initializer", "entry_point"],
        }

    def expand_domain_terms(
        self, query: str, context: Dict[str, Any] = None
    ) -> List[ExpansionTerm]:
        """
        Expand query with domain-specific terms.

        Args:
            query: Original query text
            context: Additional context information

        Returns:
            List of expansion terms with metadata
        """
        expansion_terms = []
        query_lower = query.lower()
        context = context or {}

        # Detect domain concepts in query
        detected_concepts = []
        for concept, data in self.domain_knowledge.items():
            if any(synonym in query_lower for synonym in data["synonyms"]):
                detected_concepts.append(concept)

        # Add related terms for detected concepts
        for concept in detected_concepts:
            concept_data = self.domain_knowledge[concept]

            # Add related terms
            for related_term in concept_data["related"]:
                if related_term.lower() not in query_lower:
                    expansion_terms.append(
                        ExpansionTerm(
                            term=related_term,
                            expansion_type=ExpansionStrategy.DOMAIN_EXPANSION,
                            confidence=0.8,
                            source=f"domain_concept:{concept}",
                            weight=0.7,
                        )
                    )

            # Add concept terms
            for concept_term in concept_data["concepts"]:
                if concept_term.lower() not in query_lower:
                    expansion_terms.append(
                        ExpansionTerm(
                            term=concept_term,
                            expansion_type=ExpansionStrategy.DOMAIN_EXPANSION,
                            confidence=0.7,
                            source=f"domain_concept:{concept}",
                            weight=0.6,
                        )
                    )

        # Add version-specific terms if context available
        target_version = context.get("minecraft_version") or context.get("mod_loader")
        if target_version and target_version in self.version_mappings:
            for version_term in self.version_mappings[target_version]:
                if version_term.lower() not in query_lower:
                    expansion_terms.append(
                        ExpansionTerm(
                            term=version_term,
                            expansion_type=ExpansionStrategy.DOMAIN_EXPANSION,
                            confidence=0.9,
                            source=f"version:{target_version}",
                            weight=0.8,
                        )
                    )

        # Add hierarchical terms
        for parent_concept, child_concepts in self.concept_hierarchy.items():
            if any(child in detected_concepts for child in child_concepts):
                if parent_concept.lower() not in query_lower:
                    expansion_terms.append(
                        ExpansionTerm(
                            term=parent_concept,
                            expansion_type=ExpansionStrategy.DOMAIN_EXPANSION,
                            confidence=0.6,
                            source="concept_hierarchy",
                            weight=0.5,
                        )
                    )

        logger.info(
            f"Domain expansion added {len(expansion_terms)} terms for concepts: {detected_concepts}"
        )
        return expansion_terms
