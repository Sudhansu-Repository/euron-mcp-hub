"""Usage over a time range: totals, series by status, latency, top tools and clients.

The overview is the dashboard's landing page and every viewer polls it, so the computed
document is cached in Valkey for 30 seconds per range: Postgres aggregates the call log
at most twice a minute, however many people are watching.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.models.enums import CallStatus, Health
from mcphub.repositories.calls import CallRepository
from mcphub.repositories.catalog import CatalogRepository
from mcphub.repositories.clients import ClientRepository
from mcphub.repositories.servers import ServerRepository
from mcphub.services.cache import STATS_TTL_S
from mcphub.services.container import Container

Range = Literal["24h", "7d", "30d"]
RANGES: dict[str, tuple[timedelta, int]] = {
    "24h": (timedelta(hours=24), 3600),
    "7d": (timedelta(days=7), 6 * 3600),
    "30d": (timedelta(days=30), 24 * 3600),
}
STATUSES = [status.value for status in CallStatus]


@dataclass(frozen=True, slots=True)
class Overview:
    range: str
    generated_at: str
    bucket_seconds: int
    totals: dict[str, Any]
    servers: dict[str, int]
    series: list[dict[str, Any]]
    latency: list[dict[str, Any]]
    statuses: dict[str, int]
    top_tools: list[dict[str, Any]]
    top_clients: list[dict[str, Any]]


def _buckets(since: datetime, now: datetime, size: int) -> list[datetime]:
    start = datetime.fromtimestamp(since.timestamp() // size * size, UTC)
    points = []
    while start <= now:
        points.append(start)
        start += timedelta(seconds=size)
    return points


class StatsService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session

    async def overview(self, range_: Range) -> dict[str, Any]:
        key = f"mcphub:stats:{range_}"
        cached = await self.c.cache.get(key)
        if cached is not None:
            return dict(cached)
        document = asdict(await self._compute(range_))
        await self.c.cache.put(key, document, STATS_TTL_S)
        return document

    async def _compute(self, range_: Range) -> Overview:
        span, bucket_s = RANGES[range_]
        now = datetime.now(UTC)
        since = now - span
        calls = CallRepository(self.session)
        totals = await calls.totals(since)
        series = await calls.series(since, bucket_s)
        latency = await calls.latency_series(since, bucket_s)
        statuses = await calls.status_counts(since)
        top_tools = await calls.top_tools(since, 8)
        top_clients = await calls.top_clients(since, 8)
        health = await ServerRepository(self.session).health_counts()
        total_servers, enabled_servers = await ServerRepository(self.session).counts()
        exposed = await CatalogRepository(self.session).count_gateway_tools()
        active_clients = await ClientRepository(self.session).count_active()

        # Every bucket appears, with zeros, so charts keep their time axis honest.
        by_bucket: dict[datetime, dict[str, int]] = {
            start: dict.fromkeys(STATUSES, 0) for start in _buckets(since, now, bucket_s)
        }
        for point in series:
            by_bucket.setdefault(point.start, dict.fromkeys(STATUSES, 0))[point.status] = (
                point.calls
            )
        latencies = {point.start: point for point in latency}
        forwarded = totals.ok + totals.failed
        servers = {"total": total_servers, "enabled": enabled_servers}
        for state in Health:
            servers[state.value] = health.get(state.value, 0)
        return Overview(
            range=range_,
            generated_at=now.isoformat(),
            bucket_seconds=bucket_s,
            totals={
                "calls": totals.calls,
                "ok": totals.ok,
                "failed": totals.failed,
                "refused": totals.refused,
                "success_rate": round(totals.ok / forwarded, 4) if forwarded else None,
                "p50_ms": totals.p50_ms,
                "p95_ms": totals.p95_ms,
                "clients_seen": totals.clients,
                "tools_used": totals.tools,
                "active_clients": active_clients,
                "exposed_tools": exposed,
            },
            servers=servers,
            series=[
                {"start": start.isoformat(), **counts}
                for start, counts in sorted(by_bucket.items())
            ],
            latency=[
                {
                    "start": start.isoformat(),
                    "p50_ms": latencies[start].p50_ms if start in latencies else None,
                    "p95_ms": latencies[start].p95_ms if start in latencies else None,
                }
                for start in sorted(by_bucket)
            ],
            statuses={status: statuses.get(status, 0) for status in STATUSES},
            top_tools=[asdict(item) for item in top_tools],
            top_clients=[asdict(item) for item in top_clients],
        )
