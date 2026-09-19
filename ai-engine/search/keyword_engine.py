"""
Keyword search engine with BM25 ranking and fuzzy/stemming support.

Extracted from the original ``hybrid_search_engine.py`` (issue #1741).
This engine is independent of the vector/hybrid fusion logic and can be
swapped or tested in isolation.
"""

import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from rank_bm25 import BM25Okapi

from schemas.multimodal_schema import MultiModalDocument

logger = logging.getLogger(__name__)


class KeywordSearchEngine:
    """
    Advanced keyword search engine with fuzzy matching and stemming.

    This engine provides sophisticated text matching capabilities including
    fuzzy matching, stemming, and domain-specific term recognition.
    """

    def __init__(self):
        self.stop_words = self._load_stop_words()
        self.minecraft_terms = self._load_minecraft_terms()
        self.programming_terms = self._load_programming_terms()

    def _load_stop_words(self) -> Set[str]:
        """Load common stop words to filter out."""
        return {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
        }

    def _load_minecraft_terms(self) -> Dict[str, List[str]]:
        """Load Minecraft-specific terms and their synonyms."""
        return {
            "block": ["blocks", "cube", "tile"],
            "item": ["items", "object", "tool", "weapon"],
            "entity": ["entities", "mob", "mobs", "creature", "npc"],
            "recipe": ["recipes", "crafting", "craft", "make", "create"],
            "texture": ["textures", "skin", "sprite", "image", "visual"],
            "biome": ["biomes", "environment", "terrain", "landscape"],
            "dimension": ["dimensions", "world", "realm", "plane"],
            "redstone": ["circuit", "wiring", "automation", "logic"],
            "forge": ["mod", "modification", "modding", "addon"],
            "bedrock": ["pocket", "mobile", "cross-platform"],
        }

    def _load_programming_terms(self) -> Dict[str, List[str]]:
        """Load programming-specific terms and their synonyms."""
        return {
            "class": ["classes", "object", "type", "definition"],
            "method": ["methods", "function", "procedure", "routine"],
            "variable": ["variables", "var", "field", "property"],
            "import": ["imports", "include", "require", "dependency"],
            "interface": ["interfaces", "contract", "protocol"],
            "abstract": ["abstraction", "base", "template"],
            "static": ["shared", "class-level"],
            "public": ["accessible", "exposed", "visible"],
            "private": ["hidden", "internal", "encapsulated"],
            "constructor": ["init", "initialize", "create", "instantiate"],
        }

    def extract_keywords(self, text: str, include_synonyms: bool = True) -> List[str]:
        """
        Extract and normalize keywords from text.

        Args:
            text: Input text to extract keywords from
            include_synonyms: Whether to include domain-specific synonyms

        Returns:
            List of normalized keywords
        """
        # Convert to lowercase and split into words
        words = re.findall(r"\b\w+\b", text.lower())

        # Filter stop words
        keywords = [word for word in words if word not in self.stop_words and len(word) > 2]

        # Add domain-specific synonyms
        if include_synonyms:
            expanded_keywords = []
            for keyword in keywords:
                expanded_keywords.append(keyword)

                # Add Minecraft synonyms
                for term, synonyms in self.minecraft_terms.items():
                    if keyword == term or keyword in synonyms:
                        expanded_keywords.extend([term] + synonyms)

                # Add programming synonyms
                for term, synonyms in self.programming_terms.items():
                    if keyword == term or keyword in synonyms:
                        expanded_keywords.extend([term] + synonyms)

            keywords = list(set(expanded_keywords))  # Remove duplicates

        return keywords

    def calculate_keyword_similarity(
        self, query_keywords: List[str], document_text: str
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate keyword-based similarity score.

        Args:
            query_keywords: Keywords extracted from the query
            document_text: Text content of the document

        Returns:
            Tuple of (similarity_score, explanation_metadata)
        """
        if not query_keywords or not document_text:
            return 0.0, {}

        doc_keywords = self.extract_keywords(document_text, include_synonyms=False)
        doc_keyword_counts = Counter(doc_keywords)

        # Calculate term frequency-inverse document frequency (TF-IDF) style scoring
        matched_terms = []
        total_score = 0.0

        for query_keyword in query_keywords:
            # Exact match
            if query_keyword in doc_keyword_counts:
                tf = doc_keyword_counts[query_keyword]
                # Simple TF score (could be enhanced with IDF)
                term_score = 1.0 + math.log(tf)
                total_score += term_score
                matched_terms.append(
                    {
                        "term": query_keyword,
                        "frequency": tf,
                        "score": term_score,
                        "match_type": "exact",
                    }
                )
            else:
                # Fuzzy match
                fuzzy_matches = self._find_fuzzy_matches(query_keyword, doc_keywords)
                for match, similarity in fuzzy_matches:
                    if similarity > 0.8:  # High similarity threshold
                        tf = doc_keyword_counts[match]
                        term_score = similarity * (1.0 + math.log(tf))
                        total_score += term_score
                        matched_terms.append(
                            {
                                "term": query_keyword,
                                "matched_term": match,
                                "frequency": tf,
                                "score": term_score,
                                "similarity": similarity,
                                "match_type": "fuzzy",
                            }
                        )

        # Normalize score by query length
        normalized_score = total_score / len(query_keywords) if query_keywords else 0.0

        # Apply length penalty for very short or very long documents
        doc_length_penalty = self._calculate_length_penalty(len(doc_keywords))
        final_score = normalized_score * doc_length_penalty

        explanation = {
            "matched_terms": matched_terms,
            "query_keyword_count": len(query_keywords),
            "doc_keyword_count": len(doc_keywords),
            "total_matches": len(matched_terms),
            "raw_score": total_score,
            "normalized_score": normalized_score,
            "length_penalty": doc_length_penalty,
            "final_score": final_score,
        }

        return min(final_score, 1.0), explanation

    def _find_fuzzy_matches(
        self, query_term: str, doc_keywords: List[str], max_matches: int = 3
    ) -> List[Tuple[str, float]]:
        """Find fuzzy matches for a query term in document keywords."""
        matches = []

        for doc_keyword in doc_keywords:
            similarity = self._calculate_edit_distance_similarity(query_term, doc_keyword)
            if similarity > 0.6:  # Minimum similarity threshold
                matches.append((doc_keyword, similarity))

        # Sort by similarity and return top matches
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:max_matches]

    def _calculate_edit_distance_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity based on edit distance."""
        if str1 == str2:
            return 1.0

        # Simple Levenshtein distance implementation
        len1, len2 = len(str1), len(str2)
        if len1 == 0:
            return 0.0 if len2 > 0 else 1.0
        if len2 == 0:
            return 0.0

        # Create distance matrix
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        # Initialize first row and column
        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j

        # Fill the matrix
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if str1[i - 1] == str2[j - 1] else 1
                matrix[i][j] = min(
                    matrix[i - 1][j] + 1,  # deletion
                    matrix[i][j - 1] + 1,  # insertion
                    matrix[i - 1][j - 1] + cost,  # substitution
                )

        # Calculate similarity as (1 - normalized_distance)
        max_len = max(len1, len2)
        distance = matrix[len1][len2]
        similarity = 1.0 - (distance / max_len)

        return max(similarity, 0.0)

    def _calculate_length_penalty(self, doc_length: int) -> float:
        """Calculate length penalty to favor documents of appropriate length."""
        # Optimal length range (in terms of keyword count)
        optimal_min, optimal_max = 10, 100

        if optimal_min <= doc_length <= optimal_max:
            return 1.0
        elif doc_length < optimal_min:
            # Penalty for very short documents
            return 0.5 + 0.5 * (doc_length / optimal_min)
        else:
            # Penalty for very long documents
            excess = doc_length - optimal_max
            penalty = 1.0 / (1.0 + 0.01 * excess)
            return max(penalty, 0.3)  # Minimum penalty

    # BM25-specific attributes
    _bm25_index: Optional[Any] = None
    _bm25_documents: List[str] = []

    def build_bm25_index(self, documents: Dict[str, MultiModalDocument]) -> bool:
        """
        Build a BM25 index from documents for keyword search.

        Args:
            documents: Dictionary of document_id to MultiModalDocument

        Returns:
            True if index was built successfully, False otherwise
        """
        try:
            # Prepare documents for BM25 (tokenized)
            self._bm25_documents = []
            doc_ids = []

            for doc_id, doc in documents.items():
                if doc.content_text:
                    # Tokenize: lowercase and split on whitespace/punctuation
                    tokens = re.findall(r"\b\w+\b", doc.content_text.lower())
                    # Filter out stop words
                    tokens = [t for t in tokens if t not in self.stop_words and len(t) > 1]
                    self._bm25_documents.append(tokens)
                    doc_ids.append(doc_id)

            if not self._bm25_documents:
                logger.warning("No documents with content to index for BM25")
                return False

            # Build BM25 index
            self._bm25_index = BM25Okapi(self._bm25_documents)
            logger.info(f"Built BM25 index with {len(self._bm25_documents)} documents")
            return True

        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
            return False

    def search_bm25(
        self,
        query: str,
        documents: Dict[str, MultiModalDocument],
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        Search documents using BM25 algorithm.

        Args:
            query: Search query text
            documents: Dictionary of document_id to MultiModalDocument
            top_k: Number of top results to return

        Returns:
            List of (document_id, bm25_score) tuples
        """
        if self._bm25_index is None:
            # Fall back to simple keyword search
            query_keywords = self.extract_keywords(query)
            results = []
            for doc_id, doc in documents.items():
                if doc.content_text:
                    score, _ = self.calculate_keyword_similarity(query_keywords, doc.content_text)
                    results.append((doc_id, score))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        try:
            # Tokenize query
            query_tokens = re.findall(r"\b\w+\b", query.lower())
            query_tokens = [t for t in query_tokens if t not in self.stop_words and len(t) > 1]

            if not query_tokens:
                return []

            # Get BM25 scores
            scores = self._bm25_index.get_scores(query_tokens)

            # Map scores back to document IDs
            doc_ids = list(documents.keys())
            results = []
            for i, score in enumerate(scores):
                if i < len(doc_ids):
                    results.append((doc_ids[i], score))

            # Normalize scores to 0-1 range
            if results:
                max_score = max(s for _, s in results)
                if max_score > 0:
                    results = [(doc_id, score / max_score) for doc_id, score in results]

            # Sort by score and return top_k
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            # Fall back to simple keyword search
            query_keywords = self.extract_keywords(query)
            results = []
            for doc_id, doc in documents.items():
                if doc.content_text:
                    score, _ = self.calculate_keyword_similarity(query_keywords, doc.content_text)
                    results.append((doc_id, score))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
