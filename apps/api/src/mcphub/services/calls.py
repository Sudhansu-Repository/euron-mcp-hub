"""Reading the call log: filtered pages, one call in full, and CSV export."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.errors import NotFoundError
from mcphub.core.pagination import Cursor
from mcphub.models import ToolCall
from mcphub.repositories.calls import CallFilters, CallRepository
from mcphub.repositories.clients import ClientRepository
from mcphub.repositories.servers import ServerRepository
from mcphub.repositories.users import UserRepository

EXPORT_LIMIT = 100_000
EXPORT_COLUMNS = (
    "id",
    "created_at",
    "client_name",
    "qualified_name",
    "status",
    "latency_ms",
    "upstream_ms",
    "error_message",
    "arguments",
    "source",
    "request_id",
)


@dataclass(frozen=True, slots=True)
class CallQuery:
    client: str | None = None
    server: str | None = None
    tool: str | None = None
    statuses: tuple[str, ...] = ()
    source: str | None = None
    q: str | None = None
    since: datetime | None = None
    until: datetime | None = None


@dataclass(frozen=True, slots=True)
class CallDetail:
    call: ToolCall
    actor_name: str | None


class CallService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calls = CallRepository(session)

    async def _filters(self, query: CallQuery) -> CallFilters | None:
        """Repository filters; None when a named client or server does not exist."""
        client_id = server_id = None
        if query.client:
            client = await ClientRepository(self.session).by_slug(query.client)
            if client is None:
                return None
            client_id = client.id
        if query.server:
            server = await ServerRepository(self.session).by_slug(query.server)
            if server is None:
                return None
            server_id = server.id
        return CallFilters(
            client_id=client_id,
            server_id=server_id,
            tool=query.tool,
            statuses=query.statuses,
            source=query.source,
            q=query.q,
            since=query.since,
            until=query.until,
        )

    async def page(
        self, query: CallQuery, *, cursor: str | None, limit: int
    ) -> tuple[list[ToolCall], str | None]:
        filters = await self._filters(query)
        if filters is None:
            return [], None
        rows, following = await self.calls.page(
            filters, cursor=Cursor.decode(cursor) if cursor else None, limit=limit
        )
        return rows, following.encode() if following else None

    async def count(self, query: CallQuery) -> int:
        filters = await self._filters(query)
        return 0 if filters is None else await self.calls.count(filters)

    async def get(self, call_id: uuid.UUID) -> CallDetail:
        call = await self.calls.get(call_id)
        if call is None:
            raise NotFoundError("Call not found.")
        actor = None
        if call.actor_user_id:
            user = await UserRepository(self.session).get(call.actor_user_id)
            actor = user.name if user else None
        return CallDetail(call, actor)

    async def export_csv(self, query: CallQuery) -> AsyncIterator[str]:
        """The matching calls as CSV, newest first, streamed in chunks."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        yield buffer.getvalue()
        filters = await self._filters(query)
        if filters is None:
            return
        rows = 0
        async for call in self.calls.stream(filters, EXPORT_LIMIT):
            buffer.seek(0)
            buffer.truncate()
            writer.writerow(
                [
                    call.id,
                    call.created_at.isoformat(),
                    call.client_name,
                    call.qualified_name,
                    call.status,
                    call.latency_ms,
                    call.upstream_ms if call.upstream_ms is not None else "",
                    call.error_message or "",
                    orjson.dumps(call.arguments).decode() if call.arguments is not None else "",
                    call.source,
                    call.request_id or "",
                ]
            )
            rows += 1
            yield buffer.getvalue()
