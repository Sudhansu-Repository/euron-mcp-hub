"""Usage over time, and the administrative activity feed."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from mcphub.api.deps import ContainerDep, SessionDep, ViewerDep
from mcphub.schemas.common import Page
from mcphub.schemas.stats import OverviewOut
from mcphub.schemas.system import ActivityOut
from mcphub.services import audit
from mcphub.services.stats import StatsService

router = APIRouter(prefix="/api/v1", tags=["usage"])


@router.get("/stats/overview", summary="Calls, outcomes, latency, top tools and clients")
async def overview(
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    range_: Annotated[Literal["24h", "7d", "30d"], Query(alias="range")] = "24h",
) -> OverviewOut:
    return OverviewOut.model_validate(await StatsService(container, session).overview(range_))


@router.get("/activity", summary="Administrative changes, newest first")
async def activity(
    actor: ViewerDep,
    session: SessionDep,
    target_type: Annotated[Literal["server", "tool", "client", "user"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ActivityOut]:
    events, total = await audit.activity(
        session, target_type=target_type, limit=limit, offset=offset
    )
    return Page[ActivityOut](
        items=[ActivityOut.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )
