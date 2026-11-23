"""The catalog: servers, their tools, resources, prompts, history, health and secrets."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from mcphub.api.deps import ContainerDep, OperatorDep, SessionDep, ViewerDep
from mcphub.models import Server, Tool
from mcphub.models.enums import SecretKind, Transport
from mcphub.policy.naming import canonical
from mcphub.repositories.servers import ServerFilters
from mcphub.schemas.common import Page
from mcphub.schemas.servers import (
    DiscoveryOut,
    HealthCheckOut,
    HealthHistoryOut,
    PromptOut,
    ResourceOut,
    SecretOut,
    SecretSet,
    ServerCreate,
    ServerOut,
    ServerUpdate,
    ToolOut,
    ToolUpdate,
    VersionOut,
)
from mcphub.services.catalog import CatalogService
from mcphub.services.discovery import DiscoveryService
from mcphub.services.secrets import SecretService
from mcphub.services.servers import ServerInput, ServerService, ServerStats

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


def server_out(server: Server, stats: ServerStats | None = None) -> ServerOut:
    stats = stats or ServerStats()
    return ServerOut.model_validate(server).model_copy(
        update={
            "secret_count": stats.secrets,
            "uptime_24h": stats.uptime_24h,
            "calls_24h": stats.calls_24h,
            "failed_24h": stats.failed_24h,
        }
    )


def tool_out(server: Server, tool: Tool) -> ToolOut:
    return ToolOut.model_validate(
        {
            **{key: getattr(tool, key) for key in ToolOut.model_fields if hasattr(tool, key)},
            "server_slug": server.slug,
            "qualified_name": canonical(server.slug, tool.name),
        }
    )


async def _with_stats(service: ServerService, server: Server) -> ServerOut:
    stats = await service.stats([server.id])
    return server_out(server, stats.get(server.id))


@router.get("", summary="Servers in the catalog")
async def list_servers(
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    health: Annotated[Literal["unknown", "healthy", "degraded", "down"] | None, Query()] = None,
    transport: Annotated[Literal["streamable_http", "stdio"] | None, Query()] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    enabled: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ServerOut]:
    servers, total, stats = await ServerService(container, session).page(
        ServerFilters(q=q, health=health, transport=transport, tag=tag, enabled=enabled),
        limit=limit,
        offset=offset,
    )
    return Page[ServerOut](
        items=[server_out(s, stats.get(s.id)) for s in servers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", summary="Register a server (and discover it)", status_code=status.HTTP_201_CREATED)
async def create_server(
    body: ServerCreate, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> ServerOut:
    service = ServerService(container, session)
    fields = body.model_dump(exclude={"discover", "transport"})
    server = await service.create(actor, ServerInput(transport=Transport(body.transport), **fields))
    if body.discover and server.enabled:
        await DiscoveryService(container).discover(server.id, actor)
        server = await service.reload(server)
    return await _with_stats(service, server)


@router.get("/{slug}", summary="One server")
async def get_server(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> ServerOut:
    service = ServerService(container, session)
    return await _with_stats(service, await service.get(slug))


@router.patch("/{slug}", summary="Change a server's settings")
async def update_server(
    slug: str, body: ServerUpdate, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> ServerOut:
    service = ServerService(container, session)
    server = await service.update(
        actor, await service.get(slug), body.model_dump(exclude_unset=True)
    )
    return await _with_stats(service, server)


@router.delete("/{slug}", summary="Remove a server and its secrets", status_code=204)
async def delete_server(
    slug: str, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = ServerService(container, session)
    await service.delete(actor, await service.get(slug))


@router.post("/{slug}/refresh", summary="Discover the server's tools, resources and prompts now")
async def refresh_server(
    slug: str, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> DiscoveryOut:
    service = ServerService(container, session)
    server = await service.get(slug)
    outcome = await DiscoveryService(container).discover(server.id, actor)
    server = await service.reload(server)
    return DiscoveryOut(
        ok=outcome.ok,
        error=outcome.error,
        latency_ms=outcome.latency_ms,
        new_version=outcome.new_version,
        added=outcome.added,
        removed=outcome.removed,
        changed=outcome.changed,
        server=await _with_stats(service, server),
    )


@router.post("/{slug}/check", summary="Run a health check now")
async def check_server(
    slug: str, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> HealthCheckOut:
    service = ServerService(container, session)
    server = await service.get(slug)
    outcome = await DiscoveryService(container).check(server.id, actor)
    server = await service.reload(server)
    return HealthCheckOut(
        ok=outcome.ok,
        health=outcome.health.value,
        latency_ms=outcome.latency_ms,
        error=outcome.error,
        server=await _with_stats(service, server),
    )


@router.get("/{slug}/tools", summary="The server's tools")
async def server_tools(
    slug: str,
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    include_removed: bool = False,
) -> list[ToolOut]:
    server = await ServerService(container, session).get(slug)
    tools = await CatalogService(session).tools(server, include_removed=include_removed)
    return [tool_out(server, tool) for tool in tools]


@router.patch("/{slug}/tools/{name:path}", summary="Take a tool out of the gateway, or put it back")
async def update_tool(
    slug: str,
    name: str,
    body: ToolUpdate,
    actor: OperatorDep,
    container: ContainerDep,
    session: SessionDep,
) -> ToolOut:
    service = ServerService(container, session)
    server = await service.get(slug)
    return tool_out(server, await service.set_tool_enabled(actor, server, name, body.enabled))


@router.get("/{slug}/resources", summary="The server's resources and resource templates")
async def server_resources(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[ResourceOut]:
    server = await ServerService(container, session).get(slug)
    return [ResourceOut.model_validate(r) for r in await CatalogService(session).resources(server)]


@router.get("/{slug}/prompts", summary="The server's prompts")
async def server_prompts(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[PromptOut]:
    server = await ServerService(container, session).get(slug)
    return [PromptOut.model_validate(p) for p in await CatalogService(session).prompts(server)]


@router.get("/{slug}/versions", summary="Changes to the server's version and catalog, newest first")
async def server_versions(
    slug: str,
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[VersionOut]:
    server = await ServerService(container, session).get(slug)
    versions, total = await CatalogService(session).versions(server, limit=limit, offset=offset)
    return Page[VersionOut](
        items=[VersionOut.model_validate(v) for v in versions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug}/health", summary="Health check history: uptime and latency")
async def server_health(
    slug: str,
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> HealthHistoryOut:
    server = await ServerService(container, session).get(slug)
    history = await CatalogService(session).health(server, hours)
    return HealthHistoryOut.model_validate(history)


@router.get("/{slug}/secrets", summary="The server's secrets: names only, never values")
async def list_secrets(
    slug: str, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> list[SecretOut]:
    server = await ServerService(container, session).get(slug)
    secrets = await SecretService(container, session).list(server)
    return [SecretOut.model_validate(s) for s in secrets]


@router.put("/{slug}/secrets", summary="Set a header or environment secret (write-only)")
async def set_secret(
    slug: str, body: SecretSet, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> SecretOut:
    server = await ServerService(container, session).get(slug)
    secret = await SecretService(container, session).set(
        actor, server, SecretKind(body.kind), body.name, body.value
    )
    return SecretOut.model_validate(secret)


@router.delete("/{slug}/secrets/{secret_id}", summary="Delete a secret", status_code=204)
async def delete_secret(
    slug: str,
    secret_id: uuid.UUID,
    actor: OperatorDep,
    container: ContainerDep,
    session: SessionDep,
) -> None:
    server = await ServerService(container, session).get(slug)
    await SecretService(container, session).delete(actor, server, secret_id)
