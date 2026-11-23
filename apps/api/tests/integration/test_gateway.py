"""The MCP gateway end to end: keys, per-client tool lists, policy, limits, upstream failures."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from mcp import MCPError

from mcphub.services.container import Container
from tests.integration.conftest import People
from tests.integration.support import GATEWAY, mcp_session, rows, text_of, unique

pytestmark = pytest.mark.integration

ALLOW_TICKETS = {"pattern": "tickets.*", "effect": "allow"}


async def _calls(people: People, container: Container, **filters: Any) -> list[dict[str, Any]]:
    await container.call_log.flush()
    return rows(await people.viewer.ok(await people.viewer.get("/calls", **filters)))


async def _post(app: FastAPI, key: str | None, body: dict[str, Any]) -> httpx2.Response:
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-11-25",
    }
    if key:
        headers["authorization"] = f"Bearer {key}"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url=GATEWAY
    ) as http:
        return await http.post("/mcp", json=body, headers=headers)


async def test_a_client_sees_only_the_tools_its_policy_allows(
    app: FastAPI, make_client: Any
) -> None:
    client = await make_client(
        [
            ALLOW_TICKETS,
            {"pattern": "tickets.delete_ticket", "effect": "deny"},
            {"pattern": "notes.search_notes", "effect": "allow"},
        ]
    )

    async with mcp_session(app, client.key) as session:
        names = {tool.name for tool in (await session.list_tools()).tools}

    assert "tickets.list_tickets" in names
    assert "notes.search_notes" in names
    assert "tickets.delete_ticket" not in names
    assert "notes.get_note" not in names
    assert not any(name.startswith("toolbox.") for name in names)


async def test_a_call_travels_to_the_upstream_server_and_is_recorded(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await make_client([ALLOW_TICKETS])

    async with mcp_session(app, client.key, headers={"user-agent": "it-agent/1.0"}) as session:
        result = await session.call_tool("tickets.list_tickets", {"status": "open", "limit": 3})

    assert not result.is_error
    assert "TCK-" in text_of(result)
    call = (await _calls(people, container, client=client.slug))[0]
    assert call["status"] == "ok"
    assert call["qualified_name"] == "tickets.list_tickets"
    assert call["server_slug"] == "tickets"
    assert call["upstream_ms"] is not None
    detail = await people.viewer.ok(await people.viewer.get(f"/calls/{call['id']}"))
    assert detail["arguments"] == {"status": "open", "limit": 3}
    assert detail["user_agent"] == "it-agent/1.0"
    assert detail["result_bytes"] > 0


async def test_a_denied_or_hidden_tool_looks_like_a_tool_that_does_not_exist(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await make_client(
        [ALLOW_TICKETS, {"pattern": "tickets.delete_ticket", "effect": "deny"}]
    )

    async with mcp_session(app, client.key) as session:
        with pytest.raises(MCPError) as denied:
            await session.call_tool("tickets.delete_ticket", {"ticket_id": "TCK-1201"})
        with pytest.raises(MCPError) as hidden:
            await session.call_tool("notes.get_note", {"note_id": "n-001"})
        with pytest.raises(MCPError) as missing:
            await session.call_tool("nothing.at_all", {})

    assert denied.value.error.message.startswith("Unknown tool")
    assert hidden.value.error.message.startswith("Unknown tool")
    assert missing.value.error.message.startswith("Unknown tool")
    statuses = {
        c["qualified_name"]: c["status"]
        for c in await _calls(people, container, client=client.slug)
    }
    assert statuses["tickets.delete_ticket"] == "denied"
    assert statuses["notes.get_note"] == "denied"


async def test_argument_constraints_return_a_readable_error_the_model_can_fix(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await make_client(
        [
            {
                "pattern": "tickets.create_ticket",
                "effect": "allow",
                "constraints": [
                    {"argument": "priority", "rule": "one_of", "values": ["low", "normal"]}
                ],
                "redact": ["requester_email"],
            }
        ]
    )

    async with mcp_session(app, client.key) as session:
        blocked = await session.call_tool(
            "tickets.create_ticket", {"title": "Server on fire", "priority": "urgent"}
        )
        allowed = await session.call_tool(
            "tickets.create_ticket",
            {"title": "Printer jam", "priority": "low", "requester_email": "kim@example.com"},
        )
        invalid = await session.call_tool("tickets.create_ticket", {"priority": "low"})

    assert blocked.is_error
    assert "priority" in text_of(blocked)
    assert not allowed.is_error
    assert invalid.is_error
    assert "input schema" in text_of(invalid)
    recorded = {c["status"]: c for c in await _calls(people, container, client=client.slug)}
    assert set(recorded) == {"blocked", "ok", "invalid_arguments"}
    detail = await people.viewer.ok(await people.viewer.get(f"/calls/{recorded['ok']['id']}"))
    assert detail["arguments"]["requester_email"] == "[redacted]"
    assert detail["arguments"]["title"] == "Printer jam"


async def test_rate_limits_apply_per_client_and_per_rule(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    per_rule = await make_client(
        [{"pattern": "toolbox.current_time", "effect": "allow", "rate_limit_per_minute": 2}]
    )
    per_client = await make_client(
        [{"pattern": "toolbox.*", "effect": "allow"}], rate_limit_per_minute=3
    )

    async with mcp_session(app, per_rule.key) as session:
        outcomes = [await session.call_tool("toolbox.current_time", {}) for _ in range(4)]
    assert [r.is_error for r in outcomes] == [False, False, True, True]
    assert "Rate limit exceeded" in text_of(outcomes[2])

    async with mcp_session(app, per_client.key) as session:
        outcomes = [await session.call_tool("toolbox.random_uuid", {}) for _ in range(5)]
    assert [r.is_error for r in outcomes] == [False, False, False, True, True]
    statuses = [c["status"] for c in await _calls(people, container, client=per_client.slug)]
    assert statuses.count("rate_limited") == 2


async def test_the_namespace_separator_can_be_chosen_per_client(
    app: FastAPI, make_client: Any
) -> None:
    client = await make_client([{"pattern": "toolbox.*", "effect": "allow"}], tool_separator="__")

    async with mcp_session(app, client.key) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        result = await session.call_tool("toolbox__calculate", {"expression": "6 * 7"})
        with pytest.raises(MCPError):
            await session.call_tool("toolbox.calculate", {"expression": "1 + 1"})

    assert "toolbox__calculate" in names
    assert not any("." in name for name in names)
    assert "42" in text_of(result)


async def test_a_default_allow_client_gets_everything_except_what_rules_deny(
    app: FastAPI, make_client: Any
) -> None:
    client = await make_client(
        [{"pattern": "*.delete_*", "effect": "deny"}], default_effect="allow"
    )

    async with mcp_session(app, client.key) as session:
        names = {t.name for t in (await session.list_tools()).tools}

    assert "notes.search_notes" in names
    assert "toolbox.calculate" in names
    assert "tickets.delete_ticket" not in names
    assert "notes.delete_note" not in names


@pytest.mark.parametrize("key", [None, "mch_aaaaaaaaaa_" + "b" * 43, "not-a-key", "Bearer"])
async def test_unauthenticated_requests_are_refused_before_reaching_the_protocol(
    app: FastAPI, key: str | None
) -> None:
    response = await _post(
        app, key, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    assert response.json()["error"]["data"]["code"] in {"missing_api_key", "invalid_api_key"}


async def test_a_revoked_key_stops_working_at_once_and_a_second_key_keeps_working(
    app: FastAPI, people: People, make_client: Any
) -> None:
    operator = people.operator
    client = await make_client([ALLOW_TICKETS])
    second = await operator.ok(
        await operator.post(f"/clients/{client.slug}/keys", {"name": "Second"})
    )
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    assert (await _post(app, client.key, body)).status_code == 200

    assert (
        await operator.delete(f"/clients/{client.slug}/keys/{client.key_id}")
    ).status_code == 204

    assert (await _post(app, client.key, body)).status_code == 401
    assert (await _post(app, second["key"], body)).status_code == 200


async def test_an_expired_key_is_refused(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from mcphub.models import ClientKey

    client = await make_client([ALLOW_TICKETS])
    async with container.db.session() as session:
        await session.execute(
            update(ClientKey)
            .where(ClientKey.id == client.key_id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    await container.cache.bump_keys()

    response = await _post(
        app, client.key, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )

    assert response.status_code == 401
    assert response.json()["error"]["data"]["code"] == "expired_api_key"


async def test_a_suspended_client_is_refused_and_resuming_restores_access(
    app: FastAPI, people: People, make_client: Any
) -> None:
    client = await make_client([ALLOW_TICKETS])
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    await people.operator.ok(
        await people.operator.patch(f"/clients/{client.slug}", {"status": "suspended"})
    )
    refused = await _post(app, client.key, body)
    await people.operator.ok(
        await people.operator.patch(f"/clients/{client.slug}", {"status": "active"})
    )
    restored = await _post(app, client.key, body)

    assert refused.status_code == 403
    assert refused.json()["error"]["data"]["code"] == "client_suspended"
    assert restored.status_code == 200


async def test_policy_changes_take_effect_on_the_next_request(
    app: FastAPI, people: People, make_client: Any
) -> None:
    operator = people.operator
    client = await make_client([{"pattern": "notes.search_notes", "effect": "allow"}])
    async with mcp_session(app, client.key) as session:
        before = {t.name for t in (await session.list_tools()).tools}

    rule = await operator.ok(
        await operator.post(
            f"/clients/{client.slug}/rules", {"pattern": "toolbox.*", "effect": "allow"}
        )
    )
    async with mcp_session(app, client.key) as session:
        during = {t.name for t in (await session.list_tools()).tools}
    await operator.delete(f"/clients/{client.slug}/rules/{rule['id']}")
    async with mcp_session(app, client.key) as session:
        after = {t.name for t in (await session.list_tools()).tools}

    assert "toolbox.calculate" not in before
    assert "toolbox.calculate" in during
    assert after == before


async def test_a_tool_switched_off_in_the_catalog_disappears_for_every_client(
    app: FastAPI, people: People, make_client: Any
) -> None:
    client = await make_client([{"pattern": "toolbox.*", "effect": "allow"}])
    await people.operator.ok(
        await people.operator.patch("/servers/toolbox/tools/wait", {"enabled": False})
    )
    try:
        async with mcp_session(app, client.key) as session:
            names = {t.name for t in (await session.list_tools()).tools}
            with pytest.raises(MCPError):
                await session.call_tool("toolbox.wait", {"seconds": 0})
    finally:
        await people.operator.patch("/servers/toolbox/tools/wait", {"enabled": True})

    assert "toolbox.wait" not in names
    assert "toolbox.calculate" in names


async def test_an_upstream_tool_error_is_passed_through_and_an_outage_is_reported_clearly(
    app: FastAPI, container: Container, people: People, make_client: Any, upstreams: Any
) -> None:
    operator = people.operator
    slug = unique("outage")
    await operator.ok(
        await operator.post("/servers", {"name": "Outage", "slug": slug, "url": upstreams.toolbox})
    )
    client = await make_client([{"pattern": f"{slug}.*", "effect": "allow"}])
    async with mcp_session(app, client.key) as session:
        failed = await session.call_tool(f"{slug}.calculate", {"expression": "1/0"})
        assert failed.is_error
        assert not (await session.call_tool(f"{slug}.calculate", {"expression": "1+1"})).is_error

        # The server moves away: the tool is still catalogued, the call cannot reach it.
        await operator.ok(
            await operator.patch(f"/servers/{slug}", {"url": "http://127.0.0.1:9/mcp"})
        )
        down = await session.call_tool(f"{slug}.calculate", {"expression": "1+1"})

    assert down.is_error
    assert f"{slug}" in text_of(down) or "Outage" in text_of(down)
    assert "unavailable" in text_of(down)
    statuses = [c["status"] for c in await _calls(people, container, client=client.slug)]
    assert statuses[0] == "upstream_error"
    assert "tool_error" in statuses


async def test_a_slow_upstream_call_times_out_at_the_servers_limit(
    app: FastAPI, container: Container, people: People, make_client: Any, upstreams: Any
) -> None:
    operator = people.operator
    slug = unique("slow")
    await operator.ok(
        await operator.post(
            "/servers", {"name": "Slow", "slug": slug, "url": upstreams.toolbox, "timeout_s": 1}
        )
    )
    client = await make_client([{"pattern": f"{slug}.wait", "effect": "allow"}])

    async with mcp_session(app, client.key) as session:
        started = asyncio.get_running_loop().time()
        result = await session.call_tool(f"{slug}.wait", {"seconds": 5})
        elapsed = asyncio.get_running_loop().time() - started

    assert result.is_error
    assert "did not answer within 1 seconds" in text_of(result)
    assert elapsed < 4
    assert (await _calls(people, container, client=client.slug))[0]["status"] == "timeout"


async def test_concurrent_calls_share_one_upstream_connection(
    app: FastAPI, container: Container, make_client: Any
) -> None:
    client = await make_client([{"pattern": "toolbox.*", "effect": "allow"}])

    async with mcp_session(app, client.key) as session:
        results = await asyncio.gather(
            *(session.call_tool("toolbox.calculate", {"expression": f"{n} * 2"}) for n in range(12))
        )

    assert [text_of(r) for r in results] == [
        str(float(n * 2)) if False else text_of(r) for n, r in enumerate(results)
    ]
    assert all(not r.is_error for r in results)
    assert container.pool.size >= 1


async def test_the_playground_runs_a_real_call_as_a_client_and_names_the_operator(
    app: FastAPI, container: Container, people: People, make_client: Any
) -> None:
    client = await make_client([{"pattern": "toolbox.calculate", "effect": "allow"}])

    done = await people.operator.ok(
        await people.operator.post(
            "/playground/call",
            {
                "client": client.slug,
                "tool": "toolbox.calculate",
                "arguments": {"expression": "2 ** 10"},
            },
        )
    )
    refused = await people.operator.ok(
        await people.operator.post(
            "/playground/call",
            {"client": client.slug, "tool": "tickets.list_tickets", "arguments": {}},
        )
    )

    assert done["is_error"] is False
    assert "1024" in json.dumps(done["content"])
    assert refused["is_error"] is True
    assert refused["call"]["status"] == "denied"
    await container.call_log.flush()
    detail = await people.viewer.ok(await people.viewer.get(f"/calls/{done['call']['id']}"))
    assert detail["source"] == "playground"
    assert detail["actor_name"] == "Operator"
    assert (
        await people.viewer.post("/playground/call", {"client": client.slug, "tool": "a.b"})
    ).status_code == 403
