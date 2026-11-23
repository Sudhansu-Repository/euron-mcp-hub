"""The tool catalog across every server."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from mcphub.api.deps import SessionDep, ViewerDep
from mcphub.api.routes.servers import tool_out
from mcphub.schemas.common import Page
from mcphub.schemas.servers import ToolOut
from mcphub.services.catalog import CatalogService

router = APIRouter(prefix="/api/v1/tools", tags=["catalog"])


@router.get("", summary="Search tools across every server")
async def search_tools(
    actor: ViewerDep,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    server: Annotated[str | None, Query(max_length=48)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ToolOut]:
    rows, total = await CatalogService(session).search_tools(
        q=q, server=server, limit=limit, offset=offset
    )
    return Page[ToolOut](
        items=[tool_out(s, t) for s, t in rows], total=total, limit=limit, offset=offset
    )
