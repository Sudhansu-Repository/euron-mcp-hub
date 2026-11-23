"""The scheduler worker, its leader lease, and the upstream pool's reaper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI

from mcphub.services.container import Container
from mcphub.worker import LEASE_KEY, Scheduler
from tests.integration.conftest import People
from tests.integration.support import Upstreams, mcp_session, unique

pytestmark = pytest.mark.integration


@pytest.fixture
async def scheduler(container: Container) -> Any:
    await container.redis.delete(LEASE_KEY)
    return Scheduler(container)


async def test_a_round_checks_due_servers_and_records_their_health(
    scheduler: Scheduler, people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("sched")
    await operator.ok(
        await operator.post(
            "/servers",
            {"name": "Scheduled", "slug": slug, "url": upstreams.toolbox, "discover": False},
        )
    )
    assert (await operator.ok(await operator.get(f"/servers/{slug}")))["last_check_at"] is None

    await scheduler.round()

    server = await operator.ok(await operator.get(f"/servers/{slug}"))
    assert server["health"] == "healthy"
    assert server["last_check_at"] is not None
    assert server["tool_count"] >= 5, "a never-discovered server is discovered by the round"
    history = await operator.ok(await operator.get(f"/servers/{slug}/health"))
    assert sum(b["checks"] for b in history["buckets"]) >= 1


async def test_a_recovered_server_is_rediscovered_at_once(
    scheduler: Scheduler, container: Container, people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("heal")
    await operator.ok(
        await operator.post("/servers", {"name": "Heal", "slug": slug, "url": upstreams.notes})
    )
    # Break it: three failed checks mark it down.
    await operator.ok(await operator.patch(f"/servers/{slug}", {"url": "http://127.0.0.1:9/mcp"}))
    for _ in range(3):
        await operator.post(f"/servers/{slug}/check")
    assert (await operator.ok(await operator.get(f"/servers/{slug}")))["health"] == "down"
    assert (await operator.ok(await operator.get(f"/servers/{slug}")))["tool_count"] >= 4

    # Fix it, and let the scheduler find out.
    await operator.ok(await operator.patch(f"/servers/{slug}", {"url": upstreams.notes}))
    await scheduler.round(
        datetime.now(UTC) + timedelta(seconds=container.settings.health_interval_s + 1)
    )

    server = await operator.ok(await operator.get(f"/servers/{slug}"))
    assert server["health"] == "healthy"
    assert server["consecutive_failures"] == 0
    assert server["last_discovered_at"] is not None


async def test_a_disabled_server_is_not_checked(
    scheduler: Scheduler, people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("off")
    await operator.ok(
        await operator.post(
            "/servers",
            {
                "name": "Off",
                "slug": slug,
                "url": upstreams.toolbox,
                "enabled": False,
                "discover": False,
            },
        )
    )

    await scheduler.round()

    assert (await operator.ok(await operator.get(f"/servers/{slug}")))["last_check_at"] is None


async def test_only_one_worker_leads_and_a_standby_takes_over_after_release(
    container: Container,
) -> None:
    await container.redis.delete(LEASE_KEY)
    first, second = Scheduler(container), Scheduler(container)

    assert await first._lead() is True
    assert await second._lead() is False
    assert await first._lead() is True, "the leader renews its own lease"

    await first._release()
    assert await second._lead() is True
    # A worker that never held the lease cannot release someone else's.
    await first._release()
    assert await container.redis.get(LEASE_KEY) is not None
    await second._release()


async def test_the_pool_reaper_closes_idle_connections_and_replaces_broken_ones(
    app: FastAPI, container: Container, make_client: Any
) -> None:
    client = await make_client([{"pattern": "toolbox.*", "effect": "allow"}])
    async with mcp_session(app, client.key) as session:
        await session.call_tool("toolbox.random_uuid", {})
    assert container.pool.size >= 1

    for connection in container.pool._connections.values():
        connection.last_used -= container.settings.upstream_idle_timeout_s + 60
    await container.pool.reap()
    assert container.pool.size == 0

    async with mcp_session(app, client.key) as session:
        first = await session.call_tool("toolbox.random_uuid", {})
        for connection in container.pool._connections.values():
            connection.broken = True
        second = await session.call_tool("toolbox.random_uuid", {})
    assert not first.is_error
    assert not second.is_error
    assert container.pool.size >= 1


async def test_retention_runs_from_the_scheduler_once_an_hour(
    scheduler: Scheduler, container: Container
) -> None:
    now = datetime.now(UTC)
    await scheduler.round(now)
    assert scheduler.last_retention == now

    later = now + timedelta(minutes=10)
    await scheduler.round(later)
    assert scheduler.last_retention == now, "not again within the hour"
    await scheduler.round(now + timedelta(hours=1, seconds=1))
    assert scheduler.last_retention == now + timedelta(hours=1, seconds=1)
