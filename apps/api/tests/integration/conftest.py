"""Integration fixtures: real Postgres, Valkey and the Floci AWS emulator.

`make test-integration` starts all three (scripts/test-deps.sh, ports 5455, 6415 and 4615)
and runs this suite. It works in a database of its own (`mcphub_test`, recreated on every
run), Valkey database 15 (flushed on every run), and a KMS key created for the run on the
emulator, so nothing else is touched. Point it elsewhere with TEST_DATABASE_ADMIN_URL,
TEST_REDIS_URL and TEST_AWS_ENDPOINT_URL.

The tests run the real application over ASGI. The upstream MCP servers are the bundled demo
servers, served on free local ports for the whole run, so a call travels the whole path:
client, gateway, policy, pooled upstream connection, server, call log.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import asyncpg
import boto3
import httpx2
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.engine import URL, make_url

from mcphub.core.config import Settings, get_settings
from mcphub.db.migrate import migrate
from mcphub.main import create_app
from mcphub.services.container import Container
from tests.integration.support import PASSWORD, Api, Upstreams, held, upstream_servers

# The emulator accepts any credentials; real ones must never be sent to it.
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
for _name in ("AWS_SESSION_TOKEN", "AWS_PROFILE"):
    os.environ.pop(_name, None)

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL", "postgresql://mcphub:mcphub@localhost:5455/mcphub"
)
REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6415/15")
AWS_ENDPOINT = os.environ.get("TEST_AWS_ENDPOINT_URL", "http://localhost:4615")
TEST_DATABASE = os.environ.get("TEST_DATABASE_NAME", "mcphub_test")
WEB_ORIGIN = "http://localhost:3150"
RUN = uuid.uuid4().hex[:8]
TICKETS_TOKEN = f"tkt_{uuid.uuid4().hex}"


def database_url(name: str) -> str:
    admin = make_url(ADMIN_URL)
    return URL.create(
        "postgresql+asyncpg",
        username=admin.username,
        password=admin.password,
        host=admin.host,
        port=admin.port,
        database=name,
    ).render_as_string(hide_password=False)


async def recreate_database(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def aws_client(service: str) -> Any:
    return boto3.client(service, endpoint_url=AWS_ENDPOINT, region_name="us-east-1")


def make_settings(kms_key_id: str, **overrides: Any) -> Settings:
    """Test settings, independent of the developer's environment variables."""
    values: dict[str, Any] = {
        "app_env": "test",
        "log_level": "warning",
        "database_url": database_url(TEST_DATABASE),
        "redis_url": REDIS_URL,
        "session_secret": "integration-session-secret-0123456789abcdef",
        "api_key_pepper": "integration-api-key-pepper-0123456789abcdef",
        "cors_origins": [WEB_ORIGIN],
        "web_url": WEB_ORIGIN,
        "aws_endpoint_url": AWS_ENDPOINT,
        "aws_region": "us-east-1",
        "secrets_backend": "kms",
        "secrets_kms_key_id": kms_key_id,
        "secrets_name_prefix": f"mcphub/it-{RUN}",
        "secrets_recovery_window_days": 0,
        "upstream_allowed_hosts": ["127.0.0.1"],
        "stdio_allowed_commands": [os.path.basename(sys.executable)],
        "upstream_connect_timeout_s": 10,
        "audit_flush_interval_ms": 50,
        "rate_limit_login": 100_000,
        "health_interval_s": 5,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture(scope="session")
def kms_key_id() -> str:
    key = aws_client("kms").create_key(Description=f"mcphub integration {RUN}")
    return str(key["KeyMetadata"]["KeyId"])


@pytest.fixture(scope="session")
async def settings(kms_key_id: str) -> Settings:
    get_settings.cache_clear()
    settings = make_settings(kms_key_id)
    await recreate_database(TEST_DATABASE)
    await migrate(settings)
    redis = Redis.from_url(REDIS_URL)
    await redis.flushdb()
    await redis.aclose()
    return settings


@pytest.fixture(scope="session")
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """The real application, started: database, cache, KMS, gateway and call log writer."""
    application = create_app(settings)
    async with held(application.router.lifespan_context(application)):
        yield application


@pytest.fixture(scope="session")
def container(app: FastAPI) -> Container:
    container: Container = app.state.container
    return container


@pytest.fixture(scope="session")
async def http(app: FastAPI) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://api.test", timeout=120
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def upstreams() -> AsyncIterator[Upstreams]:
    async with held(upstream_servers(TICKETS_TOKEN)) as servers:
        yield servers


@dataclass(frozen=True)
class People:
    admin: Api
    operator: Api
    viewer: Api


async def _sign_in(http: httpx2.AsyncClient, email: str, password: str) -> Api:
    response = await http.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    session = httpx2.AsyncClient(
        transport=http._transport,
        base_url="http://api.test",
        timeout=120,
        headers={"authorization": f"Bearer {response.json()['token']}"},
    )
    return Api(session, email)


@pytest.fixture(scope="session")
async def people(http: httpx2.AsyncClient) -> AsyncIterator[People]:
    """The first-run admin, plus an operator and a viewer the admin creates."""
    setup = await http.post(
        "/api/v1/auth/setup",
        json={"email": "admin@example.com", "name": "Ada Admin", "password": PASSWORD},
    )
    assert setup.status_code == 201, setup.text
    admin = await _sign_in(http, "admin@example.com", PASSWORD)
    signed_in: dict[str, Api] = {"admin": admin}
    for role in ("operator", "viewer"):
        email = f"{role}@example.com"
        created = await admin.post("/users", {"email": email, "name": role.title(), "role": role})
        temporary = (await admin.ok(created))["temporary_password"]
        signed_in[role] = await _sign_in(http, email, temporary)
    yield People(signed_in["admin"], signed_in["operator"], signed_in["viewer"])
    for api in signed_in.values():
        await api.http.aclose()


@pytest.fixture(scope="session")
async def hub(people: People, upstreams: Upstreams) -> dict[str, dict[str, Any]]:
    """The catalog the tests share: notes, toolbox and the token-protected tickets server."""
    operator = people.operator
    registered: dict[str, dict[str, Any]] = {}
    for slug, name, url in (
        ("notes", "Team notes", upstreams.notes),
        ("toolbox", "Toolbox", upstreams.toolbox),
    ):
        registered[slug] = await operator.ok(
            await operator.post(
                "/servers", {"name": name, "slug": slug, "url": url, "tags": ["demo"]}
            )
        )
    # Registered before its secret exists: discovery fails with a 401 that names the cause.
    tickets = await operator.ok(
        await operator.post(
            "/servers",
            {
                "name": "Help desk",
                "slug": "tickets",
                "url": upstreams.tickets_v1,
                "discover": False,
            },
        )
    )
    await operator.ok(
        await operator.put(
            "/servers/tickets/secrets",
            {"kind": "header", "name": "Authorization", "value": f"Bearer {TICKETS_TOKEN}"},
        )
    )
    await operator.ok(await operator.post("/servers/tickets/refresh"))
    registered["tickets"] = tickets
    return registered


@dataclass(frozen=True)
class GatewayClient:
    slug: str
    key: str
    key_id: str


@pytest.fixture
async def make_client(people: People, hub: dict[str, Any]) -> Any:
    """A factory for gateway clients with rules: returns the slug and the one-time key."""

    async def factory(rules: list[dict[str, Any]] | None = None, **fields: Any) -> GatewayClient:
        operator = people.operator
        slug = f"c-{uuid.uuid4().hex[:8]}"
        created = await operator.ok(
            await operator.post(
                "/clients", {"name": fields.pop("name", f"Client {slug}"), "slug": slug, **fields}
            )
        )
        for rule in rules or []:
            await operator.ok(await operator.post(f"/clients/{slug}/rules", rule))
        return GatewayClient(slug, created["key"]["key"], created["key"]["id"])

    return factory
