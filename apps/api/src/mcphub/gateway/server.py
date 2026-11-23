"""The MCP server clients talk to, built on the SDK's low-level `Server`.

Handlers are a route layer for MCP: they read the authenticated client the ASGI endpoint
attached to the request and delegate to `GatewayService`. They never let an unexpected
exception reach the SDK, which would echo its message to the client on handshake-era
connections; the client gets a generic error and the log gets the traceback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import mcp_types as types
from mcp import MCPError
from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp_types import INTERNAL_ERROR

from mcphub import __version__
from mcphub.core.logging import get_logger
from mcphub.services.container import Container
from mcphub.services.gateway import CallContext, GatewayService
from mcphub.services.views import ClientView

log = get_logger("mcphub.gateway")

STATE_KEY = "mcphub"
INSTRUCTIONS = (
    "Tools from several MCP servers, each named <server>.<tool> (or <server>__<tool>). "
    "Only the tools this client's policy allows are listed. A tool result that starts with "
    "'Rate limit exceeded' or names a policy rule explains what to change before retrying."
)


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """Who is calling, attached to the HTTP request by the authenticating endpoint."""

    key_id: uuid.UUID
    view: ClientView
    request_id: str | None
    user_agent: str | None


def _caller(ctx: ServerRequestContext[Any, Any]) -> GatewayRequest:
    request = ctx.request
    caller = getattr(getattr(request, "state", None), STATE_KEY, None)
    if not isinstance(caller, GatewayRequest):
        # Only reachable if the SDK were mounted without the authenticating endpoint.
        raise MCPError(code=INTERNAL_ERROR, message="The request was not authenticated.")
    return caller


def build_server(container: Container) -> Server[Any]:
    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        caller = _caller(ctx)
        try:
            return GatewayService(container).list_tools(
                caller.view, params.cursor if params else None
            )
        except MCPError:
            raise
        except Exception as exc:
            log.exception("gateway_list_failed", client=caller.view.slug)
            raise MCPError(
                code=INTERNAL_ERROR, message="The gateway failed to list tools."
            ) from exc

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        caller = _caller(ctx)
        try:
            return await GatewayService(container).call(
                caller.view,
                params.name,
                params.arguments,
                CallContext(
                    key_id=caller.key_id,
                    request_id=caller.request_id,
                    protocol_version=ctx.protocol_version,
                    user_agent=caller.user_agent,
                ),
            )
        except MCPError:
            raise
        except Exception as exc:
            log.exception("gateway_call_failed", client=caller.view.slug, tool=params.name)
            raise MCPError(
                code=INTERNAL_ERROR, message="The gateway failed to run the call."
            ) from exc

    return Server(
        "mcphub",
        version=__version__,
        title=container.settings.product_name,
        description="One endpoint for the tools of every registered MCP server.",
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
