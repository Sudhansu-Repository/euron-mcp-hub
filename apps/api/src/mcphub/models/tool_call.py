from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from mcphub.db.base import Base, IdMixin

# Tool names are split into words ("tickets create ticket") so a prefix search for
# "ticket" finds "tickets.create_ticket". Arguments are stored already redacted, so
# searching them never reaches a value the policy hid.
SEARCH_EXPRESSION = (
    "to_tsvector('simple', translate(qualified_name, '._-', '   ') || ' ' || "
    "coalesce(client_name, '') || ' ' || coalesce(error_message, '') || ' ' || "
    "coalesce(arguments::text, ''))"
)


class ToolCall(IdMixin, Base):
    """One tool call through the gateway (or the playground): the audit log."""

    __tablename__ = "tool_calls"
    # The call log pages newest first by (created_at, id); filters narrow by one dimension.
    __table_args__ = (
        Index("ix_tool_calls_created_at_id", "created_at", "id"),
        Index("ix_tool_calls_client_id_created_at", "client_id", "created_at"),
        Index("ix_tool_calls_server_id_created_at", "server_id", "created_at"),
        Index("ix_tool_calls_status_created_at", "status", "created_at"),
        Index("ix_tool_calls_search", "search", postgresql_using="gin"),
    )

    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL")
    )
    client_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_keys.id", ondelete="SET NULL")
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servers.id", ondelete="SET NULL")
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_rules.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Snapshots, so the log still reads well after a client or server is deleted.
    client_name: Mapped[str] = mapped_column(String(120))
    server_slug: Mapped[str] = mapped_column(String(48))
    tool_name: Mapped[str] = mapped_column(String(128))
    qualified_name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(12), default="gateway")
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    arguments: Mapped[dict[str, Any] | None]
    result_bytes: Mapped[int | None]
    latency_ms: Mapped[int] = mapped_column(default=0)
    upstream_ms: Mapped[int | None]
    request_id: Mapped[str | None] = mapped_column(String(64))
    protocol_version: Mapped[str | None] = mapped_column(String(20))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    search: Mapped[Any] = mapped_column(TSVECTOR, Computed(SEARCH_EXPRESSION, persisted=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
