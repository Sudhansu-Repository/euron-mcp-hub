"""The gateway's upstream connections: one per server per process, opened on demand.

- A connection is reused while the server's `config_version` is unchanged. When it
  changes (new URL, headers, environment or secrets), the next call opens a new connection
  and the old one is retired once its in-flight calls finish.
- A broken connection is replaced on the next call. A call that fails part way is not
  retried: the server may already have acted on it.
- Idle connections are closed after `idle_timeout_s`, which also stops idle stdio
  processes.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import mcp_types as types

from mcphub.core import metrics
from mcphub.core.logging import get_logger
from mcphub.upstream.connection import UpstreamConnection
from mcphub.upstream.spec import UpstreamSpec

log = get_logger("mcphub.pool")

SpecLoader = Callable[[], Awaitable[UpstreamSpec]]
_REAP_INTERVAL_S = 15.0
_RETIRE_GRACE_S = 120.0


class UpstreamPool:
    def __init__(
        self,
        *,
        connect_timeout_s: float,
        idle_timeout_s: float,
        max_call_s: float = 600,
        max_result_bytes: int = 1_048_576,
    ) -> None:
        self._max_result_bytes = max_result_bytes
        self._connect_timeout_s = connect_timeout_s
        self._idle_timeout_s = idle_timeout_s
        self._max_call_s = max_call_s
        self._connections: dict[uuid.UUID, UpstreamConnection] = {}
        self._retiring: list[tuple[float, UpstreamConnection]] = []
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._reaper: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._reaper is None:
            self._reaper = asyncio.create_task(self._reap_forever(), name="mcphub-pool-reaper")

    async def close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        connections = list(self._connections.values()) + [c for _, c in self._retiring]
        self._connections.clear()
        self._retiring.clear()
        await asyncio.gather(*(c.close() for c in connections), return_exceptions=True)
        metrics.UPSTREAM_CONNECTIONS.set(0)

    @property
    def size(self) -> int:
        return len(self._connections)

    async def call_tool(
        self,
        server_id: uuid.UUID,
        config_version: int,
        load_spec: SpecLoader,
        name: str,
        arguments: dict[str, Any],
        timeout_s: float,
    ) -> types.CallToolResult:
        connection = await self._acquire(server_id, config_version, load_spec)
        return await connection.call_tool(name, arguments, timeout_s)

    def invalidate(self, server_id: uuid.UUID) -> None:
        """Retire this server's connection now (its configuration or secrets changed)."""
        connection = self._connections.pop(server_id, None)
        if connection is not None:
            self._retire(connection)

    async def _acquire(
        self, server_id: uuid.UUID, config_version: int, load_spec: SpecLoader
    ) -> UpstreamConnection:
        current = self._connections.get(server_id)
        if current is not None and current.usable and current.config_version == config_version:
            return current
        lock = self._locks.setdefault(server_id, asyncio.Lock())
        async with lock:
            current = self._connections.get(server_id)
            if current is not None and current.usable:
                if current.config_version == config_version:
                    return current
                if current.config_version > config_version:
                    # This caller read an older view of the catalog; the newer connection
                    # is the right one to use.
                    return current
            if current is not None:
                self._connections.pop(server_id, None)
                self._retire(current)
            spec = await load_spec()
            connection = UpstreamConnection(
                spec,
                connect_timeout_s=self._connect_timeout_s,
                max_call_s=self._max_call_s,
                max_result_bytes=self._max_result_bytes,
            )
            await connection.open()
            self._connections[server_id] = connection
            metrics.UPSTREAM_CONNECTIONS.set(len(self._connections))
            return connection

    def _retire(self, connection: UpstreamConnection) -> None:
        self._retiring.append((time.monotonic(), connection))
        metrics.UPSTREAM_CONNECTIONS.set(len(self._connections))

    async def reap(self) -> None:
        now = time.monotonic()
        for server_id, connection in list(self._connections.items()):
            idle = now - connection.last_used > self._idle_timeout_s
            if not connection.usable or (idle and connection.inflight == 0):
                self._connections.pop(server_id, None)
                self._retire(connection)
        keep: list[tuple[float, UpstreamConnection]] = []
        closing: list[UpstreamConnection] = []
        for retired_at, connection in self._retiring:
            if connection.inflight == 0 or now - retired_at > _RETIRE_GRACE_S:
                closing.append(connection)
            else:
                keep.append((retired_at, connection))
        self._retiring = keep
        if closing:
            await asyncio.gather(*(c.close() for c in closing), return_exceptions=True)
        metrics.UPSTREAM_CONNECTIONS.set(len(self._connections))

    async def _reap_forever(self) -> None:
        while True:
            await asyncio.sleep(_REAP_INTERVAL_S)
            try:
                await self.reap()
            except Exception:
                log.exception("pool_reap_failed")
