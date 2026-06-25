"""
Backward-compatibility shim for the hybrid search engine family.

Issue #1741 split this single 43K file into focused modules:
- search.search_types   -- SearchMode, RankingStrategy, SearchCandidate
- search.keyword_engine -- KeywordSearchEngine
- search.hybrid_engine  -- HybridSearchEngine
- search.unified_engine -- UnifiedSearchEngine

All public symbols are re-exported here so existing imports continue to work.
"""

import logging
from importlib.util import find_spec

logger = logging.getLogger(__name__)

FEEDBACK_RERANKER_AVAILABLE = find_spec("search.feedback_reranker") is not None

from search.hybrid_engine import HybridSearchEngine
from search.keyword_engine import KeywordSearchEngine
from search.search_types import RankingStrategy, SearchCandidate, SearchMode
from search.unified_engine import UnifiedSearchEngine

__all__ = [
    "SearchMode",
    "RankingStrategy",
    "SearchCandidate",
    "KeywordSearchEngine",
    "HybridSearchEngine",
    "UnifiedSearchEngine",
    "FEEDBACK_RERANKER_AVAILABLE",
]