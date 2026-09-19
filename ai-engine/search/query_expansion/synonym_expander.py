"""
Synonym-based query expander.

``SynonymExpander`` adds synonyms and alternative terms to improve query
coverage and recall.
Extracted from the original ``search/query_expansion.py`` monolith (issue #1731).
"""

import logging
from typing import Dict, List

from .models import ExpansionStrategy, ExpansionTerm

logger = logging.getLogger(__name__)


class SynonymExpander:
    """
    Synonym-based query expander.

    This expander adds synonyms and alternative terms to improve
    query coverage and recall.
    """

    def __init__(self):
        self.synonym_database = self._load_synonyms()
        self.programming_terms = self._load_programming_synonyms()
        self.common_expansions = self._load_common_expansions()

    def _load_synonyms(self) -> Dict[str, List[str]]:
        """Load general synonym database."""
        return {
            "create": ["make", "build", "generate", "construct", "develop"],
            "implement": ["create", "build", "develop", "code", "write"],
            "fix": ["repair", "solve", "correct", "debug", "resolve"],
            "error": ["bug", "issue", "problem", "exception", "failure"],
            "guide": ["tutorial", "howto", "instructions", "walkthrough"],
            "example": ["sample", "demo", "illustration", "case", "instance"],
            "simple": ["basic", "easy", "elementary", "straightforward"],
            "advanced": ["complex", "sophisticated", "detailed", "comprehensive"],
            "quick": ["fast", "rapid", "swift", "speedy", "brief"],
            "complete": ["full", "comprehensive", "thorough", "entire"],
            "custom": ["personalized", "tailored", "bespoke", "specialized"],
            "optimize": ["improve", "enhance", "streamline", "efficient"],
        }

    def _load_programming_synonyms(self) -> Dict[str, List[str]]:
        """Load programming-specific synonyms."""
        return {
            "function": ["method", "procedure", "routine", "subroutine"],
            "variable": ["var", "field", "property", "attribute"],
            "class": ["object", "type", "entity", "model"],
            "interface": ["contract", "protocol", "api", "specification"],
            "library": ["framework", "package", "module", "dependency"],
            "import": ["include", "require", "load", "reference"],
            "export": ["expose", "provide", "publish", "output"],
            "initialize": ["init", "setup", "create", "instantiate"],
            "parameter": ["argument", "input", "param", "value"],
            "return": ["output", "result", "response", "yield"],
        }

    def _load_common_expansions(self) -> Dict[str, Dict[str, List[str]]]:
        """Load common query expansion patterns."""
        return {
            "how_to_patterns": {
                "triggers": ["how", "howto", "how to"],
                "expansions": ["tutorial", "guide", "instructions", "steps", "walkthrough"],
            },
            "what_is_patterns": {
                "triggers": ["what is", "what are", "define", "definition"],
                "expansions": ["explanation", "meaning", "concept", "overview", "introduction"],
            },
            "example_patterns": {
                "triggers": ["example", "examples", "sample"],
                "expansions": ["demo", "illustration", "case study", "use case", "instance"],
            },
            "troubleshooting_patterns": {
                "triggers": ["error", "problem", "issue", "bug", "not working"],
                "expansions": ["fix", "solve", "debug", "troubleshoot", "resolution"],
            },
        }

    def expand_synonyms(self, query: str) -> List[ExpansionTerm]:
        """
        Expand query with synonyms.

        Args:
            query: Original query text

        Returns:
            List of synonym expansion terms
        """
        expansion_terms = []
        query_words = query.lower().split()

        # Expand individual words
        for word in query_words:
            # Check general synonyms
            if word in self.synonym_database:
                for synonym in self.synonym_database[word]:
                    if synonym not in query.lower():
                        expansion_terms.append(
                            ExpansionTerm(
                                term=synonym,
                                expansion_type=ExpansionStrategy.SYNONYM_EXPANSION,
                                confidence=0.8,
                                source=f"synonym:{word}",
                                weight=0.7,
                            )
                        )

            # Check programming synonyms
            if word in self.programming_terms:
                for synonym in self.programming_terms[word]:
                    if synonym not in query.lower():
                        expansion_terms.append(
                            ExpansionTerm(
                                term=synonym,
                                expansion_type=ExpansionStrategy.SYNONYM_EXPANSION,
                                confidence=0.9,
                                source=f"programming_synonym:{word}",
                                weight=0.8,
                            )
                        )

        # Expand common patterns
        query_lower = query.lower()
        for pattern_name, pattern_data in self.common_expansions.items():
            if any(trigger in query_lower for trigger in pattern_data["triggers"]):
                for expansion in pattern_data["expansions"]:
                    if expansion not in query_lower:
                        expansion_terms.append(
                            ExpansionTerm(
                                term=expansion,
                                expansion_type=ExpansionStrategy.SYNONYM_EXPANSION,
                                confidence=0.7,
                                source=f"pattern:{pattern_name}",
                                weight=0.6,
                            )
                        )

        logger.info(f"Synonym expansion added {len(expansion_terms)} terms")
        return expansion_terms
