"""Every client API key in one place: who holds which key, and whether it is in use."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from mcphub.api.deps import ContainerDep, SessionDep, ViewerDep
from mcphub.schemas.clients import KeyListed, KeyOut
from mcphub.schemas.common import Page
from mcphub.services.clients import ClientService

router = APIRouter(prefix="/api/v1/keys", tags=["clients"])


@router.get("", summary="API keys of every client (secrets are never shown after creation)")
async def list_all_keys(
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    state: Annotated[Literal["active", "revoked", "expired"] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[KeyListed]:
    rows, total = await ClientService(container, session).page_keys(
        state=state, q=q, limit=limit, offset=offset
    )
    return Page[KeyListed](
        items=[
            KeyListed.model_validate(
                {
                    **KeyOut.model_validate(key).model_dump(),
                    "client_slug": client.slug,
                    "client_name": client.name,
                    "client_status": client.status,
                }
            )
            for key, client in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
