"""
Redis client for ARIA MVP 2.0.

Provides async Redis helpers for session state storage.
All session keys use a TTL derived from settings.redis_ttl_hours.
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from backend.config import settings

logger = logging.getLogger(__name__)

# Seconds to keep each session alive (default 24 h)
SESSION_TTL: int = settings.redis_ttl_hours * 3600


class RedisClient:
    """Async Redis wrapper for ARIA session storage."""

    def __init__(self, url: str) -> None:
        """Initialise the async Redis connection pool.

        Args:
            url: Redis connection URL, e.g. redis://localhost:6379.
        """
        self._redis: aioredis.Redis = aioredis.from_url(
            url, decode_responses=True
        )

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
        await self._redis.set(key, value, ex=ex or SESSION_TTL)

    async def get(self, key: str) -> str | None:
        """Retrieve a raw string value from Redis.

        Args:
            key: Redis key.

        Returns:
            Stored string, or None if not found.
        """
        return await self._redis.get(key)

    async def delete(self, key: str) -> None:
        """Delete a key from Redis.

        Args:
            key: Redis key to remove.
        """
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in Redis.

        Args:
            key: Redis key to check.

        Returns:
            True if the key exists, False otherwise.
        """
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
        await self._redis.expire(key, ex or SESSION_TTL)

    async def keys(self, pattern: str) -> list[str]:
        """Return all keys matching a pattern.

        Args:
            pattern: Redis glob-style pattern, e.g. 'session:*'.

        Returns:
            List of matching key strings.
        """
        raw_keys = await self._redis.keys(pattern)
        return [k.decode() if isinstance(k, bytes) else k for k in raw_keys]

    async def ping(self) -> bool:
        """Ping the Redis server."""
        return await self._redis.ping()


redis_client = RedisClient(settings.redis_url)

