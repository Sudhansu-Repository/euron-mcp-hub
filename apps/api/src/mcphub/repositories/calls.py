from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, Select, cast, delete, func, insert, select, tuple_

from mcphub.core.pagination import Cursor
from mcphub.models import ToolCall
from mcphub.models.enums import CallStatus
from mcphub.repositories.base import Repository

_TERM = re.compile(r"[a-z0-9]+")


def search_query(text: str) -> str | None:
    """A prefix tsquery from free text: `ticket print` matches `tickets.create_ticket`, printer."""
    terms = _TERM.findall(text.lower())[:8]
    return " & ".join(f"{term}:*" for term in terms) or None


@dataclass(frozen=True, slots=True)
class CallFilters:
    client_id: uuid.UUID | None = None
    server_id: uuid.UUID | None = None
    tool: str | None = None
    statuses: tuple[str, ...] = ()
    source: str | None = None
    q: str | None = None
    since: datetime | None = None
    until: datetime | None = None

    def apply(self, query: Select[Any]) -> Select[Any]:
        if self.client_id is not None:
            query = query.where(ToolCall.client_id == self.client_id)
        if self.server_id is not None:
            query = query.where(ToolCall.server_id == self.server_id)
        if self.tool:
            query = query.where(ToolCall.qualified_name == self.tool)
        if self.statuses:
            query = query.where(ToolCall.status.in_(self.statuses))
        if self.source:
            query = query.where(ToolCall.source == self.source)
        if self.since is not None:
            query = query.where(ToolCall.created_at >= self.since)
        if self.until is not None:
            query = query.where(ToolCall.created_at < self.until)
        if self.q and (tsquery := search_query(self.q)):
            query = query.where(ToolCall.search.op("@@")(func.to_tsquery("simple", tsquery)))
        return query


@dataclass(frozen=True, slots=True)
class Totals:
    calls: int
    ok: int
    failed: int
    refused: int
    clients: int
    tools: int
    p50_ms: int
    p95_ms: int


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    start: datetime
    status: str
    calls: int


@dataclass(frozen=True, slots=True)
class LatencyPoint:
    start: datetime
    p50_ms: int
    p95_ms: int


@dataclass(frozen=True, slots=True)
class TopItem:
    key: str
    label: str
    calls: int
    failed: int
    refused: int
    p95_ms: int


# Refused by the gateway itself (never forwarded) versus failed upstream.
REFUSALS = (
    CallStatus.DENIED,
    CallStatus.BLOCKED,
    CallStatus.RATE_LIMITED,
    CallStatus.INVALID_ARGUMENTS,
)
FAILURES = (CallStatus.TOOL_ERROR, CallStatus.UPSTREAM_ERROR, CallStatus.TIMEOUT)


