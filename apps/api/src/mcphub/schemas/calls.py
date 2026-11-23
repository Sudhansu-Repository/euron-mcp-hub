from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from mcphub.schemas.common import ApiModel


class CallOut(ApiModel):
    id: uuid.UUID
    created_at: datetime
    client_id: uuid.UUID | None
    client_name: str
    server_id: uuid.UUID | None
    server_slug: str
    tool_name: str
    qualified_name: str
    source: str
    status: str
    error_message: str | None
    latency_ms: int
    upstream_ms: int | None


class CallDetailOut(CallOut):
    client_key_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    arguments: dict[str, Any] | None
    result_bytes: int | None
    request_id: str | None
    protocol_version: str | None
    user_agent: str | None
    actor_name: str | None = None


class CallPage(ApiModel):
    items: list[CallOut]
    next_cursor: str | None = None
    total: int | None = Field(default=None, description="Only computed when `count=true`.")


class PlaygroundCall(ApiModel):
    client: str = Field(description="Client slug: the call runs under its policy.")
    tool: str = Field(min_length=3, max_length=200, description="tickets.list_tickets")
    arguments: dict[str, Any] = Field(default_factory=dict)


class PlaygroundResultOut(ApiModel):
    call: CallOut
    is_error: bool
    error: str | None = Field(
        default=None, description="A protocol error, such as an unknown tool."
    )
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: Any = None
