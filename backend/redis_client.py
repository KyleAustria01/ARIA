"""
Redis client for ARIA MVP 2.0.

Provides async Redis helpers for session state storage.
All session keys use a TTL derived from settings.redis_ttl_hours.
Falls back to file-based storage if Redis is unavailable (development mode).
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis

from backend.config import settings

logger = logging.getLogger(__name__)

# Seconds to keep each session alive (default 24 h)
SESSION_TTL: int = settings.redis_ttl_hours * 3600

# File path for development fallback
_FALLBACK_FILE = Path(__file__).parent.parent / ".dev_sessions.json"


class FileBasedStore:
    """File-based key-value store with TTL support (development fallback).
    
    Persists data to a JSON file so sessions survive server restarts.
    """

    def __init__(self, filepath: Path) -> None:
        """Initialize the file-based store."""
        self._filepath = filepath
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._load()

    def _load(self) -> None:
        """Load data from file if it exists."""
        if self._filepath.exists():
            try:
                with open(self._filepath, "r") as f:
                    raw = json.load(f)
                # Convert to internal format with TTL
                for key, item in raw.items():
                    if isinstance(item, dict) and "_value" in item:
                        self._data[key] = (item["_value"], item.get("_expiry"))
                    else:
                        # Legacy format: just the value
                        self._data[key] = (item, None)
            except Exception as e:
                logger.warning("Failed to load fallback store: %s", e)
                self._data = {}

    def _save(self) -> None:
        """Save data to file."""
        try:
            raw = {}
            for key, (value, expiry) in self._data.items():
                raw[key] = {"_value": value, "_expiry": expiry}
            with open(self._filepath, "w") as f:
                json.dump(raw, f)
        except Exception as e:
            logger.warning("Failed to save fallback store: %s", e)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """Store a value with optional expiry."""
        expiry = None if ex is None else time.time() + ex
        self._data[key] = (value, expiry)
        self._save()

    async def get(self, key: str) -> str | None:
        """Retrieve a value if it exists and hasn't expired."""
        if key not in self._data:
            return None
        value, expiry = self._data[key]
        if expiry is not None and time.time() > expiry:
            del self._data[key]
            self._save()
            return None
        return value

    async def delete(self, key: str) -> None:
        """Delete a key."""
        if key in self._data:
            del self._data[key]
            self._save()

    async def exists(self, key: str) -> bool:
        """Check if key exists and hasn't expired."""
        if key not in self._data:
            return False
        value, expiry = self._data[key]
        if expiry is not None and time.time() > expiry:
            del self._data[key]
            self._save()
            return False
        return True

    async def expire(self, key: str, seconds: int) -> None:
        """Set expiry on a key."""
        if key in self._data:
            value, _ = self._data[key]
            self._data[key] = (value, time.time() + seconds)
            self._save()

    async def keys(self, pattern: str) -> list[str]:
        """Return keys matching a glob pattern."""
        import fnmatch
        return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]

    async def ping(self) -> bool:
        """Health check."""
        return True


# Keep the old InMemoryStore for backwards compatibility
InMemoryStore = FileBasedStore


class RedisClient:
    """Async Redis wrapper for ARIA session storage."""

    def __init__(self, url: str) -> None:
        """Initialise the async Redis connection pool.

        Args:
            url: Redis connection URL, e.g. redis://localhost:6379.
        """
        self._redis: aioredis.Redis | None = None
        self._fallback: FileBasedStore | None = None
        self._url = url
        self._use_fallback = False

        try:
            self._redis = aioredis.from_url(
                url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3
            )
        except Exception as e:
            logger.warning(
                "Redis connection failed during init (%s). Using file-based fallback.",
                e,
            )
            self._fallback = FileBasedStore(_FALLBACK_FILE)
            self._use_fallback = True

    async def _ensure_redis_available(self) -> None:
        """Check if Redis is available; switch to fallback if not."""
        if self._use_fallback or self._redis is None:
            return
        
        try:
            await self._redis.ping()
        except Exception as e:
            logger.warning(
                "Redis connection lost (%s). Switching to file-based fallback.",
                e,
            )
            self._fallback = FileBasedStore(_FALLBACK_FILE)
            self._use_fallback = True

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """Store a raw string value in Redis.

        Args:
            key: Redis key.
            value: String value to store.
            ex: Optional expiry in seconds. Defaults to SESSION_TTL.
        """
        await self._ensure_redis_available()
        if self._use_fallback:
            await self._fallback.set(key, value, ex=ex or SESSION_TTL)
        else:
            await self._redis.set(key, value, ex=ex or SESSION_TTL)

    async def get(self, key: str) -> str | None:
        """Retrieve a raw string value from Redis.

        Args:
            key: Redis key.

        Returns:
            Stored string, or None if not found.
        """
        await self._ensure_redis_available()
        if self._use_fallback:
            return await self._fallback.get(key)
        else:
            return await self._redis.get(key)

    async def delete(self, key: str) -> None:
        """Delete a key from Redis.

        Args:
            key: Redis key to remove.
        """
        await self._ensure_redis_available()
        if self._use_fallback:
            await self._fallback.delete(key)
        else:
            await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in Redis.

        Args:
            key: Redis key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        await self._ensure_redis_available()
        if self._use_fallback:
            return await self._fallback.exists(key)
        else:
            return bool(await self._redis.exists(key))

    # ------------------------------------------------------------------
    # JSON session helpers
    # ------------------------------------------------------------------

    async def set_json(self, key: str, data: Any, ex: int | None = None) -> None:
        """Serialise data as JSON and store it in Redis.

        Args:
            key: Redis key.
            data: JSON-serialisable object.
            ex: Optional expiry in seconds. Defaults to SESSION_TTL.
        """
        await self.set(key, json.dumps(data), ex=ex)

    async def get_json(self, key: str) -> Any | None:
        """Retrieve and deserialise a JSON value from Redis.

        Args:
            key: Redis key.

        Returns:
            Deserialised Python object, or None if the key does not exist.
        """
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON from Redis key: %s", key)
            return None

    async def refresh(self, key: str, ex: int | None = None) -> None:
        """Reset the TTL on an existing key.

        Args:
            key: Redis key to refresh.
            ex: New expiry in seconds. Defaults to SESSION_TTL.
        """
        await self._ensure_redis_available()
        if self._use_fallback:
            await self._fallback.expire(key, ex or SESSION_TTL)
        else:
            await self._redis.expire(key, ex or SESSION_TTL)

    async def keys(self, pattern: str) -> list[str]:
        """Return all keys matching a pattern.

        Args:
            pattern: Redis glob-style pattern, e.g. 'session:*'.

        Returns:
            List of matching key strings.
        """
        await self._ensure_redis_available()
        if self._use_fallback:
            return await self._fallback.keys(pattern)
        else:
            raw_keys = await self._redis.keys(pattern)
            return [k.decode() if isinstance(k, bytes) else k for k in raw_keys]

    async def ping(self) -> bool:
        """Ping the Redis server."""
        await self._ensure_redis_available()
        if self._use_fallback:
            return await self._fallback.ping()
        else:
            return await self._redis.ping()


redis_client = RedisClient(settings.redis_url)

