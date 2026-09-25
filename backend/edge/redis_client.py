"""Redis client singleton for Edge services.

All Edge services share a single redis.asyncio connection pool.
The pool is initialised once at application startup and closed on shutdown.

Channels used:
  - `sensor:{station_id}:{domain}` — per-domain reading pub/sub
  - `alerts:{station_id}` — alert lifecycle pub/sub (alert engine → black-box)
  - Outbound queue: sorted set key `queue:outbound:{station_id}`
  - Dedup cache:   key `dedup:alert:{station_id}:{rule_id}` with TTL
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

_pool: Optional[aioredis.Redis] = None
_mock_mode: bool = False


async def init_redis(url: str) -> aioredis.Redis:
    """Connect to Redis and store the global pool. Call once at startup.
    Falls back to an in-memory fake if Redis is unavailable (dev mode)."""
    global _pool, _mock_mode
    try:
        _pool = aioredis.from_url(
            url,
            encoding="utf-8",
            decode_responses=False,
            socket_keepalive=True,
            health_check_interval=30,
        )
        await _pool.ping()
        log.info("edge.redis.connected", url=url)
    except Exception as exc:
        log.warning(
            "edge.redis.unavailable",
            error=str(exc),
            hint="Using in-memory Redis mock. Queue/dedup/pub-sub won't persist across restarts.",
        )
        # fakeredis provides a real async in-memory Redis implementation
        try:
            import fakeredis.aioredis as fakeredis  # type: ignore
            _pool = fakeredis.FakeRedis(decode_responses=False)
        except ImportError:
            # fakeredis not installed — use a minimal stub
            _pool = _MinimalStub()  # type: ignore
        _mock_mode = True
    return _pool  # type: ignore


class _MinimalStub:
    """Bare-minimum Redis stub so the edge server can start without Redis."""

    async def ping(self): return True
    async def close(self): pass
    async def aclose(self): pass
    async def set(self, *a, **kw): return True
    async def get(self, *a, **kw): return None
    async def delete(self, *a, **kw): return 0
    async def exists(self, *a, **kw): return 0
    async def expire(self, *a, **kw): return False
    async def publish(self, *a, **kw): return 0
    async def zadd(self, *a, **kw): return 0
    async def zrange(self, *a, **kw): return []
    async def zrem(self, *a, **kw): return 0
    async def zcard(self, *a, **kw): return 0
    async def pubsub(self, *a, **kw): return _PubSubStub()

class _PubSubStub:
    async def subscribe(self, *a, **kw): pass
    async def unsubscribe(self, *a, **kw): pass
    async def get_message(self, *a, **kw): return None
    async def close(self): pass


async def close_redis() -> None:
    """Close the Redis connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        log.info("edge.redis.closed")


def get_redis() -> aioredis.Redis:
    """Return the global Redis client (must have called init_redis first)."""
    if _pool is None:
        raise RuntimeError("Redis not initialised — call init_redis() at startup")
    return _pool


# ---------------------------------------------------------------------------
# Channel name helpers
# ---------------------------------------------------------------------------

def sensor_channel(station_id: str, domain: str) -> str:
    return f"sensor:{station_id}:{domain}"


def alerts_channel(station_id: str) -> str:
    return f"alerts:{station_id}"


def queue_key(station_id: str) -> str:
    return f"queue:outbound:{station_id}"


def dedup_key(station_id: str, rule_id: str, sensor_id: str) -> str:
    return f"dedup:alert:{station_id}:{rule_id}:{sensor_id}"
