"""Administrative activity: who changed which server, secret, client, rule, key or user."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.models import AuditEvent
from mcphub.repositories.audit import AuditRepository
from mcphub.services.actor import Actor


async def record(
    session: AsyncSession,
    actor: Actor,
    *,
    action: str,
    target_type: str,
    target_id: object | None = None,
    target_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an event to the caller's transaction, so it commits with the change it records."""
    await AuditRepository(session).add(
        AuditEvent(
            actor_user_id=actor.user_id,
            actor_name=actor.name,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            target_name=target_name,
            details=details or {},
        )
    )


async def activity(
    session: AsyncSession, *, target_type: str | None, limit: int, offset: int
) -> tuple[list[AuditEvent], int]:
    return await AuditRepository(session).page(target_type=target_type, limit=limit, offset=offset)
