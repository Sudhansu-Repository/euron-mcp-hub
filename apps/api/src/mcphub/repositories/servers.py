from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select

from mcphub.models import Server, ServerSecret
from mcphub.repositories.base import Repository, like_pattern


@dataclass(frozen=True, slots=True)
class ServerFilters:
    q: str | None = None
    health: str | None = None
    transport: str | None = None
    tag: str | None = None
    enabled: bool | None = None


class ServerRepository(Repository):
    async def get(self, server_id: uuid.UUID) -> Server | None:
        return await self.session.get(Server, server_id)

    async def by_slug(self, slug: str) -> Server | None:
        result = await self.session.execute(select(Server).where(Server.slug == slug))
        return result.scalar_one_or_none()

    async def slug_taken(self, slug: str) -> bool:
        return bool(await self.session.scalar(select(func.count()).where(Server.slug == slug)))

    async def add(self, server: Server) -> Server:
        self.session.add(server)
        await self.session.flush()
        return server

    async def page(
        self, filters: ServerFilters, *, limit: int, offset: int
    ) -> tuple[list[Server], int]:
        query = select(Server)
        if filters.q:
            pattern = like_pattern(filters.q.strip())
            query = query.where(
                or_(
                    Server.name.ilike(pattern),
                    Server.slug.ilike(pattern),
                    Server.description.ilike(pattern),
                    Server.owner.ilike(pattern),
                )
            )
        if filters.health:
            query = query.where(Server.health == filters.health)
        if filters.transport:
            query = query.where(Server.transport == filters.transport)
        if filters.tag:
            query = query.where(Server.tags.contains([filters.tag]))
        if filters.enabled is not None:
            query = query.where(Server.enabled.is_(filters.enabled))
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        result = await self.session.execute(
            query.order_by(Server.name, Server.id).limit(limit).offset(offset)
        )
        return list(result.scalars()), total

    async def due_for_check(self, before: datetime, limit: int) -> list[Server]:
        result = await self.session.execute(
            select(Server)
            .where(
                Server.enabled.is_(True),
                or_(Server.last_check_at.is_(None), Server.last_check_at < before),
            )
            .order_by(Server.last_check_at.asc().nulls_first())
            .limit(limit)
        )
        return list(result.scalars())

    async def due_for_discovery(self, now: datetime, limit: int) -> list[Server]:
        interval = func.make_interval(0, 0, 0, 0, 0, 0, Server.refresh_interval_s)
        result = await self.session.execute(
            select(Server)
            .where(
                Server.enabled.is_(True),
                or_(
                    Server.last_discovered_at.is_(None),
                    Server.last_discovered_at + interval < now,
                ),
            )
            .order_by(Server.last_discovered_at.asc().nulls_first())
            .limit(limit)
        )
        return list(result.scalars())

    async def health_counts(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Server.health, func.count())
            .where(Server.enabled.is_(True))
            .group_by(Server.health)
        )
        return {health: int(count) for health, count in result.all()}

    async def counts(self) -> tuple[int, int]:
        """(all servers, enabled servers)."""
        row = (
            await self.session.execute(
                select(func.count(), func.count().filter(Server.enabled.is_(True)))
            )
        ).one()
        return int(row[0]), int(row[1])

    async def names(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
        if not ids:
            return {}
        result = await self.session.execute(
            select(Server.id, Server.slug, Server.name).where(Server.id.in_(ids))
        )
        return {row.id: (row.slug, row.name) for row in result.all()}


class SecretRepository(Repository):
    async def for_server(self, server_id: uuid.UUID) -> list[ServerSecret]:
        result = await self.session.execute(
            select(ServerSecret)
            .where(ServerSecret.server_id == server_id)
            .order_by(ServerSecret.kind, ServerSecret.name)
        )
        return list(result.scalars())

    async def get(self, server_id: uuid.UUID, secret_id: uuid.UUID) -> ServerSecret | None:
        result = await self.session.execute(
            select(ServerSecret).where(
                ServerSecret.id == secret_id, ServerSecret.server_id == server_id
            )
        )
        return result.scalar_one_or_none()

    async def find(self, server_id: uuid.UUID, kind: str, name: str) -> ServerSecret | None:
        result = await self.session.execute(
            select(ServerSecret).where(
                ServerSecret.server_id == server_id,
                ServerSecret.kind == kind,
                ServerSecret.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, secret: ServerSecret) -> ServerSecret:
        self.session.add(secret)
        await self.session.flush()
        return secret

    async def counts(self, server_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not server_ids:
            return {}
        result = await self.session.execute(
            select(ServerSecret.server_id, func.count())
            .where(ServerSecret.server_id.in_(server_ids))
            .group_by(ServerSecret.server_id)
        )
        return {server_id: int(count) for server_id, count in result.all()}
