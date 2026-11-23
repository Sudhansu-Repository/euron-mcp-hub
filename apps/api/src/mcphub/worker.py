"""The scheduler worker: health checks, scheduled discovery and retention.

    python -m mcphub.worker

- One worker at a time leads, through a lease in Valkey renewed every round; others wait
  as hot standbys and take over within half a minute if the leader dies.
- Each round (every 5 seconds) checks the servers whose last check is older than
  HEALTH_INTERVAL_S and rediscovers those whose refresh interval has passed, a few at a
  time. A server that comes back after being down is rediscovered at once.
- Once an hour it deletes call log rows past AUDIT_RETENTION_DAYS and old health checks.
- SIGTERM finishes the current round, releases the lease and exits.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from prometheus_client import start_http_server
from redis.exceptions import RedisError

from mcphub.core.config import get_settings
from mcphub.core.logging import configure_logging, get_logger
from mcphub.db.migrate import migrate
from mcphub.models.enums import Health
from mcphub.repositories.servers import ServerRepository
from mcphub.services import retention
from mcphub.services.container import Container, build_container
from mcphub.services.discovery import DiscoveryService

log = get_logger("mcphub.worker")

LEASE_KEY = "mcphub:lease:scheduler"
LEASE_TTL_S = 30
ROUND_S = 5.0
CHECK_CONCURRENCY = 8
DISCOVERY_CONCURRENCY = 4
RETENTION_EVERY = timedelta(hours=1)

# Renew only our own lease, atomically.
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class Scheduler:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.discovery = DiscoveryService(container)
        self.identity = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.stopping = asyncio.Event()
        self.leading = False
        self.last_retention: datetime | None = None

    def stop(self) -> None:
        if not self.stopping.is_set():
            log.info("worker_stopping")
            self.stopping.set()

    async def run(self) -> None:
        while not self.stopping.is_set():
            try:
                if await self._lead():
                    await self.round()
            except Exception:
                log.exception("scheduler_round_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=ROUND_S)
        await self._release()

    async def _lead(self) -> bool:
        redis = self.c.redis
        try:
            if await redis.set(LEASE_KEY, self.identity, nx=True, ex=LEASE_TTL_S):
                acquired = True
            else:
                renewed = await redis.eval(_RENEW, 1, LEASE_KEY, self.identity, str(LEASE_TTL_S))
                acquired = bool(renewed)
        except RedisError:
            log.warning("lease_unavailable")
            acquired = False
        if acquired != self.leading:
            log.info("scheduler_leadership", leading=acquired, worker=self.identity)
            self.leading = acquired
        return acquired

    async def _release(self) -> None:
        with contextlib.suppress(RedisError):
            await self.c.redis.eval(_RELEASE, 1, LEASE_KEY, self.identity)

    async def round(self, now: datetime | None = None) -> None:
        """One scheduling round. Public so tests can drive the scheduler step by step."""
        now = now or datetime.now(UTC)
        interval = timedelta(seconds=self.c.settings.health_interval_s)
        async with self.c.db.session() as session:
            servers = ServerRepository(session)
            due_checks = await servers.due_for_check(now - interval, limit=50)
            due_discovery = [
                s for s in await servers.due_for_discovery(now, limit=20) if s.health != Health.DOWN
            ]
        recovered = await self._bounded([self._check(s.id) for s in due_checks], CHECK_CONCURRENCY)
        rediscover = {s.id for s in due_discovery} | {sid for sid in recovered if sid is not None}
        await self._bounded(
            [self.discovery.discover(server_id) for server_id in rediscover],
            DISCOVERY_CONCURRENCY,
        )
        if self.last_retention is None or now - self.last_retention >= RETENTION_EVERY:
            await retention.purge(self.c, now)
            self.last_retention = now

    async def _check(self, server_id: uuid.UUID) -> uuid.UUID | None:
        """Check one server; its id when it just came back and needs rediscovery."""
        outcome = await self.discovery.check(server_id)
        return server_id if outcome.recovered else None

    @staticmethod
    async def _bounded[T](jobs: list[Coroutine[Any, Any, T]], limit: int) -> list[T | None]:
        semaphore = asyncio.Semaphore(limit)

        async def guarded(job: Coroutine[Any, Any, T]) -> T | None:
            async with semaphore:
                try:
                    return await job
                except Exception:
                    log.exception("scheduled_job_failed")
                    return None

        return list(await asyncio.gather(*(guarded(job) for job in jobs)))


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.migrate_on_boot:
        await migrate(settings)
    container = build_container(settings)
    if port := int(os.environ.get("WORKER_METRICS_PORT", "0")):
        start_http_server(port)
    scheduler = Scheduler(container)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, scheduler.stop)
    log.info(
        "worker_started", worker=scheduler.identity, health_interval_s=settings.health_interval_s
    )
    try:
        await scheduler.run()
    finally:
        await container.close()
        log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
