from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mcphub.db.base import Base, IdMixin


class AuditEvent(IdMixin, Base):
    """An administrative change: servers, secrets, tools, clients, keys, rules and users."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Snapshot of who did it ("system" for the worker), readable after the user is gone.
    actor_name: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    target_name: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
