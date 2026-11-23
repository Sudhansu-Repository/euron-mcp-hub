"""Discovery and health checks: what each server offers now, and whether it answers.

Neither holds a database session while talking to the server: the server row and its
secrets are read, the session is closed, the probe runs, and a new session applies the
result. A slow upstream therefore never pins a database connection.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import mcp_types as types
from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.catalog.fingerprint import catalog_hash, diff_tools, tool_fingerprint
from mcphub.core import metrics
from mcphub.core.errors import NotFoundError, ServiceUnavailableError
from mcphub.core.logging import get_logger
from mcphub.core.text import truncate
from mcphub.models import HealthCheck, Prompt, Resource, Server, ServerVersion, Tool
from mcphub.models.enums import Health
from mcphub.repositories.catalog import CatalogRepository, HistoryRepository
from mcphub.repositories.servers import SecretRepository, ServerRepository
from mcphub.services import audit
from mcphub.services.actor import SYSTEM, Actor
from mcphub.services.container import Container
from mcphub.services.specs import build_spec
from mcphub.upstream.probe import Listing, ProbeResult, probe
from mcphub.upstream.spec import UpstreamError, UpstreamSpec

log = get_logger("mcphub.discovery")

MAX_TOOLS = 2000
HEALTH_TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    ok: bool
    error: str | None = None
    latency_ms: int | None = None
    new_version: bool = False
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HealthOutcome:
    ok: bool
    health: Health
    previous: Health
    latency_ms: int | None = None
    error: str | None = None

    @property
    def recovered(self) -> bool:
        return self.ok and self.previous in {Health.DOWN, Health.UNKNOWN}


def _annotations(tool: types.Tool) -> dict[str, Any]:
    if tool.annotations is None:
        return {}
    return tool.annotations.model_dump(mode="json", by_alias=True, exclude_none=True)


def _fingerprint(tool: types.Tool) -> str:
    return tool_fingerprint(
        name=tool.name,
        title=tool.title,
        description=tool.description,
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        annotations=_annotations(tool),
    )


class DiscoveryService:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.settings = container.settings

    async def _spec(self, server_id: uuid.UUID) -> tuple[Server, UpstreamSpec]:
        async with self.c.db.session() as session:
            server = await ServerRepository(session).get(server_id)
            if server is None:
                raise NotFoundError("Server not found.")
            secrets = await SecretRepository(session).for_server(server_id)
            return server, await build_spec(server, secrets, self.c.vaults, self.settings)

    async def discover(self, server_id: uuid.UUID, actor: Actor = SYSTEM) -> DiscoveryOutcome:
        try:
            server, spec = await self._spec(server_id)
            result = await probe(
                spec,
                connect_timeout_s=self.settings.upstream_connect_timeout_s,
                timeout_s=max(30.0, float(server.timeout_s)),
                full=True,
            )
        except (UpstreamError, ServiceUnavailableError) as exc:
            metrics.DISCOVERY_RUNS.labels("failed").inc()
            await self._discovery_failed(server_id, exc.message)
            return DiscoveryOutcome(ok=False, error=exc.message)
        outcome = await self._apply(server_id, result, actor)
        metrics.DISCOVERY_RUNS.labels("changed" if outcome.new_version else "unchanged").inc()
        return outcome

    async def _discovery_failed(self, server_id: uuid.UUID, message: str) -> None:
        async with self.c.db.session() as session:
            server = await ServerRepository(session).get(server_id)
            if server is not None:
                # Recorded as the time of the attempt, so the scheduler waits a full
                # refresh interval (or for the server to recover) before trying again.
                server.last_discovered_at = datetime.now(UTC)
                server.discovery_error = truncate(message, 1000)
                await session.commit()
        log.info("discovery_failed", server_id=str(server_id), reason=message)

    async def _apply(
        self, server_id: uuid.UUID, result: ProbeResult, actor: Actor
    ) -> DiscoveryOutcome:
        now = datetime.now(UTC)
        listing = result.listing
        async with self.c.db.session() as session:
            server = await ServerRepository(session).get(server_id)
            if server is None:
                raise NotFoundError("Server not found.")
            catalog = CatalogRepository(session)
            previous = {
                t.name: t.fingerprint for t in await catalog.tools(server_id, include_removed=False)
            }
            current = await self._sync_tools(session, server, listing.tools[:MAX_TOOLS], now)
            await self._sync_resources(session, server, listing, now)
            await self._sync_prompts(session, server, listing.prompts, now)
            diff = diff_tools(previous, current)
            resources = [r.uri for r in listing.resources] + [
                t.uri_template for t in listing.templates
            ]
            prompts = [p.name for p in listing.prompts]
            digest = catalog_hash(current, resources, prompts)
            identity = result.identity
            new_version = server.catalog_hash != digest or server.server_version != identity.version
            server.server_name = truncate(identity.name, 200) if identity.name else None
            server.server_version = truncate(identity.version, 80) if identity.version else None
            server.protocol_version = identity.protocol_version
            server.instructions = (
                truncate(identity.instructions, 5000) if identity.instructions else None
            )
            server.capabilities = identity.capabilities
            server.catalog_hash = digest
            server.last_discovered_at = now
            server.discovery_error = None
            server.tool_count = len(current)
            server.resource_count = len(resources)
            server.prompt_count = len(prompts)
            # A full discovery is also proof of life.
            server.health = Health.HEALTHY.value
            server.consecutive_failures = 0
            server.last_check_at = server.last_healthy_at = now
            server.last_latency_ms = result.latency_ms
            server.last_error = None
            if new_version:
                await HistoryRepository(session).add_version(
                    ServerVersion(
                        server_id=server.id,
                        server_version=server.server_version,
                        protocol_version=server.protocol_version,
                        catalog_hash=digest,
                        tool_count=server.tool_count,
                        resource_count=server.resource_count,
                        prompt_count=server.prompt_count,
                        tools_added=diff.added,
                        tools_removed=diff.removed,
                        tools_changed=diff.changed,
                    )
                )
                await audit.record(
                    session,
                    actor,
                    action="server.catalog_changed",
                    target_type="server",
                    target_id=server.id,
                    target_name=server.slug,
                    details={
                        "version": server.server_version,
                        "added": diff.added,
                        "removed": diff.removed,
                        "changed": diff.changed,
                    },
                )
            await session.commit()
        if new_version or not diff.is_empty:
            await self.c.cache.bump_catalog()
        return DiscoveryOutcome(
            ok=True,
            latency_ms=result.latency_ms,
            new_version=new_version,
            added=diff.added,
            removed=diff.removed,
            changed=diff.changed,
        )

    async def _sync_tools(
        self, session: AsyncSession, server: Server, listed: list[types.Tool], now: datetime
    ) -> dict[str, str]:
        existing = {
            t.name: t
            for t in await CatalogRepository(session).tools(server.id, include_removed=True)
        }
        current: dict[str, str] = {}
        for item in listed:
            fingerprint = _fingerprint(item)
            current[item.name] = fingerprint
            title = item.title or (item.annotations.title if item.annotations else None)
            row = existing.get(item.name)
            if row is None:
                session.add(
                    Tool(
                        server_id=server.id,
                        name=item.name,
                        title=title,
                        description=item.description or "",
                        input_schema=item.input_schema,
                        output_schema=item.output_schema,
                        annotations=_annotations(item),
                        fingerprint=fingerprint,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                continue
            if row.fingerprint != fingerprint:
                row.title = title
                row.description = item.description or ""
                row.input_schema = item.input_schema
                row.output_schema = item.output_schema
                row.annotations = _annotations(item)
                row.fingerprint = fingerprint
                row.changed_at = now
            row.removed_at = None
            row.last_seen_at = now
        for name, row in existing.items():
            if name not in current and row.removed_at is None:
                row.removed_at = now
        return current

    async def _sync_resources(
        self, session: AsyncSession, server: Server, listing: Listing, now: datetime
    ) -> None:
        existing = {
            r.uri: r
            for r in await CatalogRepository(session).resources(server.id, include_removed=True)
        }
        seen: set[str] = set()
        entries: Iterable[tuple[str, str, str | None, str | None, str | None, bool]] = [
            (r.uri, r.name, r.title, r.description, r.mime_type, False) for r in listing.resources
        ] + [
            (t.uri_template, t.name, t.title, t.description, t.mime_type, True)
            for t in listing.templates
        ]
        for uri, name, title, description, mime_type, is_template in entries:
            uri = uri[:1000]
            seen.add(uri)
            row = existing.get(uri)
            if row is None:
                session.add(
                    Resource(
                        server_id=server.id,
                        uri=uri,
                        name=name[:200],
                        title=title,
                        description=description or "",
                        mime_type=mime_type,
                        is_template=is_template,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                continue
            row.name, row.title, row.description = name[:200], title, description or ""
            row.mime_type, row.is_template = mime_type, is_template
            row.removed_at, row.last_seen_at = None, now
        for uri, row in existing.items():
            if uri not in seen and row.removed_at is None:
                row.removed_at = now

    async def _sync_prompts(
        self, session: AsyncSession, server: Server, listed: list[types.Prompt], now: datetime
    ) -> None:
        existing = {
            p.name: p
            for p in await CatalogRepository(session).prompts(server.id, include_removed=True)
        }
        seen: set[str] = set()
        for item in listed:
            seen.add(item.name)
            arguments = [
                {"name": a.name, "description": a.description, "required": bool(a.required)}
                for a in item.arguments or []
            ]
            row = existing.get(item.name)
            if row is None:
                session.add(
                    Prompt(
                        server_id=server.id,
                        name=item.name,
                        title=item.title,
                        description=item.description or "",
                        arguments=arguments,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                continue
            row.title, row.description, row.arguments = (
                item.title,
                item.description or "",
                arguments,
            )
            row.removed_at, row.last_seen_at = None, now
        for name, row in existing.items():
            if name not in seen and row.removed_at is None:
                row.removed_at = now

    async def check(self, server_id: uuid.UUID, actor: Actor = SYSTEM) -> HealthOutcome:
        """Connect, list the first page of tools, and record the result."""
        error: str | None = None
        latency: int | None = None
        try:
            server, spec = await self._spec(server_id)
            result = await probe(
                spec,
                connect_timeout_s=min(HEALTH_TIMEOUT_S, self.settings.upstream_connect_timeout_s),
                timeout_s=min(HEALTH_TIMEOUT_S, float(server.timeout_s) + 2),
                full=False,
            )
            latency = result.latency_ms
        except (UpstreamError, ServiceUnavailableError) as exc:
            error = exc.message
        return await self._record_check(server_id, error, latency, actor)

    async def _record_check(
        self, server_id: uuid.UUID, error: str | None, latency: int | None, actor: Actor
    ) -> HealthOutcome:
        now = datetime.now(UTC)
        ok = error is None
        metrics.HEALTH_CHECKS.labels("up" if ok else "down").inc()
        async with self.c.db.session() as session:
            server = await ServerRepository(session).get(server_id)
            if server is None:
                raise NotFoundError("Server not found.")
            previous = Health(server.health)
            await HistoryRepository(session).add_check(
                HealthCheck(
                    server_id=server.id,
                    ok=ok,
                    latency_ms=latency,
                    error=truncate(error, 1000) if error else None,
                    checked_at=now,
                )
            )
            server.last_check_at = now
            if ok:
                server.health = Health.HEALTHY.value
                server.consecutive_failures = 0
                server.last_healthy_at = now
                server.last_latency_ms = latency
                server.last_error = None
            else:
                server.consecutive_failures += 1
                threshold = self.settings.health_failure_threshold
                server.health = (
                    Health.DOWN.value
                    if server.consecutive_failures >= threshold
                    else Health.DEGRADED.value
                )
                server.last_error = truncate(error or "", 1000)
            health = Health(server.health)
            if health != previous and not (previous is Health.UNKNOWN and health is Health.HEALTHY):
                await audit.record(
                    session,
                    actor,
                    action="server.health_changed",
                    target_type="server",
                    target_id=server.id,
                    target_name=server.slug,
                    details={"from": previous.value, "to": health.value, "error": error},
                )
            await session.commit()
        return HealthOutcome(
            ok=ok, health=health, previous=previous, latency_ms=latency, error=error
        )
