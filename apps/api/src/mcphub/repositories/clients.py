from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update

from mcphub.models import Client, ClientKey, PolicyRule, ToolCall
from mcphub.repositories.base import Repository, like_pattern


@dataclass(frozen=True, slots=True)
class ClientSummary:
    client: Client
    active_keys: int
    rules: int
    calls_24h: int


class ClientRepository(Repository):
    async def get(self, client_id: uuid.UUID) -> Client | None:
        return await self.session.get(Client, client_id)

    async def by_slug(self, slug: str) -> Client | None:
        result = await self.session.execute(select(Client).where(Client.slug == slug))
        return result.scalar_one_or_none()

    async def slug_taken(self, slug: str) -> bool:
        return bool(await self.session.scalar(select(func.count()).where(Client.slug == slug)))

    async def add(self, client: Client) -> Client:
        self.session.add(client)
        await self.session.flush()
        return client

    async def page(
        self,
        *,
        q: str | None,
        status: str | None,
        since: datetime,
        limit: int,
        offset: int,
        only: uuid.UUID | None = None,
    ) -> tuple[list[ClientSummary], int]:
        keys = (
            select(func.count())
            .where(ClientKey.client_id == Client.id, ClientKey.revoked_at.is_(None))
            .correlate(Client)
            .scalar_subquery()
        )
        rules = (
            select(func.count())
            .where(PolicyRule.client_id == Client.id)
            .correlate(Client)
            .scalar_subquery()
        )
        calls = (
            select(func.count())
            .where(ToolCall.client_id == Client.id, ToolCall.created_at >= since)
            .correlate(Client)
            .scalar_subquery()
        )
        query = select(Client)
        if only is not None:
            query = query.where(Client.id == only)
        if q:
            pattern = like_pattern(q.strip())
            query = query.where(
                or_(
                    Client.name.ilike(pattern),
                    Client.slug.ilike(pattern),
                    Client.description.ilike(pattern),
                )
            )
        if status:
            query = query.where(Client.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        result = await self.session.execute(
            query.add_columns(keys, rules, calls)
            .order_by(Client.name, Client.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            ClientSummary(client, int(k), int(r), int(c)) for client, k, r, c in result.all()
        ], total

    async def count_active(self) -> int:
        return int(
            await self.session.scalar(select(func.count()).where(Client.status == "active")) or 0
        )

    async def bump_policy_version(self, client_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Client)
            .where(Client.id == client_id)
            .values(policy_version=Client.policy_version + 1)
        )

    async def touch(self, client_ids: list[uuid.UUID], at: datetime) -> None:
        if client_ids:
            await self.session.execute(
                update(Client).where(Client.id.in_(client_ids)).values(last_seen_at=at)
            )


class KeyRepository(Repository):
    async def page(
        self, *, state: str | None, q: str | None, now: datetime, limit: int, offset: int
    ) -> tuple[list[tuple[ClientKey, Client]], int]:
        """Keys of every client, newest first, optionally only active, revoked or expired ones."""
        query = select(ClientKey, Client).join(Client, Client.id == ClientKey.client_id)
        live = ClientKey.revoked_at.is_(None) & or_(
            ClientKey.expires_at.is_(None), ClientKey.expires_at > now
        )
        if state == "active":
            query = query.where(live)
        elif state == "revoked":
            query = query.where(ClientKey.revoked_at.is_not(None))
        elif state == "expired":
            query = query.where(ClientKey.revoked_at.is_(None), ClientKey.expires_at <= now)
        if q:
            pattern = like_pattern(q)
            query = query.where(
                or_(
                    ClientKey.name.ilike(pattern),
                    Client.name.ilike(pattern),
                    Client.slug.ilike(pattern),
                )
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        result = await self.session.execute(
            query.order_by(ClientKey.created_at.desc(), ClientKey.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in result.all()], int(total or 0)

    async def by_prefix(self, prefix: str) -> tuple[ClientKey, Client] | None:
        result = await self.session.execute(
            select(ClientKey, Client)
            .join(Client, Client.id == ClientKey.client_id)
            .where(ClientKey.prefix == prefix)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def for_client(self, client_id: uuid.UUID) -> list[ClientKey]:
        result = await self.session.execute(
            select(ClientKey)
            .where(ClientKey.client_id == client_id)
            .order_by(ClientKey.created_at.desc())
        )
        return list(result.scalars())

    async def get(self, client_id: uuid.UUID, key_id: uuid.UUID) -> ClientKey | None:
        result = await self.session.execute(
            select(ClientKey).where(ClientKey.id == key_id, ClientKey.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def add(self, key: ClientKey) -> ClientKey:
        self.session.add(key)
        await self.session.flush()
        return key

    async def touch(self, key_ids: list[uuid.UUID], at: datetime) -> None:
        if key_ids:
            await self.session.execute(
                update(ClientKey).where(ClientKey.id.in_(key_ids)).values(last_used_at=at)
            )

    async def prefixes(self, client_id: uuid.UUID) -> list[str]:
        result = await self.session.execute(
            select(ClientKey.prefix).where(ClientKey.client_id == client_id)
        )
        return list(result.scalars())


class RuleRepository(Repository):
    async def for_client(self, client_id: uuid.UUID) -> list[PolicyRule]:
        result = await self.session.execute(
            select(PolicyRule).where(PolicyRule.client_id == client_id).order_by(PolicyRule.pattern)
        )
        return list(result.scalars())

    async def get(self, client_id: uuid.UUID, rule_id: uuid.UUID) -> PolicyRule | None:
        result = await self.session.execute(
            select(PolicyRule).where(PolicyRule.id == rule_id, PolicyRule.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def find(self, client_id: uuid.UUID, pattern: str) -> PolicyRule | None:
        result = await self.session.execute(
            select(PolicyRule).where(
                PolicyRule.client_id == client_id, PolicyRule.pattern == pattern
            )
        )
        return result.scalar_one_or_none()

    async def add(self, rule: PolicyRule) -> PolicyRule:
        self.session.add(rule)
        await self.session.flush()
        return rule
