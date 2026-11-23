from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mcphub.db.base import Base, IdMixin, TimestampMixin


class Client(IdMixin, TimestampMixin, Base):
    """A caller of the gateway: an app, an agent or a person's IDE."""

    __tablename__ = "clients"

    slug: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")
    # What happens to a tool no rule matches. New clients deny: least privilege.
    default_effect: Mapped[str] = mapped_column(String(8), default="deny")
    # "." gives tickets.create_ticket; "__" gives tickets__create_ticket for model APIs
    # that reject dots in function names.
    tool_separator: Mapped[str] = mapped_column(String(4), default=".")
    rate_limit_per_minute: Mapped[int | None]
    record_arguments: Mapped[bool] = mapped_column(default=True)
    # Bumped on every rule change; part of the cached view, so stale views are refused.
    policy_version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    last_seen_at: Mapped[datetime | None]


class ClientKey(IdMixin, Base):
    """An API key of a client. Only an HMAC of the secret part is stored."""

    __tablename__ = "client_keys"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(16), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class PolicyRule(IdMixin, TimestampMixin, Base):
    """Allow or deny tools matching a pattern, with optional constraints and a rate limit."""

    __tablename__ = "policy_rules"
    __table_args__ = (UniqueConstraint("client_id", "pattern"),)

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(260))
    effect: Mapped[str] = mapped_column(String(8))
    constraints: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    rate_limit_per_minute: Mapped[int | None]
    # Argument paths recorded as "[redacted]" in the call log.
    redact: Mapped[list[str]] = mapped_column(default=list)
    description: Mapped[str] = mapped_column(String(300), default="")
