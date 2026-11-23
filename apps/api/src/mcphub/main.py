"""The FastAPI application factory: the management API and the MCP gateway in one process.

uvicorn mcphub.main:create_app --factory --port 8150
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Route

from mcphub import __version__
from mcphub.api.router import api_router
from mcphub.core.config import Settings, get_settings
from mcphub.core.context import BodySizeLimitMiddleware, RequestContextMiddleware
from mcphub.core.errors import install_exception_handlers
from mcphub.core.logging import configure_logging, get_logger
from mcphub.db.migrate import migrate
from mcphub.gateway.asgi import GatewayEndpoint, build_manager
from mcphub.services.container import build_container

log = get_logger("mcphub.app")

DESCRIPTION = """
Euron MCPHub is a registry and gateway for Model Context Protocol servers.

**Management API** (`/api/v1`): authenticate with the session cookie set by
`POST /api/v1/auth/login`, or with `Authorization: Bearer <session token>`.

**MCP gateway** (`/mcp`, streamable HTTP): MCP clients authenticate with a client API key,
`Authorization: Bearer mch_...`, and see every tool their policy allows, named
`<server>.<tool>`.

Every error of the management API uses one envelope:
`{"error": {"code", "message", "request_id", "details?"}}`.
"""

TAGS = [
    {"name": "auth", "description": "Sign-in, first-run setup, sessions and your profile."},
    {"name": "users", "description": "Dashboard accounts and roles (admins)."},
    {"name": "servers", "description": "The catalog: servers, discovery, health and secrets."},
    {"name": "catalog", "description": "Tools across every server."},
    {"name": "clients", "description": "Gateway clients, API keys and policy rules."},
    {"name": "calls", "description": "The call log: every tool call, searchable."},
    {"name": "playground", "description": "Real calls through the gateway, as a client."},
    {"name": "usage", "description": "Usage charts and administrative activity."},
    {"name": "system", "description": "Deployment information."},
]

MCP_HEADERS = ["mcp-protocol-version", "mcp-session-id", "mcp-method", "last-event-id"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.is_production and (problems := settings.production_problems()):
        raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(problems))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_boot:
            await migrate(settings)
        container = build_container(settings)
        container.start()
        manager = build_manager(container)
        app.state.container = container
        app.state.mcp_manager = manager
        log.info(
            "started",
            version=__version__,
            env=settings.app_env,
            gateway=settings.public_gateway_url,
            secrets=settings.secrets_backend,
        )
        try:
            async with manager.run():
                yield
        finally:
            await container.close()

    app = FastAPI(
        title=settings.product_name,
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
        license_info={"name": "MIT", "identifier": "MIT"},
    )
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*settings.cors_origins, *settings.gateway_allowed_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-request-id", *MCP_HEADERS],
        expose_headers=[
            "x-request-id",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset",
            "content-disposition",
            "mcp-session-id",
        ],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
    app.include_router(api_router)
    # A plain ASGI route, so the SDK transport sees the raw request (and streams if needed).
    app.router.routes.append(
        Route("/mcp", endpoint=GatewayEndpoint(), methods=["GET", "POST", "DELETE"])
    )
    return app
