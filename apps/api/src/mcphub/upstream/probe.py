"""Short-lived connections for health checks and discovery, separate from the pool.

A probe opens its own session, so checking or rediscovering a server never disturbs the
connection live gateway traffic is using, and always sees the server as a new client
would.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import anyio
import mcp_types as types
from mcp import Client, MCPError

from mcphub.upstream.connection import make_client
from mcphub.upstream.errors import HttpStatus, classify
from mcphub.upstream.spec import UpstreamSpec

MAX_PAGES = 50
_METHOD_NOT_FOUND = -32601


@dataclass(frozen=True, slots=True)
class Identity:
    """What a server says about itself when a client connects."""

    name: str | None
    version: str | None
    protocol_version: str | None
    instructions: str | None
    capabilities: dict[str, Any]


@dataclass(slots=True)
class Listing:
    tools: list[types.Tool] = field(default_factory=list)
    resources: list[types.Resource] = field(default_factory=list)
    templates: list[types.ResourceTemplate] = field(default_factory=list)
    prompts: list[types.Prompt] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    identity: Identity
    listing: Listing
    latency_ms: int


def _identity(client: Client) -> Identity:
    info = client.server_info
    capabilities = client.server_capabilities.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return Identity(
        name=info.name if info else None,
        version=(info.version or None) if info else None,
        protocol_version=client.protocol_version,
        instructions=client.instructions,
        capabilities=capabilities,
    )


async def _pages[PageT](
    fetch: Callable[[str | None], Awaitable[Any]], items: Callable[[Any], list[PageT]]
) -> list[PageT]:
    collected: list[PageT] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        page = await fetch(cursor)
        collected.extend(items(page))
        cursor = page.next_cursor
        if not cursor:
            break
    return collected


async def _optional[PageT](
    fetch: Callable[[str | None], Awaitable[Any]], items: Callable[[Any], list[PageT]]
) -> list[PageT]:
    """Pages of an optional listing; a server that does not serve it has none."""
    try:
        return await _pages(fetch, items)
    except MCPError as exc:
        if exc.code == _METHOD_NOT_FOUND:
            return []
        raise


async def probe(
    spec: UpstreamSpec, *, connect_timeout_s: float, timeout_s: float, full: bool
) -> ProbeResult:
    """Connect, read the server's identity, and list its tools (everything when `full`).

    Raises an `UpstreamError` subclass with a readable message on any failure.
    """
    started = time.perf_counter()
    status = HttpStatus()
    try:
        with anyio.fail_after(timeout_s):
            async with make_client(
                spec, connect_timeout_s=connect_timeout_s, read_timeout_s=timeout_s, status=status
            ) as client:
                identity = _identity(client)
                listing = Listing()
                if not full:
                    listing.tools = (await client.list_tools()).tools
                else:
                    listing.tools = await _pages(
                        lambda cursor: client.list_tools(cursor=cursor), lambda p: p.tools
                    )
                    caps = client.server_capabilities
                    if caps.resources is not None:
                        listing.resources = await _optional(
                            lambda cursor: client.list_resources(cursor=cursor),
                            lambda p: p.resources,
                        )
                        listing.templates = await _optional(
                            lambda cursor: client.list_resource_templates(cursor=cursor),
                            lambda p: p.resource_templates,
                        )
                    if caps.prompts is not None:
                        listing.prompts = await _optional(
                            lambda cursor: client.list_prompts(cursor=cursor),
                            lambda p: p.prompts,
                        )
    except Exception as exc:
        raise classify(exc, status.last_error) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ProbeResult(identity=identity, listing=listing, latency_ms=latency_ms)
