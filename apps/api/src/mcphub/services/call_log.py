"""The call log writer: every gateway call becomes a `tool_calls` row, off the hot path.

Records are queued in process and inserted in batches (every `flush_interval` or
`batch_size` rows), so recording a call costs the caller nothing but a queue append.
The same transaction stamps `last_used_at` on the keys and `last_seen_at` on the clients
in the batch, which is how the dashboard knows who is active without a write per call.

The queue is bounded. If Postgres stays down long enough to fill it, new records are
dropped and counted (`mcphub_audit_dropped_total`) rather than slowing the gateway; a
graceful shutdown drains whatever is queued.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from mcphub.core import metrics
from mcphub.core.ids import uuid7
from mcphub.core.logging import get_logger
from mcphub.db.session import Database
from mcphub.models import Client, ClientKey, PolicyRule, Server, User
from mcphub.repositories.calls import CallRepository
from mcphub.repositories.clients import ClientRepository, KeyRepository

log = get_logger("mcphub.call_log")
_WRITE_ATTEMPTS = 3


@dataclass(slots=True)
class CallRecord:
    client_name: str
    server_slug: str
    tool_name: str
    qualified_name: str
    status: str
    latency_ms: int
    client_id: uuid.UUID | None = None
    client_key_id: uuid.UUID | None = None
    server_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    source: str = "gateway"
    error_message: str | None = None
    arguments: dict[str, Any] | None = None
    result_bytes: int | None = None
    upstream_ms: int | None = None
    request_id: str | None = None
    protocol_version: str | None = None
    user_agent: str | None = None
    id: uuid.UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def row(self) -> dict[str, Any]:
        return asdict(self)


# Columns that reference rows an operator may delete while calls are in flight.
_REFERENCES: tuple[tuple[str, Any], ...] = (
    ("client_id", Client),
    ("client_key_id", ClientKey),
    ("server_id", Server),
    ("rule_id", PolicyRule),
    ("actor_user_id", User),
)


class CallLogWriter:
    def __init__(
        self,
        db: Database,
        *,
        flush_interval_s: float = 0.5,
        batch_size: int = 200,
        queue_size: int = 10_000,
    ) -> None:
        self._db = db
        self._interval = flush_interval_s
        self._batch_size = batch_size
        self._queue: asyncio.Queue[CallRecord] = asyncio.Queue(maxsize=queue_size)
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._dropped_logged = 0.0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="mcphub-call-log")

    def submit(self, record: CallRecord) -> None:
        try:
            self._queue.put_nowait(record)
            self._ready.set()
        except asyncio.QueueFull:
            metrics.AUDIT_DROPPED.inc()
            now = asyncio.get_running_loop().time()
            if now - self._dropped_logged > 10:
                self._dropped_logged = now
                log.error("call_log_full", queued=self._queue.qsize())

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()

    async def flush(self) -> int:
        """Write everything queued now (waiting for a batch already being written)."""
        async with self._lock:
            written = 0
            while not self._queue.empty():
                written += await self._write(self._take(self._batch_size))
            return written

    def _take(self, limit: int) -> list[CallRecord]:
        batch: list[CallRecord] = []
        while len(batch) < limit:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _run(self) -> None:
        while True:
            await self._ready.wait()
            # Let a batch build up for one interval, unless a full batch is already waiting.
            if self._queue.qsize() < self._batch_size:
                await asyncio.sleep(self._interval)
            self._ready.clear()
            try:
                await self.flush()
            except Exception:
                log.exception("call_log_flush_failed")

    async def _write(self, batch: list[CallRecord]) -> int:
        """Insert one batch, retrying transient failures. Caller holds the lock."""
        if not batch:
            return 0
        rows = [record.row() for record in batch]
        for attempt in range(1, _WRITE_ATTEMPTS + 1):
            try:
                await self._insert(rows)
                metrics.AUDIT_WRITTEN.inc(len(rows))
                return len(rows)
            except IntegrityError:
                # A client, key, server or rule was deleted while its calls were queued.
                rows = await self._without_dangling_references(rows)
            except SQLAlchemyError:
                log.warning("call_log_write_retry", attempt=attempt, rows=len(rows))
                await asyncio.sleep(0.5 * attempt)
        log.error("call_log_write_failed", rows=len(rows))
        metrics.AUDIT_DROPPED.inc(len(rows))
        return 0

    async def _insert(self, rows: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        keys = sorted({row["client_key_id"] for row in rows if row["client_key_id"]})
        clients = sorted({row["client_id"] for row in rows if row["client_id"]})
        async with self._db.session() as session:
            await CallRepository(session).insert_many(rows)
            await KeyRepository(session).touch(keys, now)
            await ClientRepository(session).touch(clients, now)
            await session.commit()

    async def _without_dangling_references(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with self._db.session() as session:
            for column, model in _REFERENCES:
                ids = {row[column] for row in rows if row[column]}
                if not ids:
                    continue
                existing = set(
                    (await session.execute(select(model.id).where(model.id.in_(ids)))).scalars()
                )
                for row in rows:
                    if row[column] and row[column] not in existing:
                        row[column] = None
        return rows
