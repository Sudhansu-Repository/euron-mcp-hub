"""The playground: a real call through the gateway pipeline, as a chosen client.

Operators use it to try a tool or check a policy from the dashboard. It runs exactly what
the gateway runs (the client's view, constraints, rate limits, the pooled upstream
connection) and is recorded in the call log as source `playground`, with the operator's
name, so it is never mistaken for the client's own traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mcp_types as types
from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.errors import ForbiddenError, UnprocessableError
from mcphub.models import Client
from mcphub.models.enums import CallSource
from mcphub.policy import naming
from mcphub.services.actor import Actor
from mcphub.services.call_log import CallRecord
from mcphub.services.container import Container
from mcphub.services.gateway import CallContext, GatewayService


@dataclass(frozen=True, slots=True)
class PlaygroundResult:
    record: CallRecord
    result: types.CallToolResult | None
    error: str | None


class PlaygroundService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session

    async def call(
        self, actor: Actor, client: Client, tool: str, arguments: dict[str, Any]
    ) -> PlaygroundResult:
        parts = naming.split(tool)
        if parts is None:
            raise UnprocessableError("Name the tool as <server>.<tool>.", code="invalid_tool")
        gateway = GatewayService(self.c)
        view = await gateway.build_view(client.id, 0, 0)
        if not view.active:
            raise ForbiddenError("This client is suspended.", code="client_suspended")
        exposed = naming.qualify(*parts, view.separator)
        outcome = await gateway.execute(
            view,
            exposed,
            arguments,
            CallContext(source=CallSource.PLAYGROUND, actor_user_id=actor.user_id),
        )
        error = outcome.error.error.message if outcome.error is not None else None
        return PlaygroundResult(outcome.record, outcome.result, error)