class CallRepository(Repository):
    async def insert_many(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            await self.session.execute(insert(ToolCall), list(rows))

    async def get(self, call_id: uuid.UUID) -> ToolCall | None:
        return await self.session.get(ToolCall, call_id)

    async def page(
        self, filters: CallFilters, *, cursor: Cursor | None, limit: int
    ) -> tuple[list[ToolCall], Cursor | None]:
        query = filters.apply(select(ToolCall))
        if cursor is not None:
            query = query.where(
                tuple_(ToolCall.created_at, ToolCall.id) < tuple_(cursor.created_at, cursor.id)
            )
        result = await self.session.execute(
            query.order_by(ToolCall.created_at.desc(), ToolCall.id.desc()).limit(limit + 1)
        )
        rows = list(result.scalars())
        following = None
        if len(rows) > limit:
            rows = rows[:limit]
            following = Cursor(rows[-1].created_at, rows[-1].id)
        return rows, following

    async def count(self, filters: CallFilters) -> int:
        query = filters.apply(select(func.count()).select_from(ToolCall))
        return int(await self.session.scalar(query) or 0)

    async def stream(self, filters: CallFilters, limit: int) -> AsyncIterator[ToolCall]:
        query = (
            filters.apply(select(ToolCall))
            .order_by(ToolCall.created_at.desc(), ToolCall.id.desc())
            .limit(limit)
            .execution_options(yield_per=500)
        )
        result = await self.session.stream_scalars(query)
        async for row in result:
            yield row

    async def totals(self, since: datetime) -> Totals:
        latency = ToolCall.latency_ms
        # Latency of calls that reached a server; refusals answer in a millisecond and
        # would drag the percentiles down.
        forwarded = ToolCall.status.notin_(REFUSALS)
        row = (
            await self.session.execute(
                select(
                    func.count(),
                    func.count().filter(ToolCall.status == CallStatus.OK),
                    func.count().filter(ToolCall.status.in_(FAILURES)),
                    func.count().filter(ToolCall.status.in_(REFUSALS)),
                    func.count(func.distinct(ToolCall.client_id)),
                    func.count(func.distinct(ToolCall.qualified_name)),
                    func.coalesce(
                        func.percentile_cont(0.5).within_group(latency).filter(forwarded), 0
                    ),
                    func.coalesce(
                        func.percentile_cont(0.95).within_group(latency).filter(forwarded), 0
                    ),
                ).where(ToolCall.created_at >= since)
            )
        ).one()
        return Totals(*(int(value) for value in row))

    def _bucket(self, bucket_s: int) -> Any:
        epoch = func.extract("epoch", ToolCall.created_at)
        return func.to_timestamp(func.floor(epoch / bucket_s) * bucket_s).label("bucket")

    async def series(self, since: datetime, bucket_s: int) -> list[SeriesPoint]:
        bucket = self._bucket(bucket_s)
        result = await self.session.execute(
            select(bucket, ToolCall.status, func.count())
            .where(ToolCall.created_at >= since)
            .group_by(bucket, ToolCall.status)
            .order_by(bucket)
        )
        return [SeriesPoint(start, status, int(calls)) for start, status, calls in result.all()]

    async def latency_series(self, since: datetime, bucket_s: int) -> list[LatencyPoint]:
        bucket = self._bucket(bucket_s)
        latency = ToolCall.latency_ms
        result = await self.session.execute(
            select(
                bucket,
                cast(func.percentile_cont(0.5).within_group(latency), Integer),
                cast(func.percentile_cont(0.95).within_group(latency), Integer),
            )
            .where(ToolCall.created_at >= since, ToolCall.status.notin_(REFUSALS))
            .group_by(bucket)
            .order_by(bucket)
        )
        return [
            LatencyPoint(start, int(p50 or 0), int(p95 or 0)) for start, p50, p95 in result.all()
        ]

    async def status_counts(self, since: datetime) -> dict[str, int]:
        result = await self.session.execute(
            select(ToolCall.status, func.count())
            .where(ToolCall.created_at >= since)
            .group_by(ToolCall.status)
        )
        return {status: int(count) for status, count in result.all()}

    async def top_tools(self, since: datetime, limit: int) -> list[TopItem]:
        result = await self.session.execute(
            select(
                ToolCall.qualified_name,
                func.count(),
                func.count().filter(ToolCall.status.in_(FAILURES)),
                func.count().filter(ToolCall.status.in_(REFUSALS)),
                cast(func.percentile_cont(0.95).within_group(ToolCall.latency_ms), Integer),
            )
            .where(ToolCall.created_at >= since)
            .group_by(ToolCall.qualified_name)
            .order_by(func.count().desc(), ToolCall.qualified_name)
            .limit(limit)
        )
        return [
            TopItem(name, name, int(calls), int(failed), int(refused), int(p95 or 0))
            for name, calls, failed, refused, p95 in result.all()
        ]

    async def top_clients(self, since: datetime, limit: int) -> list[TopItem]:
        result = await self.session.execute(
            select(
                ToolCall.client_id,
                func.max(ToolCall.client_name),
                func.count(),
                func.count().filter(ToolCall.status.in_(FAILURES)),
                func.count().filter(ToolCall.status.in_(REFUSALS)),
                cast(func.percentile_cont(0.95).within_group(ToolCall.latency_ms), Integer),
            )
            .where(ToolCall.created_at >= since)
            .group_by(ToolCall.client_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [
            TopItem(
                str(client_id) if client_id else "",
                name,
                int(calls),
                int(failed),
                int(refused),
                int(p95 or 0),
            )
            for client_id, name, calls, failed, refused, p95 in result.all()
        ]

    async def per_server(self, since: datetime) -> dict[uuid.UUID, tuple[int, int]]:
        """Calls and failures per server since a time."""
        result = await self.session.execute(
            select(
                ToolCall.server_id,
                func.count(),
                func.count().filter(ToolCall.status.in_(FAILURES)),
            )
            .where(ToolCall.created_at >= since, ToolCall.server_id.is_not(None))
            .group_by(ToolCall.server_id)
        )
        return {
            sid: (int(calls), int(failed)) for sid, calls, failed in result.all() if sid is not None
        }

    async def purge(self, before: datetime, batch: int) -> int:
        doomed = (
            select(ToolCall.id).where(ToolCall.created_at < before).limit(batch).scalar_subquery()
        )
        result = await self.session.execute(delete(ToolCall).where(ToolCall.id.in_(doomed)))
        return int(getattr(result, "rowcount", 0) or 0)
