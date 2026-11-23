"""Valkey-backed caches for the gateway's hot path, invalidated by generation counters.

Every cached entry records the generations it was built from, read *before* the data:

- key lookups: the keys generation, bumped when any key is revoked or any client is
  suspended or deleted (rare, so one global counter is enough);
- client views: the catalog generation (bumped on any server or tool change) and the
  client's own generation (bumped on any change to its rules or settings).

A reader compares them with the current values and rebuilds on a mismatch. Invalidation
is one INCR with no scans, and it is race-free: an entry built from data read before a
change carries the old generation, so it is never served after the change, even when it
is written to the cache late.

Valkey is a cache, not a source of truth. When it is unreachable, readers fall back to
Postgres and writers log the failure; entries expire on their own (views after two
minutes), which bounds how long a missed invalidation can matter.
"""

from __future__ import annotations

import uuid
from typing import Any

import orjson
from redis.asyncio import Redis
from redis.exceptions import RedisError

from mcphub.core.logging import get_logger

log = get_logger("mcphub.cache")

CATALOG_GENERATION = "mcphub:catalog:gen"
KEYS_GENERATION = "mcphub:keys:gen"
KEY_TTL_S = 300
MISSING_KEY_TTL_S = 30
VIEW_TTL_S = 120
STATS_TTL_S = 30


def client_generation_key(client_id: uuid.UUID | str) -> str:
    return f"mcphub:client:{client_id}:gen"


def api_key_key(prefix: str) -> str:
    return f"mcphub:key:{prefix}"


def view_key(client_id: uuid.UUID | str) -> str:
    return f"mcphub:view:{client_id}"


def _decode(raw: bytes | str | None) -> Any:
    return orjson.loads(raw) if raw else None


class HubCache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def bump_catalog(self) -> None:
        await self._incr(CATALOG_GENERATION)

    async def bump_client(self, client_id: uuid.UUID) -> None:
        await self._incr(client_generation_key(client_id))

    async def bump_keys(self) -> None:
        await self._incr(KEYS_GENERATION)

    async def _incr(self, key: str) -> None:
        for attempt in range(3):
            try:
                await self.redis.incr(key)
                return
            except RedisError:
                if attempt == 2:
                    log.error("cache_invalidation_failed", key=key)

    async def key_lookup(self, prefix: str) -> tuple[Any, int, int]:
        """The cached entry for a key prefix, the catalog and the keys generations."""
        raw_key, raw_catalog, raw_keys = await self.redis.mget(
            [api_key_key(prefix), CATALOG_GENERATION, KEYS_GENERATION]
        )
        return _decode(raw_key), int(raw_catalog or 0), int(raw_keys or 0)

    async def client_state(self, client_id: str) -> tuple[int, Any]:
        """The client's current generation and its cached view, in one round trip."""
        raw_gen, raw_view = await self.redis.mget(
            [client_generation_key(client_id), view_key(client_id)]
        )
        return int(raw_gen or 0), _decode(raw_view)

    async def generations(self, client_id: uuid.UUID) -> tuple[int, int]:
        raw_catalog, raw_client = await self.redis.mget(
            [CATALOG_GENERATION, client_generation_key(client_id)]
        )
        return int(raw_catalog or 0), int(raw_client or 0)

    async def put(self, key: str, value: Any, ttl_s: int) -> None:
        try:
            await self.redis.set(key, orjson.dumps(value), ex=ttl_s)
        except RedisError:
            log.warning("cache_write_failed", key=key.rsplit(":", 1)[0])

    async def get(self, key: str) -> Any:
        try:
            return _decode(await self.redis.get(key))
        except RedisError:
            log.warning("cache_read_failed", key=key.rsplit(":", 1)[0])
            return None
