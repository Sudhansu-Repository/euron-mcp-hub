"""The audit log: what is recorded, how it is filtered, scrubbed, retained and exported."""

from __future__ import annotations

import contextlib
import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from mcp import MCPError
from sqlalchemy import update

from mcphub.models import ToolCall
from mcphub.services import retention
from mcphub.services.container import Container
from tests.integration.conftest import People
from tests.integration.support import mcp_session, rows, unique

pytestmark = pytest.mark.integration


async def _traffic(app: FastAPI, container: Container, make_client: Any) -> Any:
    """A client with a mixed history: ok, denied, blocked and a tool error."""
    client = await make_client(
        [
            {"pattern": "toolbox.*", "effect": "allow"},
            {
                "pattern": "tickets.create_ticket",
                "effect": "allow",
                "constraints": [{"argument": "priority", "rule": "one_of", "values": ["low"]}],
            },
        ]
    )
    async with mcp_session(app, client.key) as session:
        await session.call_tool("toolbox.calculate", {"expression": "21 * 2"})
        await session.call_tool("toolbox.calculate", {"expression": "1/0"})
        await session.call_tool(
            "tickets.create_ticket", {"title": "Printer jam on floor 3", "priority": "urgent"}
        )
        # The denial is a protocol error; the call log has it.
        with contextlib.suppress(MCPError):
            await session.call_tool("notes.delete_note", {"note_id": "n-001"})
    await container.call_log.flush()
    return client


