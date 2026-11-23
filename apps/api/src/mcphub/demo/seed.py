"""`make demo`: accounts, servers, clients, policies and two weeks of real gateway traffic.

Everything goes through the real code paths. Servers are registered and discovered by the
services the API uses (the tickets server is upgraded from 1.3.2 to 1.4.0 along the way,
so its version history is a real one). Clients get keys and rules through the client
service. The traffic is real MCP: the app runs in-process, and SDK clients call /mcp with
the demo keys, so every policy decision, constraint, rate limit, timeout and crash in
the call log actually happened.

The only liberty taken is time. The traffic runs in "waves" tagged by request id; each
wave is then moved to its place in the past two weeks (business hours, quieter weekends,
a busy last day), and administrative events are moved to when the story says they
happened. Re-running is safe: existing accounts, servers and clients are reused, and the
traffic is only generated once.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import secrets
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import httpx2
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import func, select, text, update

from mcphub.core.config import Settings
from mcphub.core.errors import AppError
from mcphub.core.logging import get_logger
from mcphub.core.security import hash_password
from mcphub.main import create_app
from mcphub.models import (
    AuditEvent,
    ClientKey,
    HealthCheck,
    PolicyRule,
    Server,
    ServerVersion,
    Tool,
    ToolCall,
    User,
)
from mcphub.models import (
    Client as ClientModel,
)
from mcphub.models.enums import ClientStatus, Effect, Role, SecretKind, Transport
from mcphub.repositories.clients import ClientRepository, KeyRepository
from mcphub.repositories.servers import ServerRepository
from mcphub.repositories.users import UserRepository
from mcphub.services.actor import Actor
from mcphub.services.clients import ClientInput, ClientService, RuleInput
from mcphub.services.container import Container, build_container
from mcphub.services.discovery import DiscoveryService
from mcphub.services.playground import PlaygroundService
from mcphub.services.secrets import SecretService
from mcphub.services.servers import ServerInput, ServerService

log = get_logger("mcphub.demo")
DOMAIN = "lumenlabs.example"
GATEWAY = "http://mcphub.demo"


@dataclass(frozen=True)
class DemoOptions:
    password: str
    servers_host: str = "127.0.0.1"
    tickets_token: str = "demo-tickets-token"  # noqa: S105
    weather_key: str = "demo-weather-key"
    history: bool = True


@dataclass(frozen=True)
class Person:
    email: str
    name: str
    role: Role


PEOPLE = (
    Person(f"priya.sharma@{DOMAIN}", "Priya Sharma", Role.ADMIN),
    Person(f"daniel.okafor@{DOMAIN}", "Daniel Okafor", Role.OPERATOR),
    Person(f"mei.lin@{DOMAIN}", "Mei Lin", Role.VIEWER),
)


class Clock:
    """Database time, and moving rows written since a mark to when the story says."""

    def __init__(self, container: Container) -> None:
        self.c = container
        self.anchor = datetime.now(UTC)

    async def now(self) -> datetime:
        async with self.c.db.session() as session:
            value: datetime = (await session.execute(select(func.now()))).scalar_one()
            return value

    def ago(self, days: float, hour: int | None = None, minute: int = 0) -> datetime:
        moment = self.anchor - timedelta(days=days)
        if hour is not None:
            moment = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return min(moment, self.anchor - timedelta(minutes=5))

    async def move_audit(self, since: datetime, when: datetime) -> None:
        async with self.c.db.session() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditEvent.id)
                        .where(AuditEvent.created_at >= since)
                        .order_by(AuditEvent.created_at, AuditEvent.id)
                    )
                )
                .scalars()
                .all()
            )
            for offset, row_id in enumerate(rows):
                await session.execute(
                    update(AuditEvent)
                    .where(AuditEvent.id == row_id)
                    .values(created_at=when + timedelta(seconds=40 * offset))
                )
            await session.commit()


# Accounts


async def _person(container: Container, person: Person, password: str) -> User:
    async with container.db.session() as session:
        users = UserRepository(session)
        user = await users.by_email(person.email)
        if user is None:
            user = await users.add(
                User(
                    email=person.email,
                    name=person.name,
                    password_hash=await anyio.to_thread.run_sync(hash_password, password),
                    role=person.role.value,
                )
            )
            await session.commit()
        return user


# Servers


async def _register(
    container: Container,
    clock: Clock,
    actor: Actor,
    data: ServerInput,
    secret: tuple[SecretKind, str, str] | None,
    days_ago: float,
) -> Server | None:
    async with container.db.session() as session:
        existing = await ServerRepository(session).by_slug(data.slug or "")
        if existing is not None:
            return existing
    mark = await clock.now()
    when = clock.ago(days_ago, hour=10, minute=15)
    try:
        async with container.db.session() as session:
            server = await ServerService(container, session).create(actor, data)
            if secret is not None:
                kind, name, value = secret
                await SecretService(container, session).set(actor, server, kind, name, value)
    except AppError as exc:
        print(f"  skipped {data.slug}: {exc.message}")
        return None
    await DiscoveryService(container).discover(server.id, actor)
    async with container.db.session() as session:
        await session.execute(
            update(Server).where(Server.id == server.id).values(created_at=when, updated_at=when)
        )
        await session.execute(
            update(ServerVersion)
            .where(ServerVersion.server_id == server.id)
            .values(created_at=when)
        )
        await session.execute(
            update(Tool).where(Tool.server_id == server.id).values(first_seen_at=when)
        )
        await session.commit()
    await clock.move_audit(mark, when)
    return server


async def _upgrade_tickets(
    container: Container, clock: Clock, actor: Actor, server: Server, host: str
) -> None:
    """Point the help desk at its 1.4.0 endpoint: a real version change for discovery."""
    if server.url and not server.url.endswith("/v1/mcp"):
        return
    mark = await clock.now()
    when = clock.ago(2, hour=16, minute=40)
    async with container.db.session() as session:
        service = ServerService(container, session)
        current = await service.get(server.slug)
        await service.update(actor, current, {"url": f"http://{host}:9152/mcp"})
    await DiscoveryService(container).discover(server.id, actor)
    async with container.db.session() as session:
        latest = (
            (
                await session.execute(
                    select(ServerVersion.id).where(
                        ServerVersion.server_id == server.id, ServerVersion.created_at >= mark
                    )
                )
            )
            .scalars()
            .all()
        )
        await session.execute(
            update(ServerVersion).where(ServerVersion.id.in_(latest)).values(created_at=when)
        )
        await session.execute(
            update(Tool)
            .where(Tool.server_id == server.id, Tool.first_seen_at >= mark)
            .values(first_seen_at=when, last_seen_at=when)
        )
        await session.execute(
            update(Tool)
            .where(Tool.server_id == server.id, Tool.changed_at >= mark)
            .values(changed_at=when)
        )
        await session.commit()
    await clock.move_audit(mark, when)


async def _servers(
    container: Container, clock: Clock, priya: Actor, daniel: Actor, options: DemoOptions
) -> dict[str, Server]:
    host = options.servers_host
    plan: list[tuple[Actor, ServerInput, tuple[SecretKind, str, str] | None, float]] = [
        (
            priya,
            ServerInput(
                name="Team notes",
                slug="notes",
                transport=Transport.STREAMABLE_HTTP,
                url=f"http://{host}:9150/mcp",
                description="Plans, postmortems and research notes the whole company writes in.",
                tags=["knowledge", "internal"],
                owner="Platform team",
            ),
            None,
            13,
        ),
        (
            priya,
            ServerInput(
                name="Toolbox",
                slug="toolbox",
                transport=Transport.STREAMABLE_HTTP,
                url=f"http://{host}:9151/mcp",
                description="Arithmetic, unit and time zone conversion for agents.",
                tags=["utilities"],
                owner="Platform team",
                timeout_s=5,
            ),
            None,
            13,
        ),
        (
            daniel,
            ServerInput(
                name="Help desk",
                slug="tickets",
                transport=Transport.STREAMABLE_HTTP,
                url=f"http://{host}:9152/v1/mcp",
                description="Customer and internal support tickets. Holds customer contact data.",
                tags=["support", "customer-data"],
                owner="Support operations",
                timeout_s=15,
            ),
            (SecretKind.HEADER, "Authorization", f"Bearer {options.tickets_token}"),
            12,
        ),
        (
            daniel,
            ServerInput(
                name="Weather",
                slug="weather",
                transport=Transport.STDIO,
                command="mcphub-demo",
                args=["weather"],
                description="Conditions and forecasts from the weather data provider.",
                tags=["external", "data"],
                owner="Data team",
                timeout_s=10,
            ),
            (SecretKind.ENV, "WEATHER_API_KEY", options.weather_key),
            10,
        ),
        (
            priya,
            ServerInput(
                name="Warehouse analytics",
                slug="analytics",
                transport=Transport.STREAMABLE_HTTP,
                url=f"http://{host}:9153/mcp",
                description="SQL over the analytics warehouse. Being moved to the new cluster.",
                tags=["data"],
                owner="Data team",
            ),
            None,
            6,
        ),
    ]
    servers: dict[str, Server] = {}
    for actor, data, secret, days_ago in plan:
        server = await _register(container, clock, actor, data, secret, days_ago)
        if server is not None:
            servers[server.slug] = server
    if "tickets" in servers:
        await _upgrade_tickets(container, clock, daniel, servers["tickets"], host)
    return servers


async def _health_history(container: Container, servers: dict[str, Server]) -> None:
    """Real health checks, spread over the last day."""
    discovery = DiscoveryService(container)
    now = datetime.now(UTC)
    async with container.db.session() as session:
        # Registering a server records its first checks; only an older history means a
        # previous run already spread the checks over the day.
        earlier = await session.scalar(
            select(func.count())
            .select_from(HealthCheck)
            .where(HealthCheck.checked_at < now - timedelta(hours=2))
        )
        if earlier:
            return
    for slug, server in servers.items():
        rounds = 8 if slug == "weather" else 24
        start = await Clock(container).now()
        for _ in range(rounds):
            await discovery.check(server.id)
        async with container.db.session() as session:
            ids = (
                (
                    await session.execute(
                        select(HealthCheck.id)
                        .where(HealthCheck.server_id == server.id, HealthCheck.checked_at >= start)
                        .order_by(HealthCheck.checked_at)
                    )
                )
                .scalars()
                .all()
            )
            step = timedelta(hours=24) / max(1, len(ids))
            for index, check_id in enumerate(ids):
                await session.execute(
                    update(HealthCheck)
                    .where(HealthCheck.id == check_id)
                    .values(checked_at=now - timedelta(hours=24) + step * (index + 1))
                )
            await session.commit()


# Clients and policy


@dataclass
class ClientPlan:
    data: ClientInput
    rules: list[RuleInput]
    days_ago: float
    user_agent: str
    mode: str = "auto"


def _client_plans() -> list[ClientPlan]:
    allow, deny = Effect.ALLOW, Effect.DENY
    return [
        ClientPlan(
            ClientInput(
                name="Support copilot",
                slug="support-copilot",
                description="Drafts replies and keeps tickets up to date for the support team.",
                rate_limit_per_minute=600,
            ),
            [
                RuleInput(
                    "tickets.*",
                    allow,
                    constraints=[
                        {
                            "argument": "priority",
                            "rule": "one_of",
                            "values": ["low", "normal", "high"],
                        }
                    ],
                    redact=["requester_email"],
                    description="Urgent tickets stay with people; emails stay out of logs.",
                ),
                RuleInput(
                    "tickets.delete_ticket",
                    deny,
                    description="Tickets are never deleted by agents.",
                ),
                RuleInput("notes.search_notes", allow),
                RuleInput("notes.get_note", allow),
            ],
            11,
            "support-copilot/2.4 (python-mcp)",
        ),
        ClientPlan(
            ClientInput(
                name="Ops runbook agent",
                slug="ops-agent",
                description="Runs on-call runbooks: checks, conversions, status updates.",
                rate_limit_per_minute=300,
            ),
            [
                RuleInput("toolbox.*", allow),
                RuleInput("weather.*", allow),
                RuleInput("notes.*", allow),
                RuleInput("notes.delete_note", deny),
                RuleInput("tickets.list_tickets", allow),
                RuleInput("tickets.get_ticket", allow),
                RuleInput(
                    "tickets.update_status",
                    allow,
                    constraints=[
                        {"argument": "status", "rule": "one_of", "values": ["pending", "resolved"]}
                    ],
                    description="The agent can resolve, but closing stays a human decision.",
                ),
            ],
            10,
            "ops-runbook-agent/0.9 (python-mcp)",
        ),
        ClientPlan(
            ClientInput(
                name="Research assistant",
                slug="research-assistant",
                description="Research agent on a model API that rejects dots in tool names.",
                default_effect=Effect.ALLOW,
                tool_separator="__",
            ),
            [
                RuleInput("*.delete_*", deny, description="Read and create only."),
                RuleInput("tickets.*", deny, description="No customer data."),
                RuleInput("analytics.*", deny),
                RuleInput("weather.*", allow, rate_limit_per_minute=20),
            ],
            9,
            "research-assistant/1.2 (python-mcp)",
        ),
        ClientPlan(
            ClientInput(
                name="Daniel's IDE",
                slug="daniel-ide",
                description="Daniel Okafor's editor, through the IDE's MCP support.",
            ),
            [RuleInput("notes.*", allow), RuleInput("toolbox.*", allow)],
            8,
            "editor-mcp/1.104",
            "legacy",
        ),
        ClientPlan(
            ClientInput(
                name="Nightly reports job",
                slug="nightly-reports",
                description="Built the overnight ticket report until the new one shipped.",
            ),
            [RuleInput("tickets.list_tickets", allow), RuleInput("toolbox.current_time", allow)],
            12,
            "nightly-reports/3.1 (cron)",
        ),
    ]


async def _clients(
    container: Container, clock: Clock, daniel: Actor
) -> tuple[dict[str, ClientPlan], dict[str, str]]:
    plans = {plan.data.slug or "": plan for plan in _client_plans()}
    keys: dict[str, str] = {}
    for slug, plan in plans.items():
        async with container.db.session() as session:
            service = ClientService(container, session)
            existing = await ClientRepository(session).by_slug(slug)
            mark = await clock.now()
            when = clock.ago(plan.days_ago, hour=11, minute=5)
            if existing is None:
                client, _, plaintext = await service.create(
                    daniel, plan.data, key_name="Production key"
                )
                for rule in plan.rules:
                    await service.add_rule(daniel, client, rule)
            else:
                client = existing
                # The original key was shown once; a re-seed issues a fresh one.
                _, plaintext = await service.create_key(daniel, client, "Demo key (re-seed)", 30)
            keys[slug] = plaintext
        if existing is None:
            async with container.db.session() as session:
                await session.execute(
                    update(ClientModel)
                    .where(ClientModel.id == client.id)
                    .values(created_at=when, updated_at=when)
                )
                await session.execute(
                    update(ClientKey)
                    .where(ClientKey.client_id == client.id)
                    .values(created_at=when)
                )
                await session.execute(
                    update(PolicyRule)
                    .where(PolicyRule.client_id == client.id)
                    .values(created_at=when, updated_at=when)
                )
                await session.commit()
            await clock.move_audit(mark, when)
    return plans, keys


async def _key_rotation(container: Container, clock: Clock, daniel: Actor) -> None:
    """A laptop test key, made and later revoked: what key rotation looks like."""
    async with container.db.session() as session:
        service = ClientService(container, session)
        client = await service.get("support-copilot")
        if any(
            k.name == "Laptop test key" for k in await KeyRepository(session).for_client(client.id)
        ):
            return
        mark = await clock.now()
        key, _ = await service.create_key(daniel, client, "Laptop test key", None)
        await service.revoke_key(daniel, client, key.id)
        await session.execute(
            update(ClientKey)
            .where(ClientKey.id == key.id)
            .values(created_at=clock.ago(9, hour=15), revoked_at=clock.ago(5, hour=9, minute=30))
        )
        await session.commit()
    await clock.move_audit(mark, clock.ago(5, hour=9, minute=30))


# Traffic


@dataclass(frozen=True)
class Call:
    client: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


CITIES = ("Lisbon", "Pune", "Berlin", "Toronto", "Singapore", "San Francisco", "Bengaluru")
TICKET_TITLES = (
    "Refund not received after 10 days",
    "Cannot export invoices to CSV",
    "Login link expired immediately",
    "Wrong currency on the October invoice",
    "Request to add a second admin",
    "API returns 429 during batch import",
    "Dashboard slow for large accounts",
    "Shipment tracking shows the wrong carrier",
)
NOTE_QUERIES = ("launch", "on-call", "postmortem", "pricing", "SSO", "deprecation", "interview")


def _support(rng: random.Random) -> Call:
    roll = rng.random()
    if roll < 0.30:
        return Call(
            "support-copilot", "tickets.list_tickets", {"status": rng.choice(["open", "pending"])}
        )
    if roll < 0.52:
        return Call(
            "support-copilot", "tickets.get_ticket", {"ticket_id": f"TCK-{rng.randint(1201, 1212)}"}
        )
    if roll < 0.66:
        return Call(
            "support-copilot",
            "tickets.create_ticket",
            {
                "title": rng.choice(TICKET_TITLES),
                "priority": rng.choice(["normal", "normal", "high", "low"]),
                "requester_email": f"customer{rng.randint(10, 99)}@acmefreight.example",
            },
        )
    if roll < 0.76:
        return Call(
            "support-copilot",
            "tickets.add_comment",
            {
                "ticket_id": f"TCK-{rng.randint(1201, 1212)}",
                "body": "Thanks, we are looking into it.",
            },
        )
    if roll < 0.86:
        return Call("support-copilot", "notes.search_notes", {"query": rng.choice(NOTE_QUERIES)})
    if roll < 0.90:
        return Call(
            "support-copilot",
            "tickets.create_ticket",
            {"title": "Outage reported by enterprise customer", "priority": "urgent"},
        )
    if roll < 0.93:
        return Call("support-copilot", "tickets.create_ticket", {"priority": "low"})
    if roll < 0.96:
        return Call("support-copilot", "tickets.get_ticket", {"ticket_id": "TCK-9999"})
    return Call(
        "support-copilot", "tickets.delete_ticket", {"ticket_id": f"TCK-{rng.randint(1201, 1212)}"}
    )


def _ops(rng: random.Random) -> Call:
    roll = rng.random()
    if roll < 0.18:
        return Call(
            "ops-agent",
            "toolbox.current_time",
            {"timezone": rng.choice(["UTC", "Europe/Lisbon", "Asia/Kolkata", "America/Toronto"])},
        )
    if roll < 0.30:
        return Call(
            "ops-agent",
            "toolbox.calculate",
            {
                "expression": (
                    f"({rng.randint(100, 900)} * {rng.randint(2, 30)}) / {rng.randint(2, 12)}"
                )
            },
        )
    if roll < 0.40:
        return Call(
            "ops-agent",
            "toolbox.convert_timezone",
            {
                "time": "2026-10-23T09:30",
                "from_timezone": "Europe/Berlin",
                "to_timezone": "Asia/Singapore",
            },
        )
    if roll < 0.55:
        return Call("ops-agent", "weather.current_weather", {"city": rng.choice(CITIES)})
    if roll < 0.62:
        return Call(
            "ops-agent", "weather.forecast", {"city": rng.choice(CITIES), "days": rng.randint(2, 5)}
        )
    if roll < 0.72:
        return Call("ops-agent", "tickets.list_tickets", {"priority": "urgent"})
    if roll < 0.78:
        return Call(
            "ops-agent",
            "tickets.update_status",
            {
                "ticket_id": f"TCK-{rng.randint(1201, 1212)}",
                "status": "pending",
                "note": "Runbook step 3 done.",
            },
        )
    if roll < 0.81:
        return Call(
            "ops-agent",
            "tickets.update_status",
            {"ticket_id": f"TCK-{rng.randint(1201, 1212)}", "status": "closed"},
        )
    if roll < 0.92:
        return Call(
            "ops-agent",
            "notes.search_notes",
            {"query": rng.choice(["on-call", "postmortem", "runbook"])},
        )
    if roll < 0.96:
        return Call("ops-agent", "toolbox.calculate", {"expression": "1/0"})
    return Call("ops-agent", "notes.delete_note", {"note_id": "n-002"})


def _research(rng: random.Random) -> Call:
    roll = rng.random()
    if roll < 0.30:
        return Call(
            "research-assistant", "notes__search_notes", {"query": rng.choice(NOTE_QUERIES)}
        )
    if roll < 0.48:
        return Call(
            "research-assistant", "notes__get_note", {"note_id": f"n-00{rng.randint(1, 8)}"}
        )
    if roll < 0.60:
        return Call(
            "research-assistant",
            "toolbox__convert_units",
            {"value": rng.randint(1, 500), "from_unit": "km", "to_unit": "mi"},
        )
    if roll < 0.72:
        return Call(
            "research-assistant",
            "toolbox__calculate",
            {"expression": f"{rng.randint(10, 99)} ** 2 / 7"},
        )
    if roll < 0.80:
        return Call(
            "research-assistant",
            "notes__list_notes",
            {"tag": rng.choice(["research", "planning", "ops"])},
        )
    if roll < 0.86:
        return Call(
            "research-assistant", "weather__forecast", {"city": rng.choice(CITIES), "days": 3}
        )
    if roll < 0.92:
        return Call("research-assistant", "tickets__list_tickets", {})
    if roll < 0.96:
        return Call(
            "research-assistant",
            "toolbox__convert_units",
            {"value": 3, "from_unit": "km", "to_unit": "lightyears"},
        )
    return Call("research-assistant", "notes__delete_note", {"note_id": "n-004"})


def _ide(rng: random.Random) -> Call:
    roll = rng.random()
    if roll < 0.35:
        return Call("daniel-ide", "notes.list_notes", {"limit": 10})
    if roll < 0.55:
        return Call("daniel-ide", "notes.search_notes", {"query": rng.choice(NOTE_QUERIES)})
    if roll < 0.70:
        return Call("daniel-ide", "toolbox.random_uuid", {})
    if roll < 0.90:
        return Call(
            "daniel-ide", "toolbox.calculate", {"expression": f"{rng.randint(1, 64)} * 1024"}
        )
    return Call("daniel-ide", "weather.current_weather", {"city": "Lisbon"})


def _nightly(rng: random.Random) -> Call:
    if rng.random() < 0.7:
        return Call("nightly-reports", "tickets.list_tickets", {"limit": 100})
    return Call("nightly-reports", "toolbox.current_time", {})


@dataclass
class Wave:
    tag: str
    start: datetime
    end: datetime
    calls: list[Call]


def _waves(clock: Clock, rng: random.Random) -> list[Wave]:
    """Two weeks of traffic: business hours, quiet weekends, a busy last day."""
    mixes: list[tuple[Callable[[random.Random], Call], float]] = [
        (_support, 0.38),
        (_ops, 0.27),
        (_research, 0.2),
        (_ide, 0.15),
    ]

    def sample(count: int, nightly: int = 0) -> list[Call]:
        calls = [rng.choices(mixes, weights=[w for _, w in mixes])[0][0](rng) for _ in range(count)]
        return calls + [_nightly(rng) for _ in range(nightly)]

    waves: list[Wave] = []
    for days_ago in range(13, 0, -1):
        day = clock.ago(days_ago, hour=0)
        weekend = day.weekday() >= 5
        busy = 0.6 if weekend else 1.0 + (13 - days_ago) * 0.04
        nightly = 3 if days_ago >= 4 else 0
        for hour, length, size in ((9, 3, 22), (13, 4, 26), (19, 3, 8)):
            count = max(3, int(size * busy * rng.uniform(0.8, 1.2)))
            start = day + timedelta(hours=hour)
            waves.append(
                Wave(
                    f"seed-{len(waves):03d}",
                    start,
                    start + timedelta(hours=length),
                    sample(count, nightly if hour == 9 else 0),
                )
            )
    now = clock.anchor
    for hours_ago in range(23, 0, -1):
        hour = (now - timedelta(hours=hours_ago)).hour
        size = 26 if 8 <= hour <= 18 else 6
        start = now - timedelta(hours=hours_ago)
        waves.append(
            Wave(
                f"seed-{len(waves):03d}",
                start,
                start + timedelta(minutes=55),
                sample(int(size * rng.uniform(0.8, 1.2))),
            )
        )
    burst_start = clock.ago(1, hour=15, minute=12)
    waves.append(
        Wave(
            "seed-burst",
            burst_start,
            burst_start + timedelta(seconds=50),
            [
                Call("research-assistant", "weather__current_weather", {"city": rng.choice(CITIES)})
                for _ in range(32)
            ],
        )
    )
    slow = clock.ago(3, hour=14, minute=20)
    waves.append(
        Wave(
            "seed-slow",
            slow,
            slow + timedelta(minutes=20),
            [Call("ops-agent", "toolbox.wait", {"seconds": 7}) for _ in range(3)]
            + [
                Call("ops-agent", "weather.forecast", {"city": "Lisbon", "days": 14})
                for _ in range(2)
            ],
        )
    )
    return waves


async def _run_wave(
    transport: httpx2.AsyncBaseTransport,
    plans: dict[str, ClientPlan],
    keys: dict[str, str],
    wave: Wave,
) -> None:
    async with AsyncExitStack() as stack:
        sessions: dict[str, Client] = {}
        for slug in sorted({call.client for call in wave.calls}):
            plan = plans[slug]
            http = await stack.enter_async_context(
                httpx2.AsyncClient(
                    transport=transport,
                    base_url=GATEWAY,
                    timeout=60,
                    headers={
                        "authorization": f"Bearer {keys[slug]}",
                        "x-request-id": wave.tag,
                        "user-agent": plan.user_agent,
                    },
                )
            )
            sessions[slug] = await stack.enter_async_context(
                Client(
                    streamable_http_client(f"{GATEWAY}/mcp", http_client=http),
                    mode=plan.mode,
                    cache=None,
                )
            )
        semaphore = asyncio.Semaphore(6)

        async def one(call: Call) -> None:
            async with semaphore:
                # Unknown or denied tools are protocol errors; the call log has them anyway.
                with contextlib.suppress(MCPError):
                    await sessions[call.client].call_tool(call.tool, call.arguments)

        await asyncio.gather(*(one(call) for call in wave.calls))


async def _traffic(
    settings: Settings,
    container: Container,
    clock: Clock,
    plans: dict[str, ClientPlan],
    keys: dict[str, str],
    daniel: Actor,
) -> int:
    rng = random.Random(2026)
    waves = _waves(clock, rng)
    app = create_app(settings.model_copy(update={"migrate_on_boot": False}))
    total = sum(len(w.calls) for w in waves)
    print(f"  running {total} tool calls through the gateway in {len(waves)} waves...", flush=True)
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        for index, wave in enumerate(waves, start=1):
            await _run_wave(transport, plans, keys, wave)
            if index % 20 == 0:
                print(f"  ... {index}/{len(waves)} waves", flush=True)
        await app.state.container.call_log.flush()
    await _playground(container, clock, daniel)
    await _retime(container, waves, rng)
    return total


async def _playground(container: Container, clock: Clock, daniel: Actor) -> None:
    mark = await clock.now()
    async with container.db.session() as session:
        client = await ClientService(container, session).get("support-copilot")
        playground = PlaygroundService(container, session)
        await playground.call(
            daniel, client, "tickets.list_tickets", {"status": "open", "limit": 5}
        )
        await playground.call(daniel, client, "notes.search_notes", {"query": "refund"})
        await playground.call(daniel, client, "tickets.delete_ticket", {"ticket_id": "TCK-1203"})
    await container.call_log.flush()
    when = clock.ago(1, hour=11, minute=42)
    async with container.db.session() as session:
        await session.execute(
            update(ToolCall)
            .where(ToolCall.source == "playground", ToolCall.created_at >= mark)
            .values(created_at=when)
        )
        await session.commit()


async def _retime(container: Container, waves: list[Wave], rng: random.Random) -> None:
    """Move each wave to its place in time, with request ids like the middleware makes."""
    async with container.db.session() as session:
        for wave in waves:
            ids = (
                (await session.execute(select(ToolCall.id).where(ToolCall.request_id == wave.tag)))
                .scalars()
                .all()
            )
            span = (wave.end - wave.start).total_seconds()
            moments = sorted(wave.start + timedelta(seconds=rng.uniform(0, span)) for _ in ids)
            for call_id, moment in zip(ids, moments, strict=True):
                await session.execute(
                    update(ToolCall)
                    .where(ToolCall.id == call_id)
                    .values(created_at=moment, request_id=secrets.token_hex(16))
                )
        await session.commit()


async def _suspend_nightly(container: Container, clock: Clock, daniel: Actor) -> None:
    async with container.db.session() as session:
        service = ClientService(container, session)
        client = await service.get("nightly-reports")
        if client.status == ClientStatus.SUSPENDED:
            return
        mark = await clock.now()
        await service.update(daniel, client, {"status": ClientStatus.SUSPENDED})
    await clock.move_audit(mark, clock.ago(3, hour=8, minute=55))


async def _has_traffic(container: Container) -> bool:
    async with container.db.session() as session:
        return bool(await session.scalar(select(func.count()).select_from(ToolCall)))


async def run(settings: Settings, options: DemoOptions) -> None:
    container = build_container(settings)
    container.start()
    clock = Clock(container)
    try:
        people = {p.email: await _person(container, p, options.password) for p in PEOPLE}
        priya, daniel, _ = (Actor(user=people[p.email]) for p in PEOPLE)
        print("Registering and discovering the demo MCP servers...", flush=True)
        servers = await _servers(container, clock, priya, daniel, options)
        print("Creating clients, keys and policy rules...", flush=True)
        plans, keys = await _clients(container, clock, daniel)
        await _key_rotation(container, clock, daniel)
        if options.history and not await _has_traffic(container):
            await _traffic(settings, container, clock, plans, keys, daniel)
            print("  recording health checks...", flush=True)
            await _health_history(container, servers)
        await _suspend_nightly(container, clock, daniel)
        async with container.db.session() as session:
            await session.execute(text("ANALYZE tool_calls"))
            await session.commit()
        _print_summary(settings, options, servers, keys)
    finally:
        await container.close()


def _print_summary(
    settings: Settings, options: DemoOptions, servers: dict[str, Server], keys: dict[str, str]
) -> None:
    print("\nDemo ready. Sign in at", settings.web_url)
    for person in PEOPLE:
        print(f"  {person.email:<34} {person.role.value:<9} password: {options.password}")
    print(f"\n  Servers: {', '.join(sorted(servers))}")
    key = keys.get("support-copilot", "")
    print(f"\n  Gateway: {settings.public_gateway_url}")
    print(f"  Client key (Support copilot): {key}")
    print("\n  Try it with any MCP client, or:")
    print(f"  curl -s {settings.public_gateway_url} \\")
    print(f"    -H 'authorization: Bearer {key}' \\")
    print(
        "    -H 'content-type: application/json' \\\n"
        "    -H 'accept: application/json, text/event-stream' \\"
    )
    print("    -H 'mcp-protocol-version: 2025-11-25' \\")
    print("""    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'""")
