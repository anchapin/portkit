"""
Simple in-memory cache for validation results.
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class ValidationCache:
    """Simple in-memory cache for validation results."""

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._cache_ttl = 300

    def get(self, key: str) -> Optional[Any]:
        """Get cached result if still valid."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            if datetime.now().timestamp() - timestamp < self._cache_ttl:
                return result
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        """Cache a result."""
        self._cache[key] = (value, datetime.now().timestamp())

    def clear(self):
        """Clear all cached results."""
        self._cache.clear()

    def generate_key(self, addon_path: Path) -> str:
        """Generate cache key from file path and metadata."""
        if not addon_path.exists():
            return f"missing_{addon_path}"

        stat = addon_path.stat()
        key_data = f"{addon_path}_{stat.st_mtime}_{stat.st_size}"
        return hashlib.md5(key_data.encode()).hexdigest()
