from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from mcphub.schemas.common import ApiModel


class SystemInfo(ApiModel):
    product_name: str
    version: str
    mcp_sdk_version: str
    gateway_url: str
    protocol_versions: list[str]
    secrets_backend: str
    stdio_commands: list[str]
    audit_retention_days: int
    health_interval_s: int
    needs_setup: bool


class ActivityOut(ApiModel):
    id: uuid.UUID
    actor_name: str
    action: str
    target_type: str
    target_id: str | None
    target_name: str | None
    details: dict[str, Any]
    created_at: datetime
