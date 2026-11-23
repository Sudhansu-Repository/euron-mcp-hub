from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Integer, cast, delete, func, or_, select

from mcphub.models import HealthCheck, Prompt, Resource, Server, ServerVersion, Tool
from mcphub.repositories.base import Repository, like_pattern


@dataclass(frozen=True, slots=True)
class HealthBucket:
    start: datetime
    checks: int
    ok: int
    avg_latency_ms: int | None


class CatalogRepository(Repository):
    """Discovered tools, resources and prompts."""

    async def tools(self, server_id: uuid.UUID, *, include_removed: bool) -> list[Tool]:
        query = select(Tool).where(Tool.server_id == server_id)
        if not include_removed:
            query = query.where(Tool.removed_at.is_(None))
        result = await self.session.execute(query.order_by(Tool.name))
        return list(result.scalars())

    async def tool(self, server_id: uuid.UUID, name: str) -> Tool | None:
        result = await self.session.execute(
            select(Tool).where(Tool.server_id == server_id, Tool.name == name)
        )
        return result.scalar_one_or_none()

    async def resources(self, server_id: uuid.UUID, *, include_removed: bool) -> list[Resource]:
        query = select(Resource).where(Resource.server_id == server_id)
        if not include_removed:
            query = query.where(Resource.removed_at.is_(None))
        result = await self.session.execute(query.order_by(Resource.is_template, Resource.uri))
        return list(result.scalars())

    async def prompts(self, server_id: uuid.UUID, *, include_removed: bool) -> list[Prompt]:
        query = select(Prompt).where(Prompt.server_id == server_id)
        if not include_removed:
            query = query.where(Prompt.removed_at.is_(None))
        result = await self.session.execute(query.order_by(Prompt.name))
        return list(result.scalars())

    async def gateway_tools(self) -> list[tuple[Server, Tool]]:
        """Every tool the gateway can expose: present, enabled, on an enabled server."""
        result = await self.session.execute(
            select(Server, Tool)
            .join(Tool, Tool.server_id == Server.id)
            .where(Server.enabled.is_(True), Tool.enabled.is_(True), Tool.removed_at.is_(None))
            .order_by(Server.slug, Tool.name)
        )
        return [(server, tool) for server, tool in result.all()]

    async def search_tools(
        self, *, q: str | None, server_slug: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[Server, Tool]], int]:
        query = (
            select(Server, Tool)
            .join(Tool, Tool.server_id == Server.id)
            .where(Tool.removed_at.is_(None))
        )
        if q:
            pattern = like_pattern(q.strip())
            query = query.where(
                or_(
                    Tool.name.ilike(pattern),
                    Tool.title.ilike(pattern),
                    Tool.description.ilike(pattern),
                    Server.slug.ilike(pattern),
                )
            )
        if server_slug:
            query = query.where(Server.slug == server_slug)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        result = await self.session.execute(
            query.order_by(Server.slug, Tool.name).limit(limit).offset(offset)
        )
        return [(server, tool) for server, tool in result.all()], total

    async def count_gateway_tools(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Tool)
                .join(Server, Server.id == Tool.server_id)
                .where(Server.enabled.is_(True), Tool.enabled.is_(True), Tool.removed_at.is_(None))
            )
            or 0
        )


class HistoryRepository(Repository):
    """Server versions and health checks."""

    async def add_version(self, version: ServerVersion) -> None:
        self.session.add(version)

    async def versions(
        self, server_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ServerVersion], int]:
        total = int(
            await self.session.scalar(
                select(func.count()).where(ServerVersion.server_id == server_id)
            )
            or 0
        )
        result = await self.session.execute(
            select(ServerVersion)
            .where(ServerVersion.server_id == server_id)
            .order_by(ServerVersion.created_at.desc(), ServerVersion.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total

    async def add_check(self, check: HealthCheck) -> None:
        self.session.add(check)

    async def health_buckets(
        self, server_id: uuid.UUID, since: datetime, bucket_s: int
    ) -> list[HealthBucket]:
        epoch = func.extract("epoch", HealthCheck.checked_at)
        bucket = func.to_timestamp(func.floor(epoch / bucket_s) * bucket_s).label("bucket")
        result = await self.session.execute(
            select(
                bucket,
                func.count(),
                func.count().filter(HealthCheck.ok.is_(True)),
                cast(func.avg(HealthCheck.latency_ms), Integer),
            )
            .where(HealthCheck.server_id == server_id, HealthCheck.checked_at >= since)
            .group_by(bucket)
            .order_by(bucket)
        )
        return [
            HealthBucket(start, int(checks), int(ok), avg if avg is None else int(avg))
            for start, checks, ok, avg in result.all()
        ]

    async def uptime(self, server_ids: list[uuid.UUID], since: datetime) -> dict[uuid.UUID, float]:
        if not server_ids:
            return {}
        result = await self.session.execute(
            select(
                HealthCheck.server_id,
                func.count(),
                func.count().filter(HealthCheck.ok.is_(True)),
            )
            .where(HealthCheck.server_id.in_(server_ids), HealthCheck.checked_at >= since)
            .group_by(HealthCheck.server_id)
        )
        return {sid: (ok / total if total else 0.0) for sid, total, ok in result.all()}

    async def purge_checks(self, before: datetime, batch: int) -> int:
        doomed = (
            select(HealthCheck.id)
            .where(HealthCheck.checked_at < before)
            .limit(batch)
            .scalar_subquery()
        )
        result = await self.session.execute(delete(HealthCheck).where(HealthCheck.id.in_(doomed)))
        return int(getattr(result, "rowcount", 0) or 0)
