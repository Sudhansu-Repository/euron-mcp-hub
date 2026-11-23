"""The /mcp endpoint: authenticate the client key, then hand over to the SDK transport.

The SDK's streamable HTTP session manager runs stateless with JSON responses, so any API
replica can answer any request and nothing needs session affinity. The authenticated
client travels to the MCP handlers on the request scope (`request.state.mcphub`), which
the SDK attaches to every message it dispatches.
"""

from __future__ import annotations

import orjson
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.types import Receive, Scope, Send

from mcphub.core.context import get_request_id
from mcphub.core.errors import AppError, ForbiddenError, UnauthorizedError
from mcphub.core.logging import get_logger
from mcphub.gateway.server import STATE_KEY, GatewayRequest, build_server
from mcphub.services.container import Container
from mcphub.services.gateway import GatewayService

log = get_logger("mcphub.gateway")

# JSON-RPC server-error range codes for HTTP-level refusals (the body is still JSON-RPC).
_UNAUTHORIZED = -32001
_FORBIDDEN = -32003
_UNAVAILABLE = -32005


def build_manager(container: Container) -> StreamableHTTPSessionManager:
    return StreamableHTTPSessionManager(
        app=build_server(container),
        json_response=True,
        stateless=True,
        # Clients must present an API key, so DNS rebinding (which needs an ambient
        # credential) gains nothing; Origin is checked below when configured.
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        max_request_body_size=container.settings.max_request_bytes,
    )


async def _refuse(send: Send, status: int, code: int, error: AppError | None, message: str) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": code,
            "message": message,
            "data": {
                "code": error.code if error else "unavailable",
                "request_id": get_request_id(),
            },
        },
    }
    headers = [(b"content-type", b"application/json")]
    if status == 401:
        headers.append((b"www-authenticate", b'Bearer realm="mcphub", error="invalid_token"'))
    payload = orjson.dumps(body)
    headers.append((b"content-length", str(len(payload)).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class GatewayEndpoint:
    """ASGI app mounted at /mcp. Reads the container and the SDK manager from app state."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = scope["app"]
        container: Container = app.state.container
        manager: StreamableHTTPSessionManager = app.state.mcp_manager
        headers = Headers(scope=scope)

        allowed = container.settings.gateway_allowed_origins
        origin = headers.get("origin")
        if allowed and origin is not None and origin not in allowed:
            await _refuse(send, 403, _FORBIDDEN, None, "This origin may not use the gateway.")
            return

        authorization = headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            await _refuse(
                send,
                401,
                _UNAUTHORIZED,
                UnauthorizedError(code="missing_api_key"),
                "Send a client API key: Authorization: Bearer mch_...",
            )
            return
        try:
            key_id, view = await GatewayService(container).authenticate(authorization[7:].strip())
        except UnauthorizedError as exc:
            await _refuse(send, 401, _UNAUTHORIZED, exc, exc.message)
            return
        except ForbiddenError as exc:
            await _refuse(send, 403, _FORBIDDEN, exc, exc.message)
            return
        except (SQLAlchemyError, RedisError, OSError):
            log.exception("gateway_auth_unavailable")
            await _refuse(
                send, 503, _UNAVAILABLE, None, "The gateway cannot verify keys right now."
            )
            return

        scope.setdefault("state", {})[STATE_KEY] = GatewayRequest(
            key_id=key_id,
            view=view,
            request_id=get_request_id(),
            user_agent=headers.get("user-agent"),
        )
        await manager.handle_request(scope, receive, send)
