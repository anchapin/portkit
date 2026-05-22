"""Unit tests for the Document model."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

import pytest

from models.document import Document


class TestDocumentInitialization:
    """Tests for Document dataclass initialization."""

    @pytest.mark.unit
    def test_init_with_required_fields(self):
        """Test creating Document with only required fields."""
        doc = Document(content="Hello world", source="https://example.com")
        assert doc.content == "Hello world"
        assert doc.source == "https://example.com"
        assert doc.doc_type == "generic"
        assert doc.metadata == {}
        assert doc.content_hash is not None

    @pytest.mark.unit
    def test_init_with_all_fields(self):
        """Test creating Document with all fields specified."""
        metadata = {"author": "test", "version": 1}
        doc = Document(
            content="Test content",
            source="test-source",
            doc_type="tutorial",
            metadata=metadata,
            content_hash="custom_hash",
        )
        assert doc.content == "Test content"
        assert doc.source == "test-source"
        assert doc.doc_type == "tutorial"
        assert doc.metadata == metadata
        assert doc.content_hash == "custom_hash"

    @pytest.mark.unit
    def test_default_doc_type(self):
        """Test that default doc_type is 'generic'."""
        doc = Document(content="content", source="source")
        assert doc.doc_type == "generic"

    @pytest.mark.unit
    def test_default_metadata(self):
        """Test that default metadata is an empty dict."""
        doc = Document(content="content", source="source")
        assert doc.metadata == {}

    @pytest.mark.unit
    def test_custom_metadata(self):
        """Test that custom metadata values are preserved."""
        metadata: Dict[str, Any] = {"key1": "value1", "key2": 42, "nested": {"a": 1}}
        doc = Document(content="content", source="source", metadata=metadata)
        assert doc.metadata == metadata
        assert doc.metadata["key1"] == "value1"
        assert doc.metadata["nested"] == {"a": 1}


class TestDocumentPostInit:
    """Tests for Document.__post_init__ hash generation."""

    @pytest.mark.unit
    def test_post_init_generates_hash_when_none(self):
        """Test that __post_init__ generates content_hash when not provided."""
        content = "Test content for hashing"
        doc = Document(content=content, source="source")
        expected_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        assert doc.content_hash == expected_hash

    @pytest.mark.unit
    def test_post_init_preserves_existing_hash(self):
        """Test that __post_init__ preserves content_hash if already set."""
        existing_hash = "existing_hash_value"
        doc = Document(
            content="Some content",
            source="source",
            content_hash=existing_hash,
        )
        assert doc.content_hash == existing_hash

    @pytest.mark.unit
    def test_post_init_no_hash_when_content_empty(self):
        """Test that __post_init__ does not generate hash for empty content."""
        doc = Document(content="", source="source")
        assert doc.content_hash is None

    @pytest.mark.unit
    def test_post_init_no_hash_when_content_empty(self):
        """Test that __post_init__ does not generate hash for empty content."""
        doc = Document(content="", source="source")
        assert doc.content_hash is None

    @pytest.mark.unit
    def test_post_init_generates_hash_for_whitespace_content(self):
        """Test that __post_init__ generates hash for whitespace-only content.

        Note: whitespace-only strings are truthy in Python (bool("   ") == True),
        so the implementation hashes them since content is non-empty.
        """
        doc = Document(content="   ", source="source")
        assert doc.content_hash is not None
        assert len(doc.content_hash) == 32

    @pytest.mark.unit
    def test_post_init_hash_consistency(self):
        """Test that same content produces same hash."""
        content = "Consistent content"
        doc1 = Document(content=content, source="source1")
        doc2 = Document(content=content, source="source2")
        assert doc1.content_hash == doc2.content_hash

    @pytest.mark.unit
    def test_post_init_different_content_different_hash(self):
        """Test that different content produces different hashes."""
        doc1 = Document(content="Content A", source="source")
        doc2 = Document(content="Content B", source="source")
        assert doc1.content_hash != doc2.content_hash

    @pytest.mark.unit
    def test_post_init_hash_length(self):
        """Test that generated hash is MD5 hex length (32 characters)."""
        doc = Document(content="Any content here", source="source")
        assert doc.content_hash is not None
        assert len(doc.content_hash) == 32
        # MD5 hashes are hexadecimal (0-9, a-f)
        assert all(c in "0123456789abcdef" for c in doc.content_hash)


class TestDocumentFieldAccess:
    """Tests for Document field access."""

    @pytest.mark.unit
    def test_content_access(self):
        """Test accessing content field."""
        doc = Document(content="Hello", source="source")
        assert doc.content == "Hello"

    @pytest.mark.unit
    def test_source_access(self):
        """Test accessing source field."""
        doc = Document(content="content", source="https://api.example.com/docs")
        assert doc.source == "https://api.example.com/docs"

    @pytest.mark.unit
    def test_doc_type_access(self):
        """Test accessing doc_type field."""
        doc = Document(content="content", source="source", doc_type="api_reference")
        assert doc.doc_type == "api_reference"

    @pytest.mark.unit
    def test_content_hash_access(self):
        """Test accessing content_hash field."""
        doc = Document(content="content", source="source")
        assert doc.content_hash is not None
        assert isinstance(doc.content_hash, str)