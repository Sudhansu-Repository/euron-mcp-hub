"""Turning transport and SDK failures into messages an operator (or a model) can act on."""

from __future__ import annotations

from dataclasses import dataclass

import anyio
import httpx2
from mcp import MCPError
from mcp_types import CONNECTION_CLOSED, METHOD_NOT_FOUND, REQUEST_TIMEOUT
from pydantic import ValidationError

from mcphub.upstream.spec import (
    UpstreamError,
    UpstreamProtocolError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

_BROKEN = (
    anyio.ClosedResourceError,
    anyio.BrokenResourceError,
    anyio.EndOfStream,
    httpx2.TransportError,
    OSError,
)


@dataclass
class HttpStatus:
    """The last HTTP error status a server answered with.

    The SDK turns a non-JSON error response into a generic JSON-RPC error and drops the
    status code, which is the most useful part ("401" means the token secret is wrong).
    An httpx event hook records it here, for `classify` to put back in the message.
    """

    last_error: int | None = None

    async def record(self, response: httpx2.Response) -> None:
        if response.status_code >= 400:
            self.last_error = response.status_code


def leaf(exc: BaseException) -> BaseException:
    """The first concrete exception inside (possibly nested) exception groups."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    if isinstance(exc, MCPError | UpstreamError | TimeoutError):
        return exc
    cause = exc.__cause__ or exc.__context__
    if isinstance(cause, httpx2.TransportError | OSError | MCPError):
        return cause
    return exc


def _http_message(status: int) -> UpstreamUnavailableError:
    if status in {401, 403}:
        return UpstreamUnavailableError(
            f"The server refused the gateway's credentials (HTTP {status}); "
            "check this server's header secrets."
        )
    if status == 404:
        return UpstreamUnavailableError("The server answered HTTP 404; check the URL and path.")
    return UpstreamUnavailableError(f"The server answered HTTP {status}.")


def classify(exc: BaseException, http_status: int | None = None) -> UpstreamError:
    """The UpstreamError subclass and safe message for any failure talking to a server."""
    root = leaf(exc)
    if isinstance(root, UpstreamError):
        return root
    if isinstance(root, TimeoutError | httpx2.TimeoutException):
        return UpstreamTimeoutError("The server did not answer in time.")
    if isinstance(root, MCPError):
        if root.code == CONNECTION_CLOSED:
            return UpstreamUnavailableError("The connection to the server was lost.")
        if root.code == REQUEST_TIMEOUT:
            return UpstreamTimeoutError("The server did not answer in time.")
        if http_status is not None:
            return _http_message(http_status)
        if root.code == METHOD_NOT_FOUND and root.error.message == "Not Found":
            return _http_message(404)
        return UpstreamProtocolError(
            f"The server returned an error: {root.error.message}", root.code
        )
    if isinstance(root, ValidationError):
        return UpstreamProtocolError("The server's answer did not follow the MCP schema.")
    if isinstance(root, httpx2.ConnectError):
        return UpstreamUnavailableError("Could not connect to the server.")
    if isinstance(root, httpx2.HTTPStatusError):
        return _http_message(root.response.status_code)
    if isinstance(root, FileNotFoundError):
        return UpstreamUnavailableError("The stdio command was not found on the gateway host.")
    if isinstance(root, PermissionError):
        return UpstreamUnavailableError("The stdio command is not executable.")
    if isinstance(root, _BROKEN):
        return UpstreamUnavailableError("The connection to the server was lost.")
    return UpstreamUnavailableError(f"The server could not be used ({type(root).__name__}).")
