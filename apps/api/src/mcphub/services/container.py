"""Process-wide infrastructure, built once at startup and shared by every request.

Services are cheap objects created per request around one database session; everything
expensive (connection pools, upstream MCP sessions, the call log writer) lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from mcphub.core.config import Settings
from mcphub.core.ratelimit import RateLimiter
from mcphub.db.session import Database
from mcphub.integrations.vault import Vaults
from mcphub.services.cache import HubCache
from mcphub.services.call_log import CallLogWriter
from mcphub.upstream.pool import UpstreamPool


@dataclass
class Container:
    settings: Settings
    db: Database
    redis: Redis
    cache: HubCache
    limiter: RateLimiter
    vaults: Vaults
    pool: UpstreamPool
    call_log: CallLogWriter

    def start(self) -> None:
        """Start the background tasks (the pool reaper, the call log writer)."""
        self.pool.start()
        self.call_log.start()

    async def close(self) -> None:
        # Drain the call log first: it needs the database, and calls finishing during
        # shutdown still belong in it.
        await self.call_log.close()
        await self.pool.close()
        await self.redis.aclose()
        await self.db.dispose()


def build_container(settings: Settings) -> Container:
    redis = Redis.from_url(
        settings.redis_url, decode_responses=False, health_check_interval=30, socket_timeout=5
    )
    db = Database(settings)
    return Container(
        settings=settings,
        db=db,
        redis=redis,
        cache=HubCache(redis),
        limiter=RateLimiter(redis),
        vaults=Vaults(settings),
        pool=UpstreamPool(
            connect_timeout_s=settings.upstream_connect_timeout_s,
            idle_timeout_s=settings.upstream_idle_timeout_s,
            max_result_bytes=settings.upstream_max_result_bytes,
        ),
        call_log=CallLogWriter(
            db,
            flush_interval_s=settings.audit_flush_interval_ms / 1000,
            batch_size=settings.audit_batch_size,
            queue_size=settings.audit_queue_size,
        ),
    )
