"""
Query expansion system for improving search recall and precision.

This subpackage implements various query expansion techniques to enhance search
queries with additional context and related terms before processing.

Split from the original ``search/query_expansion.py`` monolith (32K) per
issue #1731. The public API is unchanged: existing imports such as
``from search.query_expansion import QueryExpansionEngine`` continue to work.

Module structure:
    - :mod:`.models` — ``ExpansionStrategy`` enum + ``ExpansionTerm`` /
      ``ExpandedQuery`` dataclasses
    - :mod:`.domain_expander` — ``MinecraftDomainExpander`` (domain-specific terms)
    - :mod:`.synonym_expander` — ``SynonymExpander`` (synonym + pattern expansion)
    - :mod:`.contextual_expander` — ``ContextualExpander`` (session/user context)
    - :mod:`.engine` — ``QueryExpansionEngine`` coordinator (entry point)
"""

from .contextual_expander import ContextualExpander
from .domain_expander import MinecraftDomainExpander
from .engine import QueryExpansionEngine
from .models import ExpandedQuery, ExpansionStrategy, ExpansionTerm
from .synonym_expander import SynonymExpander

__all__ = [
    "ContextualExpander",
    "ExpandedQuery",
    "ExpansionStrategy",
    "ExpansionTerm",
    "MinecraftDomainExpander",
    "QueryExpansionEngine",
    "SynonymExpander",
]
