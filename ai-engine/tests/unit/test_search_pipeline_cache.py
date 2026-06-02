"""
Unit tests for search/pipeline_cache.py - MemoryCache class.

Tests cover:
- MemoryCache.get() - cache miss scenarios
- MemoryCache.set()
- MemoryCache.delete()
- MemoryCache.invalidate()
- MemoryCache.get_stats()
- LRU eviction logic
"""

import pytest
import time
from datetime import datetime, timezone

from search.pipeline_cache import MemoryCache, CachedResult


class TestMemoryCacheGet:
    """Test MemoryCache.get() method."""

    def test_get_cache_miss_returns_none(self):
        """Test that get returns None for non-existent key."""
        cache = MemoryCache(max_size=100, ttl=3600)
        result = cache.get("nonexistent_key")
        assert result is None

    def test_get_cache_miss_increments_miss_counter(self):
        """Test that cache miss increments miss counter."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.get("nonexistent")
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_get_expired_entry_returns_none(self):
        """Test that get returns None for expired entry."""
        cache = MemoryCache(max_size=100, ttl=1)
        cache.set("key", {"data": "value"})
        time.sleep(1.5)
        result = cache.get("key")
        assert result is None

    def test_get_expired_increments_miss_counter(self):
        """Test that accessing expired entry increments miss counter."""
        cache = MemoryCache(max_size=100, ttl=1)
        cache.set("key", {"data": "value"})
        time.sleep(1.5)
        cache.get("key")
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_get_valid_entry_returns_cached_result(self):
        """Test that get returns cached result for valid entry."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"data": "test_value"})
        result = cache.get("key")
        assert result is not None
        assert result.data == {"data": "test_value"}

    def test_get_valid_entry_increments_hit_counter(self):
        """Test that cache hit increments hit counter."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"data": "value"})
        cache.get("key")
        stats = cache.get_stats()
        assert stats["hits"] == 1

    def test_get_updates_lru_order(self):
        """Test that get moves accessed key to end (LRU behavior)."""
        cache = MemoryCache(max_size=3, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        cache.set("key3", {"data": "3"})
        cache.get("key1")
        cache.set("key4", {"data": "4"})
        result = cache.get("key1")
        assert result is not None


class TestMemoryCacheSet:
    """Test MemoryCache.set() method."""

    def test_set_basic_dict(self):
        """Test setting a dict value."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"results": ["doc1", "doc2"]})
        result = cache.get("key")
        assert result is not None
        assert result.data == {"results": ["doc1", "doc2"]}

    def test_set_with_custom_ttl(self):
        """Test setting with custom TTL."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"data": "value"}, ttl=60)
        cached = cache.get("key")
        assert cached.ttl == 60

    def test_set_with_default_ttl(self):
        """Test setting uses cache's default TTL."""
        cache = MemoryCache(max_size=100, ttl=1800)
        cache.set("key", {"data": "value"})
        cached = cache.get("key")
        assert cached.ttl == 1800

    def test_set_cached_result_directly(self):
        """Test setting a CachedResult directly."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cached = CachedResult(data={"direct": "result"}, ttl=300)
        cache.set("key", cached)
        result = cache.get("key")
        assert result is not None
        assert result.data == {"direct": "result"}
        assert result.ttl == 300

    def test_set_preserves_results_field(self):
        """Test that set preserves results field for backwards compat."""
        cache = MemoryCache(max_size=100, ttl=3600)
        data = {"results": ["r1", "r2"], "query_analysis": "test"}
        cache.set("key", data)
        result = cache.get("key")
        assert result.results == ["r1", "r2"]

    def test_set_updates_existing_key(self):
        """Test that set updates existing key and moves to end."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"data": "first"})
        cache.set("key", {"data": "second"})
        result = cache.get("key")
        assert result.data == {"data": "second"}


