"""The call log: search and filter every tool call, inspect one, export as CSV."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from mcphub.api.deps import ContainerDep, OperatorDep, SessionDep, ViewerDep
from mcphub.models.enums import CallStatus
from mcphub.schemas.calls import (
    CallDetailOut,
    CallOut,
    CallPage,
    PlaygroundCall,
    PlaygroundResultOut,
)
from mcphub.services.calls import CallQuery, CallService
from mcphub.services.clients import ClientService
from mcphub.services.playground import PlaygroundService

router = APIRouter(prefix="/api/v1", tags=["calls"])

StatusQuery = Annotated[list[CallStatus] | None, Query(description="Repeat to match several.")]


def _query(
    client: str | None,
    server: str | None,
    tool: str | None,
    status: list[CallStatus] | None,
    source: str | None,
    q: str | None,
    since: datetime | None,
    until: datetime | None,
) -> CallQuery:
    return CallQuery(
        client=client,
        server=server,
        tool=tool,
        statuses=tuple(s.value for s in status or ()),
        source=source,
        q=q,
        since=since,
        until=until,
    )


@router.get("/calls", summary="Tool calls, newest first (keyset pages)")
async def list_calls(
    actor: ViewerDep,
    session: SessionDep,
    client: Annotated[str | None, Query(max_length=48, description="Client slug")] = None,
    server: Annotated[str | None, Query(max_length=48, description="Server slug")] = None,
    tool: Annotated[str | None, Query(max_length=200, description="tickets.create_ticket")] = None,
    status: StatusQuery = None,
    source: Annotated[str | None, Query(pattern="^(gateway|playground)$")] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Words in names, errors, arguments")
    ] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    count: bool = False,
) -> CallPage:
    query = _query(client, server, tool, status, source, q, since, until)
    service = CallService(session)
    rows, next_cursor = await service.page(query, cursor=cursor, limit=limit)
    return CallPage(
        items=[CallOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
        total=await service.count(query) if count else None,
    )


@router.get("/calls/export", summary="Matching calls as CSV (up to 100,000 rows)")
async def export_calls(
    actor: ViewerDep,
    session: SessionDep,
    client: Annotated[str | None, Query(max_length=48)] = None,
    server: Annotated[str | None, Query(max_length=48)] = None,
    tool: Annotated[str | None, Query(max_length=200)] = None,
    status: StatusQuery = None,
    source: Annotated[str | None, Query(pattern="^(gateway|playground)$")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> StreamingResponse:
    query = _query(client, server, tool, status, source, q, since, until)
    return StreamingResponse(
        CallService(session).export_csv(query),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": 'attachment; filename="mcphub-calls.csv"'},
    )


@router.get("/calls/{call_id}", summary="One call, with its recorded (redacted) arguments")
async def get_call(call_id: uuid.UUID, actor: ViewerDep, session: SessionDep) -> CallDetailOut:
    detail = await CallService(session).get(call_id)
    return CallDetailOut.model_validate(detail.call).model_copy(
        update={"actor_name": detail.actor_name}
    )


@router.post(
    "/playground/call",
    tags=["playground"],
    summary="Call a tool through the gateway pipeline as a client (recorded in the call log)",
)
async def playground_call(
    body: PlaygroundCall, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> PlaygroundResultOut:
    client = await ClientService(container, session).get(body.client)
    outcome = await PlaygroundService(container, session).call(
        actor, client, body.tool, body.arguments
    )
    result = outcome.result
    return PlaygroundResultOut(
        call=CallOut.model_validate(outcome.record),
        is_error=result.is_error if result is not None else True,
        error=outcome.error,
        content=[
            block.model_dump(mode="json", by_alias=True, exclude_none=True)
            for block in (result.content if result is not None else [])
        ],
        structured_content=result.structured_content if result is not None else None,
    )
