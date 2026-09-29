"""Shared pytest fixtures for the search test-suite.

Hardens every test under ``tests/search/`` against the intermittent
HuggingFace rate-limiting (>120 s timeout under CI parallelism) that
flaked ``test_uae_search_engine.py::test_engine_with_custom_config`` and
its siblings (see issue #1820).

This is the directory-level equivalent of the advanced_rag fix landed in
#1830, lifted one level up so all search-engine tests benefit.
"""

import pytest


@pytest.fixture(autouse=True)
def _huggingface_offline(monkeypatch):
    """Force HuggingFace into offline mode for the whole search test-suite.

    Several search engines (e.g. ``UAESearchEngine``) eagerly construct a
    ``LocalEmbeddingGenerator`` which loads ``sentence-transformers/all-MiniLM-L6-v2``
    during ``__init__``. Under CI parallelism (``-n auto --dist=loadfile``) a cache
    miss triggers a HuggingFace download that gets rate-limited (HTTP 429) and
    exceeds the pytest-timeout budget (>120 s) during construction. With offline
    mode set, a cache miss fails fast and ``LocalEmbeddingGenerator._init_model``
    falls back to its deterministic fallback vectors, so the engine still
    constructs and the search flow remains exercisable — no network, no flakiness,
    coverage preserved. When the model IS cached the real embeddings are used.
    """
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
