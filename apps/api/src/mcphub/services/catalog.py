"""Reading the catalog: tools across servers, and one server's resources, prompts and history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.models import Prompt, Resource, Server, ServerVersion, Tool
from mcphub.repositories.catalog import CatalogRepository, HealthBucket, HistoryRepository


@dataclass(frozen=True, slots=True)
class HealthHistory:
    hours: int
    bucket_minutes: int
    uptime: float | None
    buckets: list[HealthBucket]


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.catalog = CatalogRepository(session)
        self.history = HistoryRepository(session)

    async def search_tools(
        self, *, q: str | None, server: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[Server, Tool]], int]:
        return await self.catalog.search_tools(q=q, server_slug=server, limit=limit, offset=offset)

    async def tools(self, server: Server, *, include_removed: bool) -> list[Tool]:
        return await self.catalog.tools(server.id, include_removed=include_removed)

    async def resources(self, server: Server) -> list[Resource]:
        return await self.catalog.resources(server.id, include_removed=False)

    async def prompts(self, server: Server) -> list[Prompt]:
        return await self.catalog.prompts(server.id, include_removed=False)

    async def versions(
        self, server: Server, *, limit: int, offset: int
    ) -> tuple[list[ServerVersion], int]:
        return await self.history.versions(server.id, limit=limit, offset=offset)

    async def health(self, server: Server, hours: int) -> HealthHistory:
        since = datetime.now(UTC) - timedelta(hours=hours)
        # About 48 points whatever the range: 30-minute buckets for a day.
        bucket_minutes = max(5, hours * 60 // 48)
        buckets = await self.history.health_buckets(server.id, since, bucket_minutes * 60)
        checks = sum(b.checks for b in buckets)
        uptime = sum(b.ok for b in buckets) / checks if checks else None
        return HealthHistory(hours, bucket_minutes, uptime, buckets)
