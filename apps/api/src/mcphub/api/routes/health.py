"""Probes, metrics and public deployment information."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from mcphub import __version__
from mcphub.api.deps import ContainerDep, SessionDep
from mcphub.core.logging import get_logger
from mcphub.repositories.users import UserRepository
from mcphub.schemas.system import SystemInfo

router = APIRouter()
log = get_logger("mcphub.health")


def _sdk_version() -> str:
    from importlib.metadata import version

    return version("mcp")


@router.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(container: ContainerDep) -> JSONResponse:
    checks: dict[str, Any] = {}
    for name, probe in (
        ("database", container.db.ping),
        ("valkey", container.redis.ping),
        ("secrets", container.vaults.active.check),
    ):
        try:
            await probe()
            checks[name] = "ok"
        except Exception as exc:
            log.warning("readiness_check_failed", check=name, error=type(exc).__name__)
            checks[name] = "failing"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/system/info", tags=["system"], summary="Deployment information")
async def system_info(container: ContainerDep, session: SessionDep) -> SystemInfo:
    settings = container.settings
    return SystemInfo(
        product_name=settings.product_name,
        version=__version__,
        mcp_sdk_version=_sdk_version(),
        gateway_url=settings.public_gateway_url,
        protocol_versions=[*HANDSHAKE_PROTOCOL_VERSIONS, *MODERN_PROTOCOL_VERSIONS],
        secrets_backend=settings.secrets_backend,
        stdio_commands=settings.stdio_allowed_commands,
        audit_retention_days=settings.audit_retention_days,
        health_interval_s=settings.health_interval_s,
        needs_setup=await UserRepository(session).count() == 0,
    )
