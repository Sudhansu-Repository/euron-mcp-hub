"""One long-lived MCP session to an upstream server.

The SDK's transports and sessions run inside anyio task groups, which must be entered and
exited by the same task. So each connection is a background task that enters the SDK
client, publishes it, and holds it open until asked to close. Requests from any task are
multiplexed over the open session by JSON-RPC id.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import anyio
import mcp_types as types
from mcp import Client, Implementation

from mcphub import __version__
from mcphub.core.logging import get_logger
from mcphub.policy.scrub import scrub_known
from mcphub.upstream.errors import HttpStatus, classify
from mcphub.upstream.spec import (
    UpstreamError,
    UpstreamProtocolError,
    UpstreamSpec,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from mcphub.upstream.transports import open_transport

log = get_logger("mcphub.upstream")

CLIENT_INFO = Implementation(name="mcphub", title="Euron MCPHub", version=__version__)
_CLOSE_GRACE_S = 5.0


def make_client(
    spec: UpstreamSpec,
    *,
    connect_timeout_s: float,
    read_timeout_s: float,
    status: HttpStatus | None = None,
) -> Client:
    """An SDK client for the spec: protocol negotiated automatically, responses never cached."""
    transport = open_transport(
        spec, connect_timeout_s=connect_timeout_s, read_timeout_s=read_timeout_s, status=status
    )
    return Client(
        transport,
        mode="auto",
        cache=None,
        client_info=CLIENT_INFO,
        # Bounds the handshake; each tool call passes the server's own timeout.
        read_timeout_seconds=connect_timeout_s,
    )


class UpstreamConnection:
    def __init__(
        self,
        spec: UpstreamSpec,
        *,
        connect_timeout_s: float,
        max_call_s: float,
        max_result_bytes: int = 1_048_576,
    ) -> None:
        self.spec = spec
        self._max_result_bytes = max_result_bytes
        self.config_version = spec.config_version
        self._connect_timeout_s = connect_timeout_s
        self._max_call_s = max_call_s
        self._client: Client | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._failure: UpstreamError | None = None
        self._status = HttpStatus()
        self.broken = False
        self.inflight = 0
        self.last_used = time.monotonic()

    @property
    def usable(self) -> bool:
        return self._client is not None and not self.broken

    @property
    def protocol_version(self) -> str | None:
        return self._client.protocol_version if self._client is not None else None

    async def open(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"mcphub-upstream-{self.spec.slug}")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=self._connect_timeout_s + 2)
        except TimeoutError:
            await self.close()
            raise UpstreamTimeoutError("Connecting to the server timed out.") from None
        if self._client is None:
            raise self._failure or UpstreamUnavailableError("Could not connect to the server.")

    async def _run(self) -> None:
        client = make_client(
            self.spec,
            connect_timeout_s=self._connect_timeout_s,
            read_timeout_s=self._max_call_s,
            status=self._status,
        )
        try:
            async with client:
                self._client = client
                self._ready.set()
                log.info(
                    "upstream_connected",
                    server=self.spec.slug,
                    protocol=client.protocol_version,
                    transport=self.spec.transport.value,
                )
                await self._stop.wait()
        except Exception as exc:
            self._failure = classify(exc, self._status.last_error)
            log.warning(
                "upstream_connection_failed", server=self.spec.slug, reason=self._failure.message
            )
        finally:
            self._client = None
            self.broken = True
            self._ready.set()

    async def call_tool(
        self, name: str, arguments: dict[str, Any], timeout_s: float
    ) -> types.CallToolResult:
        client = self._client
        if client is None or self.broken:
            raise UpstreamUnavailableError("The connection to the server is closed.")
        self.inflight += 1
        self._status.last_error = None
        try:
            with anyio.fail_after(timeout_s):
                result = await client.call_tool(name, arguments, read_timeout_seconds=timeout_s)
            return self._vet(result)
        except UpstreamProtocolError:
            raise
        except Exception as exc:
            error = classify(exc, self._status.last_error)
            if isinstance(error, UpstreamTimeoutError):
                raise UpstreamTimeoutError(
                    f"The server did not answer within {timeout_s:g} seconds."
                ) from exc
            if isinstance(error, UpstreamUnavailableError):
                # The session is unusable; the pool opens a fresh one for the next call.
                self.broken = True
                self._stop.set()
            raise error from exc
        finally:
            self.inflight -= 1
            self.last_used = time.monotonic()

    def _vet(self, result: types.CallToolResult) -> types.CallToolResult:
        """Refuse an oversized result and mask the gateway's own secrets in what is left."""
        size = len(result.model_dump_json(by_alias=True, exclude_none=True))
        if size > self._max_result_bytes:
            raise UpstreamProtocolError(
                f"The result is {size:,} bytes, over the gateway's limit of "
                f"{self._max_result_bytes:,} bytes."
            )
        secrets = [*self.spec.headers.values(), *self.spec.env.values()]
        if not secrets:
            return result
        blocks = [
            block.model_copy(update={"text": scrub_known(block.text, secrets)})
            if isinstance(block, types.TextContent)
            else block
            for block in result.content
        ]
        return result.model_copy(update={"content": blocks})

    async def close(self) -> None:
        self._stop.set()
        task = self._task
        if task is None or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=_CLOSE_GRACE_S)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
