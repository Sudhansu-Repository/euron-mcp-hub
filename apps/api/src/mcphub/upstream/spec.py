"""What it takes to reach one upstream server, and how reaching it can fail."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from mcphub.models.enums import Transport


@dataclass(frozen=True, slots=True)
class UpstreamSpec:
    """A server's connection settings with its secrets already decrypted.

    Lives only in memory for as long as a connection is being opened. `repr` hides header
    and environment values so a spec can never end up in a log line or a traceback.
    """

    server_id: uuid.UUID
    slug: str
    transport: Transport
    config_version: int
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    headers: Mapping[str, str] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        target = self.url if self.transport is Transport.STREAMABLE_HTTP else self.command
        return (
            f"UpstreamSpec(slug={self.slug!r}, transport={self.transport.value}, "
            f"target={target!r}, headers={sorted(self.headers)}, env={sorted(self.env)})"
        )


class UpstreamError(Exception):
    """The upstream server could not be used. The message is safe to show to a client."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UpstreamUnavailableError(UpstreamError):
    """Could not connect, or the connection broke."""


class UpstreamTimeoutError(UpstreamError):
    """The server did not answer within its timeout."""


class UpstreamRefusedError(UpstreamError):
    """The server's address or command is not allowed by this deployment's guards."""


class UpstreamProtocolError(UpstreamError):
    """The server answered with a JSON-RPC error instead of a result."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
