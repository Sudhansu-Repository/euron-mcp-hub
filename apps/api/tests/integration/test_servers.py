"""The server registry: registration, discovery, health, version history, egress policy."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from tests.integration.conftest import TICKETS_TOKEN, People
from tests.integration.support import Upstreams, rows, unique

pytestmark = pytest.mark.integration


async def test_registering_a_server_discovers_its_tools_resources_and_prompts(
    people: People, hub: dict[str, Any]
) -> None:
    server = await people.viewer.ok(await people.viewer.get("/servers/notes"))

    assert server["health"] == "healthy"
    assert server["server_name"]
    assert server["tool_count"] >= 4
    assert server["prompt_count"] >= 1
    tools = await people.viewer.ok(await people.viewer.get("/servers/notes/tools"))
    assert {"search_notes", "get_note"} <= {t["name"] for t in rows(tools)}
    first = rows(tools)[0]
    assert first["qualified_name"] == f"notes.{first['name']}"
    assert first["input_schema"]["type"] == "object"
    assert len(first["fingerprint"]) == 64


async def test_a_server_that_needs_a_token_reports_why_it_failed_until_the_secret_is_set(
    people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("desk")
    created = await operator.ok(
        await operator.post("/servers", {"name": "Desk", "slug": slug, "url": upstreams.tickets_v1})
    )
    assert created["health"] in {"unknown", "down"}
    assert "credentials" in (created["discovery_error"] or created["last_error"] or "")

    await operator.ok(
        await operator.put(
            f"/servers/{slug}/secrets",
            {"kind": "header", "name": "Authorization", "value": f"Bearer {TICKETS_TOKEN}"},
        )
    )
    refreshed = await operator.ok(await operator.post(f"/servers/{slug}/refresh"))
    assert refreshed["ok"] is True
    assert refreshed["server"]["tool_count"] >= 5


async def test_a_changed_catalog_is_recorded_as_a_version_with_its_diff(
    people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("versions")
    await operator.ok(
        await operator.post(
            "/servers",
            {"name": "Versions", "slug": slug, "url": upstreams.tickets_v1, "discover": False},
        )
    )
    await operator.ok(
        await operator.put(
            f"/servers/{slug}/secrets",
            {"kind": "header", "name": "Authorization", "value": f"Bearer {TICKETS_TOKEN}"},
        )
    )
    first = await operator.ok(await operator.post(f"/servers/{slug}/refresh"))
    assert first["new_version"] is True

    await operator.ok(await operator.patch(f"/servers/{slug}", {"url": upstreams.tickets}))
    second = await operator.ok(await operator.post(f"/servers/{slug}/refresh"))

    assert second["new_version"] is True
    assert "add_comment" in second["added"]
    versions = await operator.ok(await operator.get(f"/servers/{slug}/versions"))
    items = rows(versions)
    assert len(items) == 2
    assert items[0]["tools_added"] == second["added"]

    # Nothing changed since: a rediscovery records no new version.
    again = await operator.ok(await operator.post(f"/servers/{slug}/refresh"))
    assert again["new_version"] is False


async def test_health_checks_record_history_and_failures_mark_a_server_down(
    people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("flaky")
    await operator.ok(
        await operator.post("/servers", {"name": "Flaky", "slug": slug, "url": upstreams.toolbox})
    )
    ok = await operator.ok(await operator.post(f"/servers/{slug}/check"))
    assert ok["ok"] is True
    assert ok["latency_ms"] is not None

    # Point it somewhere nothing listens: three failed checks in a row mark it down.
    await operator.ok(await operator.patch(f"/servers/{slug}", {"url": "http://127.0.0.1:9/mcp"}))
    states = []
    for _ in range(3):
        failed = await operator.ok(await operator.post(f"/servers/{slug}/check"))
        assert failed["ok"] is False
        states.append(failed["health"])
    assert states[-1] == "down"
    assert states[0] != "healthy"

    history = await operator.ok(await operator.get(f"/servers/{slug}/health"))
    assert sum(bucket["checks"] for bucket in history["buckets"]) >= 4
    assert history["uptime"] is not None
    assert history["uptime"] < 1


@pytest.mark.parametrize(
    ("url", "needle"),
    [
        ("http://169.254.169.254/latest/meta-data/", "metadata"),
        ("http://metadata.google.internal/mcp", "metadata"),
        ("http://10.0.0.5:9000/mcp", "private or local"),
        ("http://192.168.1.10/mcp", "private or local"),
        ("http://localhost:9000/mcp", "private or local"),
        ("file:///etc/passwd", "http"),
        ("https://user:pw@example.com/mcp", "credentials"),
    ],
)
async def test_the_egress_policy_refuses_dangerous_upstream_urls(
    people: People, url: str, needle: str
) -> None:
    response = await people.operator.post(
        "/servers", {"name": "Bad", "slug": unique("bad"), "url": url}
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "target_refused"
    assert needle in error["message"]


async def test_the_egress_policy_is_enforced_again_when_a_server_is_edited(
    people: People, hub: dict[str, Any]
) -> None:
    response = await people.operator.patch(
        "/servers/toolbox", {"url": "http://169.254.169.254/mcp"}
    )

    assert response.status_code == 422
    unchanged = await people.operator.ok(await people.operator.get("/servers/toolbox"))
    assert "169.254" not in unchanged["url"]


async def test_stdio_servers_need_an_allow_listed_command(people: People) -> None:
    operator = people.operator
    refused = await operator.post(
        "/servers",
        {"name": "Shell", "slug": unique("sh"), "transport": "stdio", "command": "/bin/sh"},
    )
    assert refused.status_code == 422
    assert "not an allowed stdio command" in refused.json()["error"]["message"]

    slug = unique("wx")
    created = await operator.ok(
        await operator.post(
            "/servers",
            {
                "name": "Weather over stdio",
                "slug": slug,
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "mcphub.demo.servers", "weather"],
                "discover": False,
            },
        )
    )
    await operator.ok(
        await operator.put(
            f"/servers/{slug}/secrets",
            {"kind": "env", "name": "WEATHER_API_KEY", "value": "k" * 12},
        )
    )
    ok = await operator.ok(await operator.post(f"/servers/{slug}/refresh"))
    assert ok["ok"] is True, ok
    assert created["transport"] == "stdio"
    tools = await operator.ok(await operator.get(f"/servers/{slug}/tools"))
    assert {"current_weather", "forecast"} <= {t["name"] for t in rows(tools)}


async def test_a_tool_can_be_taken_out_of_the_gateway_and_put_back(
    people: People, hub: dict[str, Any]
) -> None:
    operator = people.operator
    off = await operator.ok(
        await operator.patch("/servers/toolbox/tools/random_uuid", {"enabled": False})
    )
    assert off["enabled"] is False
    on = await operator.ok(
        await operator.patch("/servers/toolbox/tools/random_uuid", {"enabled": True})
    )
    assert on["enabled"] is True


async def test_only_operators_change_the_catalog_and_viewers_read_it(
    people: People, hub: dict[str, Any], upstreams: Upstreams
) -> None:
    body = {"name": "Nope", "slug": unique("nope"), "url": upstreams.notes}

    assert (await people.viewer.post("/servers", body)).status_code == 403
    assert (await people.viewer.post("/servers/notes/refresh")).status_code == 403
    assert (await people.viewer.get("/servers/notes")).status_code == 200
    anonymous = await people.viewer.http.request(
        "GET", "/api/v1/servers", headers={"authorization": ""}
    )
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "unauthorized"


async def test_slugs_are_unique_and_validated(people: People, upstreams: Upstreams) -> None:
    operator = people.operator
    duplicate = await operator.post(
        "/servers", {"name": "Again", "slug": "notes", "url": upstreams.notes}
    )
    assert duplicate.status_code == 409
    invalid = await operator.post(
        "/servers", {"name": "Dots", "slug": "has.dots", "url": upstreams.notes}
    )
    assert invalid.status_code == 422


async def test_removing_a_server_removes_its_tools_and_secrets(
    people: People, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("gone")
    await operator.ok(
        await operator.post("/servers", {"name": "Gone", "slug": slug, "url": upstreams.toolbox})
    )
    await operator.ok(
        await operator.put(
            f"/servers/{slug}/secrets", {"kind": "header", "name": "X-Team", "value": "gone-soon-1"}
        )
    )

    assert (await operator.delete(f"/servers/{slug}")).status_code == 204

    assert (await operator.get(f"/servers/{slug}")).status_code == 404
    search = await operator.ok(await operator.get("/tools", q=slug))
    assert all(t["server_slug"] != slug for t in rows(search))


async def test_the_catalog_lists_filters_and_searches(people: People, hub: dict[str, Any]) -> None:
    viewer = people.viewer
    tagged = await viewer.ok(await viewer.get("/servers", tag="demo"))
    assert {"notes", "toolbox"} <= {s["slug"] for s in tagged["items"]}
    assert tagged["total"] >= 2

    found = await viewer.ok(await viewer.get("/tools", q="convert"))
    items = rows(found)
    assert items
    assert all("convert" in (t["name"] + t["description"]).lower() for t in items)

    page = await viewer.ok(await viewer.get("/servers", limit=1, offset=1))
    assert len(page["items"]) == 1
    assert page["limit"] == 1
