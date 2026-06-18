"""Shared infrastructure for all scrapers.

Provides:
- Global ThreadPoolExecutor with configurable concurrency cap
- Race-level response cache with TTL
- Centralized HTTP client management
"""
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Global thread pool — shared across ALL scrapers and status_manager
# Cap at 15 concurrent requests to avoid IP throttling
MAX_CONCURRENT_REQUESTS = 15
_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()


def get_pool() -> ThreadPoolExecutor:
    """Get or create the global thread pool."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadPoolExecutor(
                    max_workers=MAX_CONCURRENT_REQUESTS,
                    thread_name_prefix="scraper"
                )
                logger.info(f"Created global thread pool with {MAX_CONCURRENT_REQUESTS} workers")
    return _pool


def shutdown_pool():
    """Shutdown the global thread pool on app exit."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        _pool = None


# Race-level response cache
# Key: (source, meeting_name, race_number) -> {data, timestamp}
_race_cache: Dict[tuple, Dict[str, Any]] = {}
_race_cache_lock = threading.Lock()
RACE_CACHE_TTL = 300  # 5 minutes — race results don't change once Final


def get_race_cache(source: str, meeting_name: str, race_number: int) -> Optional[dict]:
    """Get cached race data if still valid."""
    key = (source, meeting_name.lower().strip(), race_number)
    with _race_cache_lock:
        entry = _race_cache.get(key)
        if entry and time.time() - entry["ts"] < RACE_CACHE_TTL:
            return entry["data"]
    return None


def set_race_cache(source: str, meeting_name: str, race_number: int, data: dict):
    """Cache race data."""
    key = (source, meeting_name.lower().strip(), race_number)
    with _race_cache_lock:
        _race_cache[key] = {"data": data, "ts": time.time()}


def invalidate_race_cache(source: str = None, meeting_name: str = None):
    """Invalidate race cache. If source/meeting_name given, only clear that subset."""
    with _race_cache_lock:
        if source is None and meeting_name is None:
            _race_cache.clear()
        else:
            keys_to_remove = [
                k for k in _race_cache
                if (source is None or k[0] == source) and
                   (meeting_name is None or k[1] == meeting_name.lower().strip())
            ]
            for k in keys_to_remove:
                del _race_cache[k]
