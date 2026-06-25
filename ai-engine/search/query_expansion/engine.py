"""
Main query expansion engine that coordinates expansion strategies.

``QueryExpansionEngine`` combines multiple expansion approaches to create
enhanced queries that improve search recall and precision.
Extracted from the original ``search/query_expansion.py`` monolith (issue #1731).
"""

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from schemas.multimodal_schema import SearchQuery

from .contextual_expander import ContextualExpander
from .domain_expander import MinecraftDomainExpander
from .models import ExpandedQuery, ExpansionStrategy, ExpansionTerm
from .synonym_expander import SynonymExpander

logger = logging.getLogger(__name__)


class QueryExpansionEngine:
    """
    Main query expansion engine that coordinates different expansion strategies.

    This engine combines multiple expansion approaches to create enhanced
    queries that improve search recall and precision.
    """

    def __init__(self):
        self.domain_expander = MinecraftDomainExpander()
        self.synonym_expander = SynonymExpander()
        self.contextual_expander = ContextualExpander()

        self.expansion_strategies = {
            ExpansionStrategy.DOMAIN_EXPANSION: self.domain_expander.expand_domain_terms,
            ExpansionStrategy.SYNONYM_EXPANSION: self.synonym_expander.expand_synonyms,
            ExpansionStrategy.CONTEXTUAL_EXPANSION: self.contextual_expander.expand_contextually,
        }

    def expand_query(
        self,
        query: SearchQuery,
        strategies: List[ExpansionStrategy] = None,
        max_expansion_terms: int = 10,
        session_context: Dict[str, Any] = None,
    ) -> ExpandedQuery:
        """
        Expand a search query using specified strategies.

        Args:
            query: Original search query
            strategies: List of expansion strategies to use
            max_expansion_terms: Maximum number of terms to add
            session_context: Session context for contextual expansion

        Returns:
            Expanded query with metadata
        """
        if strategies is None:
            strategies = [
                ExpansionStrategy.DOMAIN_EXPANSION,
                ExpansionStrategy.SYNONYM_EXPANSION,
                ExpansionStrategy.CONTEXTUAL_EXPANSION,
            ]

        logger.info(f"Expanding query '{query.query_text}' using strategies: {strategies}")

        all_expansion_terms = []
        expansion_metadata = {
            "original_length": len(query.query_text.split()),
            "strategies_used": strategies,
            "strategy_results": {},
        }

        # Apply each expansion strategy
        for strategy in strategies:
            try:
                if strategy == ExpansionStrategy.DOMAIN_EXPANSION:
                    context = session_context or {}
                    terms = self.domain_expander.expand_domain_terms(query.query_text, context)
                elif strategy == ExpansionStrategy.SYNONYM_EXPANSION:
                    terms = self.synonym_expander.expand_synonyms(query.query_text)
                elif strategy == ExpansionStrategy.CONTEXTUAL_EXPANSION:
                    session_id = (
                        session_context.get("session_id", "default")
                        if session_context
                        else "default"
                    )
                    user_id = session_context.get("user_id") if session_context else None
                    terms = self.contextual_expander.expand_contextually(
                        query.query_text, session_id, user_id
                    )
                else:
                    terms = []

                all_expansion_terms.extend(terms)
                expansion_metadata["strategy_results"][strategy] = {
                    "terms_added": len(terms),
                    "avg_confidence": sum(t.confidence for t in terms) / len(terms)
                    if terms
                    else 0.0,
                }

            except Exception as e:
                logger.warning(f"Error in expansion strategy {strategy}: {e}")
                expansion_metadata["strategy_results"][strategy] = {
                    "terms_added": 0,
                    "error": str(e),
                }

        # Remove duplicates and sort by confidence * weight
        unique_terms = {}
        for term in all_expansion_terms:
            term_key = term.term.lower()
            if term_key not in unique_terms or (term.confidence * term.weight) > (
                unique_terms[term_key].confidence * unique_terms[term_key].weight
            ):
                unique_terms[term_key] = term

        # Sort and limit expansion terms
        sorted_terms = sorted(
            unique_terms.values(), key=lambda t: t.confidence * t.weight, reverse=True
        )
        final_expansion_terms = sorted_terms[:max_expansion_terms]

        # Build expanded query
        expansion_text_parts = [term.term for term in final_expansion_terms]
        expanded_query_text = query.query_text

        if expansion_text_parts:
            expanded_query_text += " " + " ".join(expansion_text_parts)

        # Calculate overall expansion confidence
        expansion_confidence = (
            (
                sum(term.confidence * term.weight for term in final_expansion_terms)
                / sum(term.weight for term in final_expansion_terms)
            )
            if final_expansion_terms
            else 0.0
        )

        # Update metadata
        expansion_metadata.update(
            {
                "total_candidate_terms": len(all_expansion_terms),
                "unique_candidate_terms": len(unique_terms),
                "final_expansion_terms": len(final_expansion_terms),
                "expanded_length": len(expanded_query_text.split()),
                "expansion_ratio": len(expanded_query_text.split()) / len(query.query_text.split()),
                "avg_term_confidence": expansion_confidence,
            }
        )

        # Update contextual information for future queries
        if session_context:
            session_id = session_context.get("session_id", "default")
            self.contextual_expander.update_context(query, session_id)

        expanded_query = ExpandedQuery(
            original_query=query.query_text,
            expanded_query=expanded_query_text,
            expansion_terms=final_expansion_terms,
            expansion_confidence=expansion_confidence,
            expansion_metadata=expansion_metadata,
        )

        logger.info(
            f"Query expansion completed: {len(query.query_text.split())} -> "
            f"{len(expanded_query_text.split())} terms"
        )

        return expanded_query

    def get_expansion_explanation(self, expanded_query: ExpandedQuery) -> str:
        """Generate human-readable explanation of query expansion."""
        metadata = expanded_query.expansion_metadata

        explanation_parts = [
            f"Original query: '{expanded_query.original_query}'",
            f"Expanded to {metadata['expanded_length']} terms ({metadata['expansion_ratio']:.1f}x longer)",
        ]

        # Add strategy results
        for strategy, results in metadata["strategy_results"].items():
            if "error" not in results:
                explanation_parts.append(
                    f"{strategy}: added {results['terms_added']} terms "
                    f"(avg confidence: {results['avg_confidence']:.2f})"
                )

        # Add top expansion terms
        if expanded_query.expansion_terms:
            top_terms = expanded_query.expansion_terms[:5]
            term_descriptions = [
                f"{term.term} ({term.expansion_type}, {term.confidence:.2f})" for term in top_terms
            ]
            explanation_parts.append(f"Top expansion terms: {', '.join(term_descriptions)}")

        return "; ".join(explanation_parts)

    def analyze_expansion_effectiveness(
        self,
        expanded_query: ExpandedQuery,
        search_results_count: int,
        user_satisfaction: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Analyze the effectiveness of query expansion.

        Args:
            expanded_query: The expanded query
            search_results_count: Number of results returned
            user_satisfaction: Optional user satisfaction score (0-1)

        Returns:
            Analysis results
        """
        metadata = expanded_query.expansion_metadata

        analysis = {
            "expansion_effectiveness": {
                "results_increase": search_results_count > 0,
                "expansion_confidence": expanded_query.expansion_confidence,
                "term_diversity": len(
                    set(term.expansion_type for term in expanded_query.expansion_terms)
                ),
                "strategy_balance": self._calculate_strategy_balance(
                    expanded_query.expansion_terms
                ),
            },
            "recommendations": [],
        }

        # Add recommendations based on analysis
        if expanded_query.expansion_confidence < 0.5:
            analysis["recommendations"].append(
                "Consider using more conservative expansion strategies"
            )

        if metadata["expansion_ratio"] > 3.0:
            analysis["recommendations"].append("Query expansion may be too aggressive")

        if search_results_count == 0:
            analysis["recommendations"].append(
                "Try alternative expansion strategies or reduce expansion scope"
            )

        if user_satisfaction is not None:
            analysis["user_satisfaction"] = user_satisfaction
            if user_satisfaction < 0.6:
                analysis["recommendations"].append(
                    "User satisfaction low - review expansion strategy effectiveness"
                )

        return analysis

    def _calculate_strategy_balance(
        self, expansion_terms: List[ExpansionTerm]
    ) -> Dict[str, float]:
        """Calculate balance between different expansion strategies."""
        if not expansion_terms:
            return {}

        strategy_counts = Counter(term.expansion_type for term in expansion_terms)
        total_terms = len(expansion_terms)

        return {strategy: count / total_terms for strategy, count in strategy_counts.items()}
