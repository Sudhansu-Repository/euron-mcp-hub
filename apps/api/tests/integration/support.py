"""Helpers for the integration suite: an API client per role, MCP sessions, upstream servers."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import httpx2
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.types import ASGIApp

from mcphub.demo.servers.common import RequireBearer, mcp_app, mounted
from mcphub.demo.servers.notes import build_notes_server
from mcphub.demo.servers.tickets import LATEST, PREVIOUS, Queue, build_tickets_server
from mcphub.demo.servers.toolbox import build_toolbox_server

PASSWORD = "Integration-Pass-9137!"
GATEWAY = "http://gateway.test"


def rows(body: Any) -> list[dict[str, Any]]:
    """The items of a list response, whether it is a plain list or a page."""
    items: list[dict[str, Any]] = body["items"] if isinstance(body, dict) else body
    return items


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Api:
    """The management API as one signed-in person (bearer token), over ASGI."""

    def __init__(self, http: httpx2.AsyncClient, email: str) -> None:
        self.http = http
        self.email = email

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx2.Response:
        return await self.http.request(method, f"/api/v1{path}", **kwargs)

    async def get(self, path: str, **params: Any) -> httpx2.Response:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: dict[str, Any] | None = None) -> httpx2.Response:
        return await self.request("POST", path, json=body or {})

    async def put(self, path: str, body: dict[str, Any]) -> httpx2.Response:
        return await self.request("PUT", path, json=body)

    async def patch(self, path: str, body: dict[str, Any]) -> httpx2.Response:
        return await self.request("PATCH", path, json=body)

    async def delete(self, path: str) -> httpx2.Response:
        return await self.request("DELETE", path)

    async def ok(self, response: httpx2.Response) -> Any:
        assert response.status_code < 300, f"{response.status_code}: {response.text}"
        return response.json() if response.content else None


@dataclass(frozen=True)
class Upstreams:
    notes: str
    toolbox: str
    tickets: str
    tickets_v1: str
    tickets_token: str


class _Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _free_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock


@contextlib.asynccontextmanager
async def serve(app: ASGIApp) -> AsyncIterator[str]:
    """Serve an ASGI app on a free local port for the duration of the block."""
    sock = _free_socket()
    server = _Server(uvicorn.Config(app, log_level="warning", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.02)
        if task.done():
            task.result()
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        await task
        sock.close()


@contextlib.asynccontextmanager
async def upstream_servers(tickets_token: str) -> AsyncIterator[Upstreams]:
    queue = Queue()
    tickets: Starlette = mounted(
        ("/v1", build_tickets_server(queue, version=PREVIOUS)),
        ("", build_tickets_server(queue, version=LATEST)),
    )
    async with (
        serve(mcp_app(build_notes_server())) as notes,
        serve(mcp_app(build_toolbox_server())) as toolbox,
        serve(RequireBearer(tickets, tickets_token)) as ticket_base,
    ):
        yield Upstreams(
            notes=f"{notes}/mcp",
            toolbox=f"{toolbox}/mcp",
            tickets=f"{ticket_base}/mcp",
            tickets_v1=f"{ticket_base}/v1/mcp",
            tickets_token=tickets_token,
        )


@contextlib.asynccontextmanager
async def mcp_session(
    app: Any, key: str, *, headers: dict[str, str] | None = None
) -> AsyncIterator[Client]:
    """An MCP client session against the gateway, authenticated with a client API key."""
    async with (
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url=GATEWAY,
            timeout=60,
            headers={"authorization": f"Bearer {key}", **(headers or {})},
        ) as http,
        Client(
            streamable_http_client(f"{GATEWAY}/mcp", http_client=http), mode="auto", cache=None
        ) as client,
    ):
        yield client


def text_of(result: Any) -> str:
    return "".join(block.text for block in result.content if getattr(block, "text", None))


@contextlib.asynccontextmanager
async def held[T](manager: contextlib.AbstractAsyncContextManager[T]) -> AsyncIterator[T]:
    """Enter an async context in a task of its own and keep it open until the block ends.

    anyio task groups (the MCP session manager runs one) must be exited by the task that
    entered them, but a pytest fixture's setup and teardown run in different tasks.
    """
    ready: asyncio.Future[T] = asyncio.get_running_loop().create_future()
    release = asyncio.Event()

    async def run() -> None:
        try:
            async with manager as value:
                ready.set_result(value)
                await release.wait()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            else:
                raise

    task = asyncio.create_task(run())
    try:
        yield await ready
    finally:
        release.set()
        await task
