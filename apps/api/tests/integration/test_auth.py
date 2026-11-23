"""Dashboard sign-in, sessions, passwords, lockout and account administration."""

from __future__ import annotations

import httpx2
import pytest

from tests.integration.conftest import People
from tests.integration.support import PASSWORD, unique

pytestmark = pytest.mark.integration


async def test_first_run_setup_is_refused_once_an_account_exists(
    http: httpx2.AsyncClient, people: People
) -> None:
    again = await http.post(
        "/api/v1/auth/setup",
        json={"email": "intruder@example.com", "name": "Intruder", "password": PASSWORD},
    )

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_set_up"
    info = await people.viewer.ok(await people.viewer.get("/system/info"))
    assert info["needs_setup"] is False


async def test_sign_in_sets_an_httponly_cookie_that_works_for_reads(
    http: httpx2.AsyncClient, people: People
) -> None:
    response = await http.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "mcphub_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    me = await http.get("/api/v1/auth/me")
    assert me.json()["email"] == "admin@example.com"


async def test_cookie_sessions_cannot_write_from_another_origin(
    http: httpx2.AsyncClient, people: People
) -> None:
    login = await http.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200

    foreign = await http.post("/api/v1/auth/logout", headers={"origin": "https://evil.example.org"})
    own = await http.post("/api/v1/auth/logout", headers={"origin": "http://localhost:3150"})

    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "csrf"
    assert own.status_code == 204
    http.cookies.clear()


async def test_wrong_credentials_get_one_uniform_answer(
    http: httpx2.AsyncClient, people: People
) -> None:
    wrong_password = await http.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "nope-nope-nope"}
    )
    unknown = await http.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"}
    )

    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_repeated_failures_lock_the_account_temporarily(
    http: httpx2.AsyncClient, people: People
) -> None:
    admin = people.admin
    email = f"{unique('lock')}@example.com"
    created = await admin.ok(
        await admin.post("/users", {"email": email, "name": "Lock", "role": "viewer"})
    )

    statuses = [
        (
            await http.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-wrong-1"}
            )
        ).status_code
        for _ in range(9)
    ]
    right = await http.post(
        "/api/v1/auth/login",
        json={"email": email, "password": created["temporary_password"]},
    )

    assert statuses[:8] == [401] * 8
    assert statuses[8] == 429
    assert right.status_code == 429


async def test_changing_a_password_ends_every_other_session(
    http: httpx2.AsyncClient, people: People
) -> None:
    admin = people.admin
    email = f"{unique('pw')}@example.com"
    created = await admin.ok(
        await admin.post("/users", {"email": email, "name": "Pw", "role": "viewer"})
    )
    first = (
        await http.post(
            "/api/v1/auth/login", json={"email": email, "password": created["temporary_password"]}
        )
    ).json()["token"]
    second = (
        await http.post(
            "/api/v1/auth/login", json={"email": email, "password": created["temporary_password"]}
        )
    ).json()["token"]
    http.cookies.clear()

    changed = await http.post(
        "/api/v1/auth/password",
        headers={"authorization": f"Bearer {first}"},
        json={
            "current_password": created["temporary_password"],
            "new_password": "A-brand-new-pass-77",
        },
    )
    stale = await http.get("/api/v1/auth/me", headers={"authorization": f"Bearer {second}"})
    fresh = await http.get(
        "/api/v1/auth/me", headers={"authorization": f"Bearer {changed.json()['token']}"}
    )

    assert changed.status_code == 200
    assert stale.status_code == 401
    assert fresh.status_code == 200
    weak = await http.post(
        "/api/v1/auth/password",
        headers={"authorization": f"Bearer {changed.json()['token']}"},
        json={"current_password": "A-brand-new-pass-77", "new_password": "short"},
    )
    assert weak.status_code == 422
    http.cookies.clear()


async def test_signing_out_revokes_the_token(http: httpx2.AsyncClient, people: People) -> None:
    admin = people.admin
    email = f"{unique('out')}@example.com"
    created = await admin.ok(
        await admin.post("/users", {"email": email, "name": "Out", "role": "viewer"})
    )
    token = (
        await http.post(
            "/api/v1/auth/login", json={"email": email, "password": created["temporary_password"]}
        )
    ).json()["token"]
    http.cookies.clear()
    headers = {"authorization": f"Bearer {token}"}
    assert (await http.get("/api/v1/auth/me", headers=headers)).status_code == 200

    assert (await http.post("/api/v1/auth/logout", headers=headers)).status_code == 204

    assert (await http.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_deactivated_accounts_lose_access_immediately(
    http: httpx2.AsyncClient, people: People
) -> None:
    admin = people.admin
    email = f"{unique('gone')}@example.com"
    created = await admin.ok(
        await admin.post("/users", {"email": email, "name": "Gone", "role": "operator"})
    )
    token = (
        await http.post(
            "/api/v1/auth/login", json={"email": email, "password": created["temporary_password"]}
        )
    ).json()["token"]
    http.cookies.clear()
    headers = {"authorization": f"Bearer {token}"}
    assert (await http.get("/api/v1/servers", headers=headers)).status_code == 200

    await admin.ok(await admin.patch(f"/users/{created['user']['id']}", {"is_active": False}))

    assert (await http.get("/api/v1/servers", headers=headers)).status_code == 401
    login = await http.post(
        "/api/v1/auth/login", json={"email": email, "password": created["temporary_password"]}
    )
    assert login.status_code == 401
    http.cookies.clear()


async def test_the_last_admin_cannot_be_demoted(people: People) -> None:
    admin = people.admin
    me = await admin.ok(await admin.get("/auth/me"))

    response = await admin.patch(f"/users/{me['id']}", {"role": "viewer"})

    assert response.status_code == 422


async def test_error_responses_use_one_envelope_with_a_request_id(people: People) -> None:
    response = await people.viewer.get("/servers/does-not-exist")

    body = response.json()["error"]
    assert response.status_code == 404
    assert body["code"] == "not_found"
    assert body["request_id"] == response.headers["x-request-id"]
    invalid = await people.operator.post("/servers", {"name": ""})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_failed"
    assert invalid.json()["error"]["details"]
