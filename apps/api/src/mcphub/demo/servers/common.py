"""Serving demo servers: one process, several ports, one shutdown."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import signal
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

# The gateway reaches demo servers by container name, so the Host header is not localhost.
OPEN_HOSTS = TransportSecuritySettings(enable_dns_rebinding_protection=False)


def mcp_app(server: MCPServer) -> Starlette:
    return server.streamable_http_app(
        stateless_http=True, json_response=True, transport_security=OPEN_HOSTS
    )


def mounted(*servers: tuple[str, MCPServer]) -> Starlette:
    """Several MCP servers under one port, each at `<prefix>/mcp`.

    Starlette runs only the outer app's lifespan, so it enters every session manager.
    """
    mounts = [Mount(prefix, app=mcp_app(server)) for prefix, server in servers]

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for _prefix, server in servers:
                await stack.enter_async_context(server.session_manager.run())
            yield

    return Starlette(routes=mounts, lifespan=lifespan)


class RequireBearer:
    """Refuse requests without the expected bearer token, like a real hosted MCP server."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            supplied = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                body = (
                    b'{"error":"invalid_token","error_description":"A bearer token is required."}'
                )
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"www-authenticate", b'Bearer realm="tickets"'),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


class _Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        # Several servers share this process; `serve_all` handles signals for all of them.
        yield


async def serve_all(apps: list[tuple[ASGIApp, int]], host: str) -> None:
    servers = [
        _Server(uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False))
        for app, port in apps
    ]

    def stop() -> None:
        for server in servers:
            server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)
    await asyncio.gather(*(server.serve() for server in servers))
