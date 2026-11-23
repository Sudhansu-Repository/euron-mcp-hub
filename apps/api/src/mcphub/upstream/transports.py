"""SDK transports for a spec: streamable HTTP with injected headers, or a stdio process."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from mcp import StdioServerParameters, stdio_client
from mcp.client._transport import TransportStreams
from mcp.client.streamable_http import streamable_http_client

from mcphub.models.enums import Transport
from mcphub.upstream.errors import HttpStatus
from mcphub.upstream.spec import UpstreamRefusedError, UpstreamSpec

USER_AGENT = "mcphub-gateway"


@asynccontextmanager
async def open_transport(
    spec: UpstreamSpec,
    *,
    connect_timeout_s: float,
    read_timeout_s: float,
    status: HttpStatus | None = None,
) -> AsyncIterator[TransportStreams]:
    """Read and write streams to the server, closed (and the process stopped) on exit."""
    if spec.transport is Transport.STREAMABLE_HTTP:
        if not spec.url:
            raise UpstreamRefusedError("This server has no URL.")
        headers = {"user-agent": USER_AGENT, **spec.headers}
        timeout = httpx2.Timeout(connect_timeout_s, read=read_timeout_s)
        # Redirects are left off: the SDK follows same-origin redirects itself, and a
        # redirect elsewhere must not carry the injected secret headers along.
        hooks = {"response": [status.record]} if status is not None else {}
        async with (
            httpx2.AsyncClient(headers=headers, timeout=timeout, event_hooks=hooks) as http,
            streamable_http_client(spec.url, http_client=http) as streams,
        ):
            yield streams
        return
    if not spec.command:
        raise UpstreamRefusedError("This server has no command.")
    params = StdioServerParameters(command=spec.command, args=list(spec.args), env=dict(spec.env))
    # The server's stderr joins the gateway's own, so crashes are visible in its logs.
    async with stdio_client(params, errlog=sys.stderr) as streams:
        yield streams
