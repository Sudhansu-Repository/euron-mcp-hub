"""Clients, their API keys and tool permissions, and who may manage them."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.conftest import People
from tests.integration.support import rows, unique

pytestmark = pytest.mark.integration


async def test_creating_a_client_returns_its_key_once(people: People) -> None:
    operator = people.operator
    created = await operator.ok(
        await operator.post(
            "/clients",
            {"name": "Support copilot", "slug": unique("copilot"), "key_name": "Production"},
        )
    )

    key = created["key"]
    assert key["key"].startswith("mch_")
    assert key["prefix"] in key["key"]
    assert created["client"]["default_effect"] == "deny"
    assert created["gateway_url"].endswith("/mcp")
    listed = await operator.ok(await operator.get(f"/clients/{created['client']['slug']}/keys"))
    assert [k["name"] for k in rows(listed)] == ["Production"]
    assert "key" not in rows(listed)[0]
    assert key["key"] not in str(listed)


async def test_rules_are_validated_and_ordered_by_specificity(
    people: People, make_client: Any
) -> None:
    operator = people.operator
    client = await make_client()
    path = f"/clients/{client.slug}/rules"

    ok = await operator.ok(await operator.post(path, {"pattern": "tickets.*", "effect": "allow"}))
    assert ok["pattern"] == "tickets.*"
    duplicate = await operator.post(path, {"pattern": "tickets.*", "effect": "deny"})
    bad_pattern = await operator.post(path, {"pattern": "no-dot", "effect": "allow"})
    bad_constraint = await operator.post(
        path,
        {
            "pattern": "tickets.create_ticket",
            "constraints": [{"argument": "priority", "rule": "pattern", "value": "(unclosed"}],
        },
    )
    bad_redact = await operator.post(path, {"pattern": "notes.get_note", "redact": ["not a path!"]})

    assert duplicate.status_code == 409
    assert bad_pattern.status_code == 422
    assert bad_constraint.status_code == 422
    assert bad_redact.status_code == 422


async def test_the_permission_matrix_shows_what_each_rule_grants(
    people: People, make_client: Any
) -> None:
    client = await make_client(
        [
            {"pattern": "tickets.*", "effect": "allow"},
            {"pattern": "tickets.delete_ticket", "effect": "deny"},
            {"pattern": "notes.search_notes", "effect": "allow"},
        ]
    )

    access = rows(await people.viewer.ok(await people.viewer.get(f"/clients/{client.slug}/tools")))
    by_name = {row["qualified_name"]: row for row in access}

    assert by_name["tickets.get_ticket"]["allowed"] is True
    assert by_name["tickets.get_ticket"]["rule_pattern"] == "tickets.*"
    assert by_name["tickets.delete_ticket"]["allowed"] is False
    assert by_name["tickets.delete_ticket"]["rule_pattern"] == "tickets.delete_ticket"
    assert by_name["notes.search_notes"]["allowed"] is True
    assert by_name["notes.get_note"]["allowed"] is False
    assert "default" in by_name["notes.get_note"]["reason"].lower()
    assert by_name["tickets.get_ticket"]["read_only"] is True


async def test_simulation_explains_a_call_without_making_it(
    people: People, make_client: Any
) -> None:
    client = await make_client(
        [
            {
                "pattern": "tickets.create_ticket",
                "effect": "allow",
                "constraints": [
                    {"argument": "priority", "rule": "one_of", "values": ["low", "normal"]}
                ],
            }
        ]
    )
    simulate = f"/clients/{client.slug}/simulate"

    fine = await people.viewer.ok(
        await people.viewer.post(
            simulate,
            {"tool": "tickets.create_ticket", "arguments": {"title": "Printer", "priority": "low"}},
        )
    )
    assert fine["would_call"] is True

    blocked = await people.viewer.ok(
        await people.viewer.post(
            simulate,
            {"tool": "tickets.create_ticket", "arguments": {"title": "Fire", "priority": "urgent"}},
        )
    )
    assert blocked["would_call"] is False
    assert blocked["violations"][0]["argument"] == "priority"

    hidden = await people.viewer.ok(
        await people.viewer.post(simulate, {"tool": "notes.get_note", "arguments": {}})
    )
    assert hidden["allowed"] is False
    missing = await people.viewer.ok(
        await people.viewer.post(simulate, {"tool": "nothing.here", "arguments": {}})
    )
    assert missing["found"] is False

    invalid = await people.viewer.ok(
        await people.viewer.post(
            simulate, {"tool": "tickets.create_ticket", "arguments": {"priority": "low"}}
        )
    )
    assert invalid["schema_errors"]


async def test_clients_can_be_suspended_resumed_and_deleted(
    people: People, make_client: Any
) -> None:
    operator = people.operator
    client = await make_client()

    suspended = await operator.ok(
        await operator.patch(f"/clients/{client.slug}", {"status": "suspended"})
    )
    assert suspended["status"] == "suspended"
    resumed = await operator.ok(
        await operator.patch(f"/clients/{client.slug}", {"status": "active"})
    )
    assert resumed["status"] == "active"

    assert (await operator.delete(f"/clients/{client.slug}")).status_code == 204
    assert (await operator.get(f"/clients/{client.slug}")).status_code == 404


async def test_a_client_key_cannot_use_the_management_api(people: People, make_client: Any) -> None:
    client = await make_client()

    response = await people.viewer.http.request(
        "GET", "/api/v1/servers", headers={"authorization": f"Bearer {client.key}"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "client_key_not_allowed"


async def test_roles_decide_who_may_change_clients_and_accounts(
    people: People, make_client: Any
) -> None:
    client = await make_client()
    new = {"name": "Nope", "slug": unique("nope")}

    assert (await people.viewer.post("/clients", new)).status_code == 403
    assert (
        await people.viewer.post(f"/clients/{client.slug}/keys", {"name": "x"})
    ).status_code == 403
    assert (await people.viewer.delete(f"/clients/{client.slug}")).status_code == 403
    assert (await people.operator.get("/users")).status_code == 403
    assert (
        await people.operator.post("/users", {"email": "a@example.com", "name": "A"})
    ).status_code == 403
    assert (await people.admin.get("/users")).status_code == 200
    assert (await people.viewer.get(f"/clients/{client.slug}")).status_code == 200


async def test_clients_list_with_counts_and_filters(people: People, make_client: Any) -> None:
    client = await make_client([{"pattern": "notes.*", "effect": "allow"}], name="Findable agent")

    found = await people.viewer.ok(await people.viewer.get("/clients", q="Findable"))

    assert found["total"] >= 1
    mine = next(c for c in found["items"] if c["slug"] == client.slug)
    assert mine["rules"] == 1
    assert mine["active_keys"] == 1


async def test_every_key_is_listed_with_its_client_and_state(
    people: People, make_client: Any
) -> None:
    operator = people.operator
    first = await make_client(name="Key holder")
    second = await operator.ok(
        await operator.post(f"/clients/{first.slug}/keys", {"name": "Spare"})
    )
    await operator.delete(f"/clients/{first.slug}/keys/{second['id']}")

    everything = await people.viewer.ok(await people.viewer.get("/keys", q=first.slug))
    active = await people.viewer.ok(await people.viewer.get("/keys", q=first.slug, state="active"))
    revoked = await people.viewer.ok(
        await people.viewer.get("/keys", q=first.slug, state="revoked")
    )

    assert everything["total"] == 2
    assert [k["name"] for k in active["items"]] == ["Default key"]
    assert [k["name"] for k in revoked["items"]] == ["Spare"]
    assert active["items"][0]["client_slug"] == first.slug
    assert "key" not in active["items"][0]
    assert (await people.viewer.get("/keys", state="nonsense")).status_code == 422


async def test_a_single_client_reports_the_same_counts_as_the_list(
    people: People, make_client: Any
) -> None:
    client = await make_client([{"pattern": "notes.*", "effect": "allow"}])

    one = await people.viewer.ok(await people.viewer.get(f"/clients/{client.slug}"))

    assert one["rules"] == 1
    assert one["active_keys"] == 1
