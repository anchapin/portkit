"""
Contextual query expander using session and user context.

``ContextualExpander`` adds terms based on previous queries, user preferences,
and session context to personalize search results.
Extracted from the original ``search/query_expansion.py`` monolith (issue #1731).
"""

import logging
from collections import Counter, defaultdict
from typing import List

from schemas.multimodal_schema import SearchQuery

from .models import ExpansionStrategy, ExpansionTerm

logger = logging.getLogger(__name__)


class ContextualExpander:
    """
    Contextual query expander that uses session and user context.

    This expander adds terms based on previous queries, user preferences,
    and session context to personalize search results.
    """

    def __init__(self):
        self.session_context = {}
        self.user_profiles = {}
        self.query_history = defaultdict(list)

    def update_context(self, query: SearchQuery, session_id: str = "default"):
        """Update contextual information."""
        if session_id not in self.session_context:
            self.session_context[session_id] = {
                "recent_queries": [],
                "topics": Counter(),
                "content_types": Counter(),
                "complexity_level": "medium",
            }

        context = self.session_context[session_id]

        # Add to recent queries
        context["recent_queries"].append(query.query_text)
        context["recent_queries"] = context["recent_queries"][-10:]  # Keep last 10

        # Update topic interests
        topics = self._extract_topics(query.query_text)
        for topic in topics:
            context["topics"][topic] += 1

        # Update content type preferences
        if query.content_types:
            for content_type in query.content_types:
                context["content_types"][content_type] += 1

        # Update complexity level based on query
        complexity = self._assess_query_complexity(query.query_text)
        if complexity != context["complexity_level"]:
            context["complexity_level"] = complexity

    def expand_contextually(
        self, query: str, session_id: str = "default", user_id: str = None
    ) -> List[ExpansionTerm]:
        """
        Expand query based on contextual information.

        Args:
            query: Original query text
            session_id: Session identifier
            user_id: User identifier (optional)

        Returns:
            List of contextual expansion terms
        """
        expansion_terms = []

        # Get session context
        context = self.session_context.get(session_id, {})

        # Add terms from recent topics
        topic_interests = context.get("topics", Counter())
        for topic, frequency in topic_interests.most_common(5):
            if topic.lower() not in query.lower() and frequency > 1:
                confidence = min(0.5 + (frequency * 0.1), 0.9)
                expansion_terms.append(
                    ExpansionTerm(
                        term=topic,
                        expansion_type=ExpansionStrategy.CONTEXTUAL_EXPANSION,
                        confidence=confidence,
                        source=f"session_topic:frequency_{frequency}",
                        weight=0.5,
                    )
                )

        # Add terms from similar previous queries
        recent_queries = context.get("recent_queries", [])
        for prev_query in recent_queries[-5:]:
            similarity = self._calculate_query_similarity(query, prev_query)
            if similarity > 0.6:
                prev_terms = set(prev_query.lower().split()) - set(query.lower().split())
                for term in list(prev_terms)[:3]:  # Add up to 3 terms
                    expansion_terms.append(
                        ExpansionTerm(
                            term=term,
                            expansion_type=ExpansionStrategy.CONTEXTUAL_EXPANSION,
                            confidence=similarity,
                            source=f"similar_query:similarity_{similarity:.2f}",
                            weight=0.4,
                        )
                    )

        # Add complexity-appropriate terms
        complexity_level = context.get("complexity_level", "medium")
        complexity_terms = self._get_complexity_terms(complexity_level)
        for term in complexity_terms:
            if term.lower() not in query.lower():
                expansion_terms.append(
                    ExpansionTerm(
                        term=term,
                        expansion_type=ExpansionStrategy.CONTEXTUAL_EXPANSION,
                        confidence=0.6,
                        source=f"complexity_level:{complexity_level}",
                        weight=0.3,
                    )
                )

        # Add user profile terms if available
        if user_id and user_id in self.user_profiles:
            profile_terms = self._get_user_profile_terms(user_id, query)
            expansion_terms.extend(profile_terms)

        logger.info(
            f"Contextual expansion added {len(expansion_terms)} terms for session {session_id}"
        )
        return expansion_terms

    def _extract_topics(self, query: str) -> List[str]:
        """Extract topics from query text."""
        # Simplified topic extraction
        minecraft_topics = {
            "blocks",
            "items",
            "entities",
            "recipes",
            "crafting",
            "redstone",
            "modding",
            "forge",
            "fabric",
            "java",
            "bedrock",
            "biomes",
            "structures",
            "world_generation",
            "automation",
            "building",
        }

        query_lower = query.lower()
        detected_topics = []

        for topic in minecraft_topics:
            if topic in query_lower:
                detected_topics.append(topic)

        return detected_topics

    def _assess_query_complexity(self, query: str) -> str:
        """Assess the complexity level of a query."""
        complexity_indicators = {
            "simple": ["how", "what", "simple", "basic", "easy"],
            "advanced": ["advanced", "complex", "detailed", "comprehensive", "optimize"],
            "technical": ["implement", "algorithm", "performance", "architecture", "design"],
        }

        query_lower = query.lower()

        for level, indicators in complexity_indicators.items():
            if any(indicator in query_lower for indicator in indicators):
                return level

        # Default to medium if no specific indicators
        return "medium"

    def _get_complexity_terms(self, complexity_level: str) -> List[str]:
        """Get terms appropriate for the complexity level."""
        complexity_terms = {
            "simple": ["basic", "easy", "beginner", "introduction", "getting started"],
            "medium": ["tutorial", "guide", "example", "walkthrough"],
            "advanced": ["advanced", "detailed", "comprehensive", "optimization", "best practices"],
            "technical": [
                "implementation",
                "architecture",
                "design patterns",
                "performance",
                "scalability",
            ],
        }

        return complexity_terms.get(complexity_level, [])

    def _calculate_query_similarity(self, query1: str, query2: str) -> float:
        """Calculate similarity between two queries."""
        words1 = set(query1.lower().split())
        words2 = set(query2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def _get_user_profile_terms(self, user_id: str, query: str) -> List[ExpansionTerm]:
        """Get expansion terms from user profile."""
        profile = self.user_profiles.get(user_id, {})
        expansion_terms = []

        # Add terms from user's favorite topics
        favorite_topics = profile.get("favorite_topics", [])
        for topic in favorite_topics:
            if topic.lower() not in query.lower():
                expansion_terms.append(
                    ExpansionTerm(
                        term=topic,
                        expansion_type=ExpansionStrategy.CONTEXTUAL_EXPANSION,
                        confidence=0.7,
                        source="user_profile:favorite_topic",
                        weight=0.6,
                    )
                )

        return expansion_terms
