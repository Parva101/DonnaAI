"""Redis connection pool.

Usage:
    from app.core.redis import get_redis

    async def my_endpoint(redis = Depends(get_redis)):
        await redis.set("key", "value")
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings

_redis: Redis | None = None


async def init_redis() -> Redis:
    """Create and verify the Redis connection pool (called at app startup)."""
    global _redis
    _redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    await _redis.ping()
    return _redis


async def close_redis() -> None:
    """Gracefully close the Redis pool (called at app shutdown)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def get_redis() -> Redis:
    """FastAPI dependency — returns the shared Redis client."""
    if _redis is None:
        raise RuntimeError("Redis not initialised. Call init_redis() first.")
    return _redis