async def test_the_call_log_filters_by_client_status_tool_and_text(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await _traffic(app, container, make_client)
    viewer = people.viewer

    everything = await viewer.ok(await viewer.get("/calls", client=client.slug, count="true"))
    assert everything["total"] == 4
    assert {c["status"] for c in everything["items"]} == {"ok", "tool_error", "blocked", "denied"}

    failed = rows(await viewer.ok(await viewer.get("/calls", client=client.slug, status="blocked")))
    assert [c["qualified_name"] for c in failed] == ["tickets.create_ticket"]
    two = await viewer.ok(
        await viewer.request(
            "GET",
            "/calls",
            params=[("client", client.slug), ("status", "ok"), ("status", "denied")],
        )
    )
    assert {c["status"] for c in two["items"]} == {"ok", "denied"}

    by_tool = rows(
        await viewer.ok(await viewer.get("/calls", client=client.slug, tool="toolbox.calculate"))
    )
    assert len(by_tool) == 2
    by_server = rows(
        await viewer.ok(await viewer.get("/calls", client=client.slug, server="toolbox"))
    )
    assert len(by_server) == 2
    by_text = rows(await viewer.ok(await viewer.get("/calls", client=client.slug, q="printer")))
    assert [c["status"] for c in by_text] == ["blocked"]
    nothing = rows(await viewer.ok(await viewer.get("/calls", client="no-such-client")))
    assert nothing == []


async def test_the_call_log_pages_with_a_keyset_cursor(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await _traffic(app, container, make_client)
    viewer = people.viewer

    first = await viewer.ok(await viewer.get("/calls", client=client.slug, limit=3))
    second = await viewer.ok(
        await viewer.get("/calls", client=client.slug, limit=3, cursor=first["next_cursor"])
    )

    assert len(first["items"]) == 3
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    ids = [c["id"] for c in first["items"] + second["items"]]
    assert len(set(ids)) == 4
    stamps = [c["created_at"] for c in first["items"] + second["items"]]
    assert stamps == sorted(stamps, reverse=True)


async def test_call_details_keep_redacted_arguments_and_hide_credentials(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await make_client([{"pattern": "notes.*", "effect": "allow"}])
    async with mcp_session(app, client.key) as session:
        await session.call_tool(
            "notes.search_notes",
            {"query": "use Bearer abcdefghijklmnop123 and mch_aaaaaaaaaa_xyz12345678 to log in"},
        )
        await session.call_tool("notes.get_note", {"note_id": "n-001", "api_key": "sk-live-1234"})
    await container.call_log.flush()

    calls = rows(await people.viewer.ok(await people.viewer.get("/calls", client=client.slug)))
    details = [await people.viewer.ok(await people.viewer.get(f"/calls/{c['id']}")) for c in calls]
    dumped = str(details)

    assert "abcdefghijklmnop123" not in dumped
    assert "mch_aaaaaaaaaa_xyz12345678" not in dumped
    assert "sk-live-1234" not in dumped
    assert "[redacted]" in dumped


async def test_a_client_can_turn_off_argument_recording(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await make_client(
        [{"pattern": "toolbox.calculate", "effect": "allow"}], record_arguments=False
    )
    async with mcp_session(app, client.key) as session:
        await session.call_tool("toolbox.calculate", {"expression": "2 + 2"})
    await container.call_log.flush()

    call = rows(await people.viewer.ok(await people.viewer.get("/calls", client=client.slug)))[0]
    detail = await people.viewer.ok(await people.viewer.get(f"/calls/{call['id']}"))

    assert detail["arguments"] is None
    assert detail["status"] == "ok"


async def test_calls_export_as_csv_with_the_same_filters(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await _traffic(app, container, make_client)

    response = await people.viewer.get("/calls/export", client=client.slug, status="ok")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    table = list(csv.DictReader(io.StringIO(response.text)))
    assert len(table) == 1
    assert table[0]["qualified_name"] == "toolbox.calculate"
    assert table[0]["client_name"].startswith("Client c-")


async def test_calls_past_retention_are_purged_and_recent_ones_kept(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await _traffic(app, container, make_client)
    recent = rows(await people.viewer.ok(await people.viewer.get("/calls", client=client.slug)))
    old_ids = [c["id"] for c in recent[:2]]
    async with container.db.session() as session:
        await session.execute(
            update(ToolCall)
            .where(ToolCall.id.in_(old_ids))
            .values(created_at=datetime.now(UTC) - timedelta(days=400))
        )
        await session.commit()

    purged = await retention.purge(container)

    assert purged.calls >= 2
    left = rows(await people.viewer.ok(await people.viewer.get("/calls", client=client.slug)))
    assert {c["id"] for c in left} == {c["id"] for c in recent[2:]}


async def test_the_overview_aggregates_the_log_and_the_catalog(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    await _traffic(app, container, make_client)

    overview = await people.viewer.ok(await people.viewer.get("/stats/overview", range="24h"))

    totals = overview["totals"]
    assert totals["calls"] >= 4
    assert totals["ok"] >= 1
    assert totals["refused"] >= 2
    assert totals["p95_ms"] >= totals["p50_ms"]
    assert overview["servers"]["total"] >= 3
    assert overview["statuses"]["blocked"] >= 1
    assert overview["top_tools"][0]["calls"] >= 1
    assert len(overview["series"]) > 1
    assert (await people.viewer.get("/stats/overview", range="1y")).status_code == 422


async def test_admin_activity_records_who_changed_what_without_secret_values(
    people: People, make_client: Any
) -> None:
    client = await make_client([{"pattern": "notes.*", "effect": "allow"}])
    await people.operator.ok(
        await people.operator.patch(f"/clients/{client.slug}", {"status": "suspended"})
    )

    activity = await people.viewer.ok(await people.viewer.get("/activity", limit=50))

    mine = [a for a in activity["items"] if a["target_name"] == client.slug]
    actions = {a["action"] for a in mine}
    assert {"client.created", "client.suspended"} <= actions
    assert {a["actor_name"] for a in mine} == {"Operator"}
    assert "mch_" not in str(activity)


async def test_the_call_log_is_visible_to_viewers_only_when_signed_in(people: People) -> None:
    anonymous = await people.viewer.http.request(
        "GET", "/api/v1/calls", headers={"authorization": ""}
    )

    assert anonymous.status_code == 401
    assert (await people.viewer.get(f"/calls/{unique('x')}")).status_code == 422
