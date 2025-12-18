"""
Hybrid caching module: Redis + in-memory fallback.

Provides distributed caching with Redis (for production) and graceful fallback
to in-memory caching if Redis is unavailable. Reduces API calls and LLM processing.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional

# Try to import Redis; gracefully degrade if unavailable
try:
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


# ===== REDIS CONNECTION =====

redis_client = None

if REDIS_AVAILABLE:
    try:
        redis_client = Redis(
            host="localhost",
            port=6379,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        # Test connection
        redis_client.ping()
        print("✓ Redis cache connected (distributed mode)")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")
        print("   Falling back to in-memory cache.")
        redis_client = None
else:
    print("⚠️  Redis not installed. Using in-memory cache only.")


# ===== IN-MEMORY CACHE (FALLBACK) =====

class CacheEntry:
    """Represents a cached item with TTL support."""

    def __init__(self, value: Any, ttl_seconds: int = 3600):
        self.value = value
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds

    def __repr__(self) -> str:
        age = int(time.time() - self.created_at)
        return f"<CacheEntry age={age}s ttl={self.ttl_seconds}s>"


class InMemoryCache:
    """Fallback in-memory cache (LRU with TTL)."""

    def __init__(self, max_entries: int = 100):
        self._cache: Dict[str, CacheEntry] = {}
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Retrieve from in-memory cache."""
        entry = self._cache.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.is_expired():
            del self._cache[key]
            self.misses += 1
            return None
        self.hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store in in-memory cache."""
        if len(self._cache) >= self.max_entries:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at,
            )
            del self._cache[oldest_key]
        self._cache[key] = CacheEntry(value, ttl_seconds)

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()
        self.hits = 0
        self.misses = 0

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "mode": "in-memory",
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
        }


# Global in-memory fallback instance
_memory_cache = InMemoryCache(max_entries=100)


# ===== KEY GENERATION =====

def _make_key(prefix: str, *parts: Any) -> str:
    """Generate cache key (hash-based for length limit)."""
    combined = "||".join(str(p) for p in parts)
    h = hashlib.sha256(combined.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


# ===== REDIS + FALLBACK FUNCTIONS =====

def get_cached_raw(
    job_id: str,
    max_studies: int,
) -> Optional[List[Dict]]:
    """Fetch cached raw study results (tries Redis first, then memory)."""
    key = _make_key(job_id, "raw", max_studies)

    # Try Redis first
    if redis_client:
        try:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"⚠️  Redis get error: {e}")

    # Fallback to in-memory
    cached = _memory_cache.get(key)
    return cached if isinstance(cached, list) else None


def set_cached_raw(
    job_id: str,
    max_studies: int,
    data: List[Dict],
    ttl: int = 600
) -> str:
    """Cache raw study results (Redis + in-memory)."""
    key = _make_key(job_id, "raw", max_studies)

    # Try Redis first
    if redis_client:
        try:
            redis_client.set(key, json.dumps(data), ex=ttl)
            return key
        except Exception as e:
            print(f"⚠️  Redis set error: {e}")

    # Fallback to in-memory
    _memory_cache.set(key, data, ttl_seconds=ttl)
    return key


def get_cached_summary(
    job_id: str
) -> Optional[str]:
    """Fetch cached final summary markdown (tries Redis first, then memory)."""
    key = _make_key(job_id, "final_summary")
    # Try Redis first
    if redis_client:
        try:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"⚠️  Redis get error: {e}")

    # Fallback to in-memory
    cached = _memory_cache.get(key)
    return cached if isinstance(cached, (str, List)) else None


def set_cached_summary(
    job_id: str,
    summary: str,
    ttl: int = 1800,
) -> bool:
    """Cache final summary markdown (Redis + in-memory)."""
    key = _make_key(job_id, "final_summary")

    # Try Redis first
    if redis_client:
        try:
            redis_client.set(key, summary, ex=ttl)
            return True
        except Exception as e:
            print(f"⚠️  Redis set error: {e}")

    # Fallback to in-memory
    _memory_cache.set(key, summary, ttl_seconds=ttl)
    return True


def set_cached_chunk_summary(
    job_id: str,
    chunk_index: int,
    chunk_summary: str,
    ttl: int = 1800
) -> bool:
    """Cache chunk summary markdown (Redis + in-memory)."""
    key = _make_key(job_id, "chunk_summary", chunk_index)

    # Try Redis first
    if redis_client:
        try:
            redis_client.set(key, chunk_summary, ex=ttl)
            return True
        except Exception as e:
            print(f"⚠️  Redis set error: {e}")

    # Fallback to in-memory
    _memory_cache.set(key, chunk_summary, ttl_seconds=ttl)
    return True


def get_cached_chunk_summary(
    job_id: str,
    chunk_index
) -> Optional[str]:
    """Fetch cached chunk_summary markdown (tries Redis first, then memory)."""
    key = _make_key(job_id, "chunk_summary", chunk_index)

    # Try Redis first
    if redis_client:
        try:
            data = redis_client.get(key)
            if data:
                return data
        except Exception as e:
            print(f"⚠️  Redis get error: {e}")

    # Fallback to in-memory
    cached = _memory_cache.get(key)
    return cached if isinstance(cached, (str, List)) else None


def get_all_chunks_summary(job_id: str, pages: int):
    chunks = []
    for i in range(int(pages)):
        chunk = get_cached_chunk_summary(job_id, i)
        print(f"Retrieved chunk {i}: {chunk}")
        if chunk:
            chunks.append(chunk)
    return chunks

# ===== LEGACY COMPATIBILITY FUNCTIONS =====


def get_cached_trials(
    query: str, filters: Optional[Dict[str, str]] = None
) -> Optional[List[Dict[str, Any]]]:
    """Retrieve trials from cache (legacy compatibility)."""
    key = _make_key("trials", query, json.dumps(filters or {}))
    return get_cached_raw(query, 0, [])


def cache_trials(
    query: str,
    trials: List[Dict[str, Any]],
    filters: Optional[Dict[str, str]] = None,
) -> None:
    """Cache trials (legacy compatibility)."""
    set_cached_raw(query, 0, [], trials)


def cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    redis_info = {}
    if redis_client:
        try:
            info = redis_client.info()
            redis_info = {
                "mode": "redis",
                "connected": True,
                "used_memory": info.get("used_memory", 0),
                "total_keys": redis_client.dbsize(),
            }
        except Exception:
            redis_info = {"mode": "redis", "connected": False}

    return {
        "redis": redis_info,
        "memory": _memory_cache.stats(),
    }


def clear_all_caches() -> None:
    """Clear all caches (Redis + in-memory)."""
    if redis_client:
        try:
            redis_client.flushdb()
        except Exception as e:
            print(f"⚠️  Redis flush error: {e}")
    _memory_cache.clear()


# stats for processed job

def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get status of a submitted job.

    Args:
        job_id: job ID returned from submit_summarization_job

    Returns:
        dict with status ("processing", "done", "error") and result

        key = _make_key("job_status", job_id)
    """

    key = _make_key(job_id, "job_status")
    if redis_client:
        data = redis_client.get(key)
        if data:
            return json.loads(data) if data else None

    cached = _memory_cache.get(key)
    return cached if isinstance(cached, dict) else None


def set_job_status(job_id: str, status: str, chunk_completed: int = 0,
                   total_chunks: int = 0, summary: Optional[str] = None, ttl: int = 3600) -> bool:
    """Store jon stats in cache"""
    key = _make_key(job_id, "job_status")
    status_data = {
        "job_id": job_id,
        "status": status,
        "chunk_completed": chunk_completed,
        "total_chunks": total_chunks,
        "summary": summary,
        "updated_at": str(datetime.now(timezone.utc))
    }

    if redis_client:
        redis_client.set(key, json.dumps(status_data), ex=ttl)
        return True

    _memory_cache.set(key, json.dumps(status_data), ttl_seconds=ttl)
    return True


def get_final_summary(job_id: str) -> Optional[str]:
    """ Retrieve final aggregated summary from cache"""
    final_key = _make_key(job_id, "job_status")
    if redis_client:
        data = redis_client.get(final_key)
        return json.loads(data) if data else None
    cached = _memory_cache.get(final_key)
    return cached if isinstance(cached, dict) else None
