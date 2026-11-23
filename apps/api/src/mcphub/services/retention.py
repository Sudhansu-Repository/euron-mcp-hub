"""Retention: the call log keeps AUDIT_RETENTION_DAYS, health checks keep a week."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mcphub.core.logging import get_logger
from mcphub.repositories.calls import CallRepository
from mcphub.repositories.catalog import HistoryRepository
from mcphub.services.container import Container

log = get_logger("mcphub.retention")

HEALTH_RETENTION = timedelta(days=7)
BATCH = 5000


@dataclass(frozen=True, slots=True)
class Purged:
    calls: int
    checks: int


async def purge(container: Container, now: datetime | None = None) -> Purged:
    """Delete expired rows in batches, each in its own short transaction."""
    now = now or datetime.now(UTC)
    calls_before = now - timedelta(days=container.settings.audit_retention_days)
    checks_before = now - HEALTH_RETENTION
    calls = checks = 0
    while True:
        async with container.db.session() as session:
            deleted = await CallRepository(session).purge(calls_before, BATCH)
            await session.commit()
        calls += deleted
        if deleted < BATCH:
            break
    while True:
        async with container.db.session() as session:
            deleted = await HistoryRepository(session).purge_checks(checks_before, BATCH)
            await session.commit()
        checks += deleted
        if deleted < BATCH:
            break
    if calls or checks:
        log.info("retention_purged", calls=calls, health_checks=checks)
    return Purged(calls, checks)