class TestMemoryCacheDelete:
    """Test MemoryCache.delete() method."""

    def test_delete_existing_key(self):
        """Test deleting an existing key."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"data": "value"})
        cache.delete("key")
        result = cache.get("key")
        assert result is None

    def test_delete_nonexistent_key(self):
        """Test deleting a non-existent key does not raise."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.delete("nonexistent")
        result = cache.get("nonexistent")
        assert result is None

    def test_delete_reduces_cache_size(self):
        """Test that delete reduces cache size."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        assert cache.get_stats()["size"] == 2
        cache.delete("key1")
        assert cache.get_stats()["size"] == 1


class TestMemoryCacheInvalidate:
    """Test MemoryCache.invalidate() method."""

    def test_invalidate_all_clears_cache(self):
        """Test that invalidate with no pattern clears all entries."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        cache.invalidate()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get_stats()["size"] == 0

    def test_invalidate_with_pattern_deletes_matching(self):
        """Test that invalidate with pattern deletes matching keys."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("query:java", {"data": "java"})
        cache.set("query:python", {"data": "python"})
        cache.set("query:rust", {"data": "rust"})
        cache.invalidate(pattern="java")
        assert cache.get("query:java") is None
        assert cache.get("query:python") is not None
        assert cache.get("query:rust") is not None

    def test_invalidate_pattern_no_match(self):
        """Test that invalidate with non-matching pattern does nothing."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.invalidate(pattern="nonexistent")
        assert cache.get("key1") is not None

    def test_invalidate_multiple_pattern_matches(self):
        """Test invalidating multiple keys with same pattern prefix."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("user:1:data", {"data": "1"})
        cache.set("user:1:profile", {"data": "2"})
        cache.set("user:2:data", {"data": "3"})
        cache.invalidate(pattern="user:1:")
        assert cache.get("user:1:data") is None
        assert cache.get("user:1:profile") is None
        assert cache.get("user:2:data") is not None


class TestMemoryCacheGetStats:
    """Test MemoryCache.get_stats() method."""

    def test_stats_initial_state(self):
        """Test stats for empty cache."""
        cache = MemoryCache(max_size=100, ttl=3600)
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["size"] == 0
        assert stats["max_size"] == 100
        assert stats["ttl"] == 3600

    def test_stats_hit_rate_calculation(self):
        """Test hit rate is calculated correctly."""
        cache = MemoryCache(max_size=100, ttl=3600)
        cache.set("key", {"data": "value"})
        cache.get("key")
        cache.get("key")
        cache.get("missing")
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3)

    def test_stats_hit_rate_zero_total(self):
        """Test hit rate is 0 when no operations performed."""
        cache = MemoryCache(max_size=100, ttl=3600)
        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_stats_size_reflects_cache_contents(self):
        """Test size in stats reflects actual cache contents."""
        cache = MemoryCache(max_size=100, ttl=3600)
        for i in range(10):
            cache.set(f"key{i}", {"data": i})
        stats = cache.get_stats()
        assert stats["size"] == 10


class TestMemoryCacheLRUEviction:
    """Test LRU eviction logic in MemoryCache."""

    def test_lru_eviction_removes_oldest(self):
        """Test that LRU eviction removes oldest (first) entry."""
        cache = MemoryCache(max_size=3, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        cache.set("key3", {"data": "3"})
        cache.set("key4", {"data": "4"})
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_lru_get_moves_to_end(self):
        """Test that get moves accessed item to end, protecting from eviction."""
        cache = MemoryCache(max_size=3, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        cache.set("key3", {"data": "3"})
        cache.get("key1")
        cache.set("key4", {"data": "4"})
        assert cache.get("key1") is not None
        assert cache.get("key4") is not None

    def test_lru_set_existing_moves_to_end(self):
        """Test that updating existing key moves it to end."""
        cache = MemoryCache(max_size=3, ttl=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        cache.set("key3", {"data": "3"})
        cache.set("key1", {"data": "1_updated"})
        cache.set("key4", {"data": "4"})
        assert cache.get("key1") is not None
        assert cache.get("key1").data == {"data": "1_updated"}

    def test_lru_exact_max_size(self):
        """Test cache does not exceed max_size."""
        cache = MemoryCache(max_size=5, ttl=3600)
        for i in range(10):
            cache.set(f"key{i}", {"data": i})
        stats = cache.get_stats()
        assert stats["size"] == 5

    def test_lru_order_after_mixed_operations(self):
        """Test LRU order is maintained after mixed get/set operations.
        
        With max_size=4:
        - Initial: [a, b, c, d]
        - get(a): moves a to end -> [b, c, d, a]
        - set(e): "a" exists so move_to_end (no-op), then insert e -> [b, c, d, a, e]
                  Evict oldest (b) -> [c, d, a, e]
        """
        cache = MemoryCache(max_size=4, ttl=3600)
        cache.set("a", {"data": "a"})
        cache.set("b", {"data": "b"})
        cache.set("c", {"data": "c"})
        cache.set("d", {"data": "d"})
        cache.get("a")
        cache.set("e", {"data": "e"})
        assert cache.get("a") is not None
        assert cache.get("b") is None  # evicted during set(e)
        assert cache.get("c") is not None
        assert cache.get("d") is not None
        assert cache.get("e") is not None


class TestCachedResult:
    """Test CachedResult dataclass."""

    def test_cached_result_default_timestamp(self):
        """Test CachedResult has default UTC timestamp."""
        result = CachedResult(data={"key": "value"})
        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)

    def test_cached_result_default_ttl(self):
        """Test CachedResult has default TTL of 3600."""
        result = CachedResult(data={"key": "value"})
        assert result.ttl == 3600

    def test_cached_result_is_expired_with_seconds(self):
        """Test is_expired with float timestamp."""
        result = CachedResult(
            data={"key": "value"},
            timestamp=time.time() - 100,
            ttl=10,
        )
        assert result.is_expired() is True

    def test_cached_result_is_expired_with_datetime(self):
        """Test is_expired with datetime timestamp."""
        old_time = datetime.now(timezone.utc).timestamp() - 100
        result = CachedResult(
            data={"key": "value"},
            timestamp=old_time,
            ttl=10,
        )
        assert result.is_expired() is True

    def test_cached_result_not_expired(self):
        """Test is_expired returns False for fresh entry."""
        result = CachedResult(
            data={"key": "value"},
            timestamp=time.time(),
            ttl=3600,
        )
        assert result.is_expired() is False