from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from mcphub.schemas.common import ApiModel

TransportName = Literal["streamable_http", "stdio"]


class ServerCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(
        default=None,
        max_length=48,
        description=(
            "The tool namespace: `tickets` gives `tickets.create_ticket`. "
            "Derived from the name when omitted."
        ),
    )
    description: str = Field(default="", max_length=2000)
    transport: TransportName = "streamable_http"
    url: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=300)
    args: list[str] = Field(default_factory=list, max_length=50)
    env: dict[str, str] = Field(
        default_factory=dict, description="Non-secret environment for stdio servers."
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Non-secret HTTP headers. Put credentials in secrets."
    )
    tags: list[str] = Field(default_factory=list, max_length=12)
    owner: str = Field(default="", max_length=120)
    homepage_url: str | None = Field(default=None, max_length=500)
    timeout_s: int = Field(default=30, ge=1, le=600)
    refresh_interval_s: int = Field(default=300, ge=30, le=86_400)
    enabled: bool = True
    discover: bool = Field(default=True, description="Run discovery right after registering.")


class ServerUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    transport: TransportName | None = None
    url: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=300)
    args: list[str] | None = Field(default=None, max_length=50)
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    tags: list[str] | None = Field(default=None, max_length=12)
    owner: str | None = Field(default=None, max_length=120)
    homepage_url: str | None = Field(default=None, max_length=500)
    timeout_s: int | None = Field(default=None, ge=1, le=600)
    refresh_interval_s: int | None = Field(default=None, ge=30, le=86_400)
    enabled: bool | None = None


class ServerOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    transport: str
    url: str | None
    command: str | None
    args: list[str]
    env: dict[str, Any]
    headers: dict[str, Any]
    tags: list[str]
    owner: str
    homepage_url: str | None
    enabled: bool
    timeout_s: int
    refresh_interval_s: int
    config_version: int
    health: str
    consecutive_failures: int
    last_check_at: datetime | None
    last_healthy_at: datetime | None
    last_latency_ms: int | None
    last_error: str | None
    server_name: str | None
    server_version: str | None
    protocol_version: str | None
    instructions: str | None
    capabilities: dict[str, Any]
    last_discovered_at: datetime | None
    discovery_error: str | None
    tool_count: int
    resource_count: int
    prompt_count: int
    created_at: datetime
    updated_at: datetime
    secret_count: int = 0
    uptime_24h: float | None = None
    calls_24h: int = 0
    failed_24h: int = 0


class DiscoveryOut(ApiModel):
    ok: bool
    error: str | None
    latency_ms: int | None
    new_version: bool
    added: list[str]
    removed: list[str]
    changed: list[str]
    server: ServerOut


class HealthCheckOut(ApiModel):
    ok: bool
    health: str
    latency_ms: int | None
    error: str | None
    server: ServerOut


class ToolOut(ApiModel):
    id: uuid.UUID
    server_slug: str
    name: str
    qualified_name: str
    title: str | None
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]
    enabled: bool
    fingerprint: str
    first_seen_at: datetime
    last_seen_at: datetime
    changed_at: datetime | None
    removed_at: datetime | None


class ToolUpdate(ApiModel):
    enabled: bool


class ResourceOut(ApiModel):
    id: uuid.UUID
    uri: str
    name: str
    title: str | None
    description: str
    mime_type: str | None
    is_template: bool
    first_seen_at: datetime


class PromptArgumentOut(ApiModel):
    name: str
    description: str | None = None
    required: bool = False


class PromptOut(ApiModel):
    id: uuid.UUID
    name: str
    title: str | None
    description: str
    arguments: list[PromptArgumentOut]
    first_seen_at: datetime


class VersionOut(ApiModel):
    id: uuid.UUID
    server_version: str | None
    protocol_version: str | None
    catalog_hash: str
    tool_count: int
    resource_count: int
    prompt_count: int
    tools_added: list[str]
    tools_removed: list[str]
    tools_changed: list[str]
    created_at: datetime


class HealthBucketOut(ApiModel):
    start: datetime
    checks: int
    ok: int
    avg_latency_ms: int | None


class HealthHistoryOut(ApiModel):
    hours: int
    bucket_minutes: int
    uptime: float | None
    buckets: list[HealthBucketOut]


SecretKindName = Literal["header", "env"]


class SecretSet(ApiModel):
    kind: SecretKindName = "header"
    name: str = Field(min_length=1, max_length=128, description="Header or variable name.")
    value: str = Field(
        min_length=1,
        max_length=4096,
        description="Write-only. Encrypted at once and never returned by any endpoint.",
    )


class SecretOut(ApiModel):
    id: uuid.UUID
    kind: str
    name: str
    backend: str
    version: int
    created_at: datetime
    updated_at: datetime
