from __future__ import annotations

from sqlalchemy import func, select

from mcphub.models import AuditEvent
from mcphub.repositories.base import Repository


class AuditRepository(Repository):
    async def add(self, event: AuditEvent) -> None:
        self.session.add(event)

    async def page(
        self, *, target_type: str | None, limit: int, offset: int
    ) -> tuple[list[AuditEvent], int]:
        query = select(AuditEvent)
        if target_type:
            query = query.where(AuditEvent.target_type == target_type)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        result = await self.session.execute(
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total
