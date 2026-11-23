"""Registering, changing and removing upstream servers, and switching tools on or off."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.errors import ConflictError, NotFoundError, UnprocessableError
from mcphub.core.logging import get_logger
from mcphub.core.text import is_valid_slug, slugify
from mcphub.models import Server, Tool
from mcphub.models.enums import Transport
from mcphub.repositories.calls import CallRepository
from mcphub.repositories.catalog import CatalogRepository, HistoryRepository
from mcphub.repositories.servers import SecretRepository, ServerFilters, ServerRepository
from mcphub.services import audit
from mcphub.services.actor import Actor
from mcphub.services.container import Container
from mcphub.services.specs import check_target, stored
from mcphub.upstream.spec import UpstreamRefusedError

log = get_logger("mcphub.servers")

_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
# Set by the transport or the protocol; an operator value would break the connection.
RESERVED_HEADERS = frozenset(
    {"host", "content-length", "content-type", "accept", "mcp-session-id", "mcp-protocol-version"}
)
# Changing any of these changes how the gateway connects, so pooled connections are replaced.
CONNECTION_FIELDS = frozenset({"transport", "url", "command", "args", "env", "headers"})
# Fields copied into client views; changing them needs the views rebuilt.
VIEW_FIELDS = frozenset({"name", "enabled", "timeout_s"})


def check_header_name(name: str) -> str:
    if not _HEADER_NAME.fullmatch(name):
        raise UnprocessableError(f"{name!r} is not a valid HTTP header name.")
    if name.lower() in RESERVED_HEADERS:
        raise UnprocessableError(f"The gateway sets the {name} header itself.")
    return name


def check_env_name(name: str) -> str:
    if not _ENV_NAME.fullmatch(name):
        raise UnprocessableError(f"{name!r} is not a valid environment variable name.")
    return name


@dataclass(slots=True)
class ServerInput:
    name: str
    transport: Transport
    slug: str | None = None
    description: str = ""
    url: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    owner: str = ""
    homepage_url: str | None = None
    timeout_s: int = 30
    refresh_interval_s: int = 300
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ServerStats:
    secrets: int = 0
    uptime_24h: float | None = None
    calls_24h: int = 0
    failed_24h: int = 0


def _normalise_tags(tags: list[str]) -> list[str]:
    seen: list[str] = []
    for tag in tags:
        value = slugify(tag, fallback="", max_length=40)
        if value and value not in seen:
            seen.append(value)
    return seen[:12]


class ServerService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.servers = ServerRepository(session)

    async def get(self, slug: str) -> Server:
        server = await self.servers.by_slug(slug)
        if server is None:
            raise NotFoundError("Server not found.")
        return server

    async def reload(self, server: Server) -> Server:
        """Re-read a server another session (discovery, a health check) has just changed."""
        await self.session.refresh(server)
        return server

    async def page(
        self, filters: ServerFilters, *, limit: int, offset: int
    ) -> tuple[list[Server], int, dict[uuid.UUID, ServerStats]]:
        servers, total = await self.servers.page(filters, limit=limit, offset=offset)
        return servers, total, await self.stats([server.id for server in servers])

    async def stats(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, ServerStats]:
        """Secrets, uptime and call volume for a page of servers, in four queries."""
        since = datetime.now(UTC) - timedelta(hours=24)
        secrets = await SecretRepository(self.session).counts(ids)
        uptime = await HistoryRepository(self.session).uptime(ids, since)
        calls = await CallRepository(self.session).per_server(since) if ids else {}
        return {
            server_id: ServerStats(
                secrets=secrets.get(server_id, 0),
                uptime_24h=uptime.get(server_id),
                calls_24h=calls.get(server_id, (0, 0))[0],
                failed_24h=calls.get(server_id, (0, 0))[1],
            )
            for server_id in ids
        }

    async def _validate(self, data: ServerInput) -> None:
        if data.transport is Transport.STREAMABLE_HTTP:
            if not data.url:
                raise UnprocessableError(
                    "A streamable HTTP server needs a URL.", code="url_required"
                )
            data.command, data.args = None, []
        else:
            if not data.command:
                raise UnprocessableError("A stdio server needs a command.", code="command_required")
            data.url = None
        for name in data.headers:
            check_header_name(name)
        for name in data.env:
            check_env_name(name)
        probe = Server(
            slug="probe",
            name=data.name,
            transport=data.transport.value,
            url=data.url,
            command=data.command,
        )
        try:
            await check_target(probe, self.c.settings)
        except UpstreamRefusedError as exc:
            raise UnprocessableError(exc.message, code="target_refused") from exc

    async def _unique_slug(self, requested: str | None, name: str) -> str:
        if requested:
            slug = requested.strip().lower()
            if not is_valid_slug(slug):
                raise UnprocessableError(
                    "Use lowercase letters, digits and single hyphens for the namespace.",
                    code="invalid_slug",
                )
            if await self.servers.slug_taken(slug):
                raise ConflictError(f"The namespace {slug} is already used by another server.")
            return slug
        base = slugify(name, fallback="server")
        slug, n = base, 2
        while await self.servers.slug_taken(slug):
            slug = f"{base[:44]}-{n}"
            n += 1
        return slug

    async def create(self, actor: Actor, data: ServerInput) -> Server:
        await self._validate(data)
        server = await self.servers.add(
            Server(
                slug=await self._unique_slug(data.slug, data.name),
                name=data.name.strip(),
                description=data.description.strip(),
                transport=data.transport.value,
                url=data.url,
                command=data.command,
                args=list(data.args),
                env=dict(data.env),
                headers=dict(data.headers),
                tags=_normalise_tags(data.tags),
                owner=data.owner.strip(),
                homepage_url=data.homepage_url,
                timeout_s=data.timeout_s,
                refresh_interval_s=data.refresh_interval_s,
                enabled=data.enabled,
                created_by=actor.user_id,
            )
        )
        await audit.record(
            self.session,
            actor,
            action="server.registered",
            target_type="server",
            target_id=server.id,
            target_name=server.slug,
            details={"transport": server.transport, "target": server.url or server.command},
        )
        await self.session.commit()
        return server

    async def update(self, actor: Actor, server: Server, changes: dict[str, Any]) -> Server:
        if not changes:
            return server
        merged = ServerInput(
            name=changes.get("name", server.name),
            transport=Transport(changes.get("transport", server.transport)),
            slug=server.slug,
            url=changes.get("url", server.url),
            command=changes.get("command", server.command),
            args=changes.get("args", server.args),
            env=changes.get("env", server.env),
            headers=changes.get("headers", server.headers),
        )
        if CONNECTION_FIELDS & changes.keys():
            await self._validate(merged)
            changes |= {"url": merged.url, "command": merged.command, "args": merged.args}
        changed: list[str] = []
        for key, value in changes.items():
            if key == "tags":
                value = _normalise_tags(value)
            if isinstance(value, str) and key in {"name", "description", "owner"}:
                value = value.strip()
            if getattr(server, key) != value:
                setattr(server, key, value)
                changed.append(key)
        if not changed:
            return server
        reconnect = bool(CONNECTION_FIELDS & set(changed))
        if reconnect:
            server.config_version += 1
        await audit.record(
            self.session,
            actor,
            action="server.updated",
            target_type="server",
            target_id=server.id,
            target_name=server.slug,
            details={"fields": sorted(changed)},
        )
        await self.session.commit()
        if reconnect or ("enabled" in changed and not server.enabled):
            self.c.pool.invalidate(server.id)
        if reconnect or VIEW_FIELDS & set(changed):
            await self.c.cache.bump_catalog()
        return server

    async def delete(self, actor: Actor, server: Server) -> None:
        secrets = await SecretRepository(self.session).for_server(server.id)
        await audit.record(
            self.session,
            actor,
            action="server.deleted",
            target_type="server",
            target_id=server.id,
            target_name=server.slug,
        )
        await self.session.delete(server)
        await self.session.commit()
        self.c.pool.invalidate(server.id)
        await self.c.cache.bump_catalog()
        # Rows are gone with the commit; values held in Secrets Manager follow. A failure
        # here only leaves an unreferenced secret, which the operator can delete in AWS.
        for secret in secrets:
            try:
                await self.c.vaults.for_backend(secret.backend).destroy(stored(secret))
            except Exception:
                log.warning("secret_destroy_failed", server=server.slug, secret=secret.name)

    async def set_tool_enabled(
        self, actor: Actor, server: Server, tool_name: str, enabled: bool
    ) -> Tool:
        tool = await CatalogRepository(self.session).tool(server.id, tool_name)
        if tool is None or tool.removed_at is not None:
            raise NotFoundError("Tool not found.")
        if tool.enabled != enabled:
            tool.enabled = enabled
            await audit.record(
                self.session,
                actor,
                action="tool.enabled" if enabled else "tool.disabled",
                target_type="tool",
                target_id=tool.id,
                target_name=f"{server.slug}.{tool.name}",
            )
            await self.session.commit()
            await self.c.cache.bump_catalog()
        return tool
