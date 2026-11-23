from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from mcphub.policy.constraints import Constraint
from mcphub.schemas.common import ApiModel

EffectName = Literal["allow", "deny"]
SeparatorName = Literal[".", "__"]


class ClientCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=48)
    description: str = Field(default="", max_length=1000)
    default_effect: EffectName = Field(
        default="deny", description="What a tool no rule matches gets. Deny is least privilege."
    )
    tool_separator: SeparatorName = "."
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    record_arguments: bool = True
    key_name: str = Field(default="Default key", min_length=1, max_length=80)
    key_expires_in_days: int | None = Field(default=None, ge=1, le=730)


class ClientUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    status: Literal["active", "suspended"] | None = None
    default_effect: EffectName | None = None
    tool_separator: SeparatorName | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    record_arguments: bool | None = None


class ClientOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    status: str
    default_effect: str
    tool_separator: str
    rate_limit_per_minute: int | None
    record_arguments: bool
    policy_version: int
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
    active_keys: int = 0
    rules: int = 0
    calls_24h: int = 0


class KeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    expires_in_days: int | None = Field(default=None, ge=1, le=730)


class KeyOut(ApiModel):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class KeyListed(KeyOut):
    client_slug: str
    client_name: str
    client_status: str


class KeyCreated(KeyOut):
    key: str = Field(description="The full key. Shown once; only a keyed hash is stored.")


class ClientCreated(ApiModel):
    client: ClientOut
    key: KeyCreated
    gateway_url: str


class RuleCreate(ApiModel):
    pattern: str = Field(
        min_length=1,
        max_length=260,
        description="<server>.<tool> with * and ? wildcards: tickets.*, tickets.get_*, *.",
    )
    effect: EffectName = "allow"
    constraints: list[Constraint] = Field(default_factory=list, max_length=50)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    redact: list[str] = Field(default_factory=list, max_length=50)
    description: str = Field(default="", max_length=300)


class RuleUpdate(ApiModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=260)
    effect: EffectName | None = None
    constraints: list[Constraint] | None = Field(default=None, max_length=50)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    redact: list[str] | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=300)


class RuleOut(ApiModel):
    id: uuid.UUID
    pattern: str
    effect: str
    constraints: list[dict[str, Any]]
    rate_limit_per_minute: int | None
    redact: list[str]
    description: str
    created_at: datetime
    updated_at: datetime


class AccessOut(ApiModel):
    server_slug: str
    server_name: str
    tool: str
    qualified_name: str
    exposed_name: str
    title: str | None
    description: str
    allowed: bool
    reason: str
    rule_id: uuid.UUID | None
    rule_pattern: str | None
    read_only: bool | None
    destructive: bool | None


class SimulateRequest(ApiModel):
    tool: str = Field(min_length=3, max_length=200, description="tickets.create_ticket")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ViolationOut(ApiModel):
    argument: str
    rule: str
    message: str


class SimulateOut(ApiModel):
    tool: str
    exposed_name: str
    found: bool
    allowed: bool
    reason: str
    rule_id: uuid.UUID | None
    rule_pattern: str | None
    schema_errors: list[str]
    violations: list[ViolationOut]
    would_call: bool
