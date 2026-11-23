"""Value sets stored as text with CHECK constraints (cheaper to evolve than Postgres enums)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return {Role.VIEWER: 1, Role.OPERATOR: 2, Role.ADMIN: 3}[self]

    def allows(self, required: Role) -> bool:
        return self.rank >= required.rank


class Transport(StrEnum):
    STREAMABLE_HTTP = "streamable_http"
    STDIO = "stdio"


class Health(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    # The last check failed, but fewer times in a row than the failure threshold.
    DEGRADED = "degraded"
    DOWN = "down"


class SecretKind(StrEnum):
    HEADER = "header"
    ENV = "env"


class ClientStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Effect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class CallStatus(StrEnum):
    OK = "ok"
    TOOL_ERROR = "tool_error"
    DENIED = "denied"
    BLOCKED = "blocked"
    INVALID_ARGUMENTS = "invalid_arguments"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_ERROR = "upstream_error"
    TIMEOUT = "timeout"

    @property
    def is_failure(self) -> bool:
        return self is not CallStatus.OK


class CallSource(StrEnum):
    GATEWAY = "gateway"
    PLAYGROUND = "playground"
