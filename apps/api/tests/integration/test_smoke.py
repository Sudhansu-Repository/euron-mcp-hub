from __future__ import annotations

import pytest

from tests.integration.conftest import People

pytestmark = pytest.mark.integration


async def test_the_stack_boots_and_the_first_admin_exists(people: People) -> None:
    me = await people.admin.ok(await people.admin.get("/auth/me"))

    assert me["role"] == "admin"
    assert (await people.viewer.ok(await people.viewer.get("/auth/me")))["role"] == "viewer"


async def test_the_shared_catalog_is_discovered(
    people: People, hub: dict[str, dict[str, object]]
) -> None:
    servers = await people.viewer.ok(await people.viewer.get("/servers"))

    by_slug = {s["slug"]: s for s in servers["items"]}
    assert {"notes", "toolbox", "tickets"} <= set(by_slug)
    assert by_slug["tickets"]["tool_count"] >= 5
    assert by_slug["notes"]["health"] in {"healthy", "unknown"}
