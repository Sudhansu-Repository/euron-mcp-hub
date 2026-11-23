"""Upstream secrets: write-only, envelope-encrypted by KMS, bound to their server."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from mcphub.core.config import Settings
from mcphub.integrations.vault import (
    KmsVault,
    LocalVault,
    SecretContext,
    SecretsManagerVault,
    SecretUnavailableError,
    StoredSecret,
)
from mcphub.models import AuditEvent, ServerSecret
from mcphub.services.container import Container
from tests.integration.conftest import TICKETS_TOKEN, People, make_settings
from tests.integration.support import Upstreams, unique

pytestmark = pytest.mark.integration

VALUE = "Bearer s3cr3t-value-that-must-never-leak-0042"


async def _stored(container: Container, server_id: str) -> list[ServerSecret]:
    async with container.db.session() as session:
        rows = await session.execute(
            select(ServerSecret).where(ServerSecret.server_id == server_id)
        )
        return list(rows.scalars())


async def test_a_secret_value_is_never_returned_by_any_endpoint(
    people: People, container: Container, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("vault")
    server = await operator.ok(
        await operator.post("/servers", {"name": "Vault", "slug": slug, "url": upstreams.toolbox})
    )

    saved = await operator.ok(
        await operator.put(
            f"/servers/{slug}/secrets", {"kind": "header", "name": "Authorization", "value": VALUE}
        )
    )

    assert saved["name"] == "Authorization"
    assert saved["backend"] == "kms"
    assert saved["version"] == 1
    listed = await operator.ok(await operator.get(f"/servers/{slug}/secrets"))
    everything = json.dumps(
        [
            saved,
            listed,
            await operator.ok(await operator.get(f"/servers/{slug}")),
            await operator.ok(await operator.get("/servers")),
            await operator.ok(await operator.get("/activity")),
        ]
    )
    assert "s3cr3t-value" not in everything
    assert all("value" not in item and "ciphertext" not in item for item in listed)

    rows = await _stored(container, server["id"])
    assert len(rows) == 1
    assert rows[0].ciphertext is not None
    assert b"s3cr3t" not in rows[0].ciphertext
    assert rows[0].key_ref


async def test_changing_a_secret_bumps_its_version_and_reconnects_the_server(
    people: People, container: Container, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("rotate")
    server = await operator.ok(
        await operator.post(
            "/servers",
            {"name": "Rotate", "slug": slug, "url": upstreams.tickets, "discover": False},
        )
    )
    path = f"/servers/{slug}/secrets"
    await operator.ok(
        await operator.put(
            path, {"kind": "header", "name": "Authorization", "value": "Bearer wrong"}
        )
    )
    assert (await operator.ok(await operator.post(f"/servers/{slug}/check")))["ok"] is False

    rotated = await operator.ok(
        await operator.put(
            path, {"kind": "header", "name": "Authorization", "value": f"Bearer {TICKETS_TOKEN}"}
        )
    )

    assert rotated["version"] == 2
    assert (await operator.ok(await operator.post(f"/servers/{slug}/check")))["ok"] is True
    after = await operator.ok(await operator.get(f"/servers/{slug}"))
    assert after["config_version"] > server["config_version"]
    assert len(await _stored(container, server["id"])) == 1


async def test_a_ciphertext_cannot_be_replayed_against_another_secret(
    kms_key_id: str, settings: Settings
) -> None:
    vault = KmsVault(make_settings(kms_key_id))
    server_id, other_id = uuid.uuid4(), uuid.uuid4()
    context = SecretContext(server_id, "header", "Authorization")
    stored = await vault.store(context, "swordfish-1234", None)

    assert await vault.reveal(context, stored) == "swordfish-1234"
    with pytest.raises(SecretUnavailableError):
        await vault.reveal(SecretContext(other_id, "header", "Authorization"), stored)
    with pytest.raises(SecretUnavailableError):
        await vault.reveal(SecretContext(server_id, "header", "X-Other"), stored)


async def test_secrets_manager_backend_keeps_only_an_arn_in_the_database(
    kms_key_id: str,
) -> None:
    vault = SecretsManagerVault(make_settings(kms_key_id, secrets_backend="secretsmanager"))
    context = SecretContext(uuid.uuid4(), "env", "WEATHER_API_KEY")

    stored = await vault.store(context, "wx-key-0000-1111", None)
    assert stored.ciphertext is None
    assert stored.secret_arn
    assert await vault.reveal(context, stored) == "wx-key-0000-1111"

    updated = await vault.store(context, "wx-key-2222-3333", stored)
    assert updated.secret_arn == stored.secret_arn
    assert await vault.reveal(context, updated) == "wx-key-2222-3333"

    await vault.destroy(updated)
    with pytest.raises(SecretUnavailableError):
        await vault.reveal(context, updated)


async def test_secrets_stored_by_another_backend_stay_readable(
    container: Container, kms_key_id: str
) -> None:
    context = SecretContext(uuid.uuid4(), "header", "X-Api-Key")
    local = LocalVault(make_settings(kms_key_id, secrets_backend="local"))
    stored: StoredSecret = await local.store(context, "from-the-laptop-1", None)

    assert stored.backend == "local"
    assert await container.vaults.reveal(context, stored) == "from-the-laptop-1"


async def test_secret_names_and_kinds_are_validated(people: People, upstreams: Upstreams) -> None:
    operator = people.operator
    slug = unique("names")
    await operator.ok(
        await operator.post("/servers", {"name": "Names", "slug": slug, "url": upstreams.toolbox})
    )
    path = f"/servers/{slug}/secrets"

    bad_header = await operator.put(path, {"kind": "header", "name": "Bad Header", "value": "x"})
    reserved = await operator.put(path, {"kind": "header", "name": "Content-Type", "value": "x"})
    env_on_http = await operator.put(path, {"kind": "env", "name": "TOKEN", "value": "x"})
    empty = await operator.put(path, {"kind": "header", "name": "X-Team", "value": ""})

    assert {r.status_code for r in (bad_header, reserved, env_on_http, empty)} == {422}


async def test_deleting_a_secret_and_its_audit_trail_carries_no_value(
    people: People, container: Container, upstreams: Upstreams
) -> None:
    operator = people.operator
    slug = unique("drop")
    await operator.ok(
        await operator.post("/servers", {"name": "Drop", "slug": slug, "url": upstreams.toolbox})
    )
    saved: dict[str, Any] = await operator.ok(
        await operator.put(
            f"/servers/{slug}/secrets", {"kind": "header", "name": "X-Team", "value": VALUE}
        )
    )

    assert (await operator.delete(f"/servers/{slug}/secrets/{saved['id']}")).status_code == 204

    assert await operator.ok(await operator.get(f"/servers/{slug}/secrets")) == []
    async with container.db.session() as session:
        events = (await session.execute(select(AuditEvent))).scalars().all()
    assert not any("s3cr3t-value" in json.dumps(e.details) for e in events)
    actions = [e.action for e in events if e.target_name and slug in e.target_name]
    assert any("secret" in action for action in actions)


async def test_viewers_cannot_write_secrets_and_the_vault_health_is_reported(
    people: People, hub: dict[str, Any]
) -> None:
    denied = await people.viewer.put(
        "/servers/notes/secrets", {"kind": "header", "name": "X-Team", "value": "x" * 10}
    )
    assert denied.status_code == 403

    info = await people.viewer.ok(await people.viewer.get("/system/info"))
    assert info["secrets_backend"] == "kms"
