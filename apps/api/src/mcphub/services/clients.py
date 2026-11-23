"""Gateway clients: their keys, their policy rules, and what those rules add up to."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.errors import ConflictError, NotFoundError, UnprocessableError
from mcphub.core.security import generate_api_key
from mcphub.core.text import is_valid_slug, slugify
from mcphub.models import Client, ClientKey, PolicyRule
from mcphub.models.enums import ClientStatus, Effect
from mcphub.policy import constraints, naming
from mcphub.policy.constraints import Violation, parse_constraints
from mcphub.policy.patterns import validate_pattern
from mcphub.repositories.catalog import CatalogRepository
from mcphub.repositories.clients import (
    ClientRepository,
    ClientSummary,
    KeyRepository,
    RuleRepository,
)
from mcphub.services import audit
from mcphub.services.actor import Actor
from mcphub.services.container import Container
from mcphub.services.gateway import schema_errors
from mcphub.services.views import Access, compile_view, constraints_of, evaluate

_PATH = re.compile(r"^[A-Za-z0-9_-]{1,64}(?:\.[A-Za-z0-9_-]{1,64}){0,7}$")


@dataclass(slots=True)
class ClientInput:
    name: str
    slug: str | None = None
    description: str = ""
    default_effect: Effect = Effect.DENY
    tool_separator: str = naming.DOT
    rate_limit_per_minute: int | None = None
    record_arguments: bool = True


@dataclass(slots=True)
class RuleInput:
    pattern: str
    effect: Effect
    constraints: list[dict[str, Any]] = field(default_factory=list)
    rate_limit_per_minute: int | None = None
    redact: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True, slots=True)
class Simulation:
    tool: str
    exposed: str
    found: bool
    allowed: bool
    reason: str
    rule: PolicyRule | None = None
    schema_errors: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @property
    def would_call(self) -> bool:
        return self.found and self.allowed and not self.schema_errors and not self.violations


def _check_redact(paths: list[str]) -> list[str]:
    for path in paths:
        if not _PATH.fullmatch(path):
            raise UnprocessableError(f"{path!r} is not an argument path such as `customer.email`.")
    return sorted(set(paths))


class ClientService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.clients = ClientRepository(session)
        self.keys = KeyRepository(session)
        self.rules = RuleRepository(session)

    # Clients

    async def page(
        self, *, q: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[list[ClientSummary], int]:
        since = datetime.now(UTC) - timedelta(hours=24)
        return await self.clients.page(q=q, status=status, since=since, limit=limit, offset=offset)

    async def summary(self, client: Client) -> ClientSummary:
        """The client with its key, rule and call counts, as the list shows them."""
        since = datetime.now(UTC) - timedelta(hours=24)
        found, _ = await self.clients.page(
            q=None, status=None, since=since, limit=1, offset=0, only=client.id
        )
        return found[0] if found else ClientSummary(client, 0, 0, 0)

    async def get(self, slug: str) -> Client:
        client = await self.clients.by_slug(slug)
        if client is None:
            raise NotFoundError("Client not found.")
        return client

    async def _unique_slug(self, requested: str | None, name: str) -> str:
        if requested:
            slug = requested.strip().lower()
            if not is_valid_slug(slug):
                raise UnprocessableError(
                    "Use lowercase letters, digits and single hyphens.", code="invalid_slug"
                )
            if await self.clients.slug_taken(slug):
                raise ConflictError(f"A client called {slug} already exists.")
            return slug
        base = slugify(name, fallback="client")
        slug, n = base, 2
        while await self.clients.slug_taken(slug):
            slug = f"{base[:44]}-{n}"
            n += 1
        return slug

    async def create(
        self,
        actor: Actor,
        data: ClientInput,
        *,
        key_name: str = "Default key",
        key_expires_in_days: int | None = None,
    ) -> tuple[Client, ClientKey, str]:
        """A new client and its first key (the plaintext is returned once, never stored)."""
        if data.tool_separator not in naming.SEPARATORS:
            raise UnprocessableError("The separator must be . or __.")
        client = await self.clients.add(
            Client(
                slug=await self._unique_slug(data.slug, data.name),
                name=data.name.strip(),
                description=data.description.strip(),
                default_effect=data.default_effect.value,
                tool_separator=data.tool_separator,
                rate_limit_per_minute=data.rate_limit_per_minute,
                record_arguments=data.record_arguments,
                created_by=actor.user_id,
            )
        )
        key, plaintext = await self._new_key(actor, client, key_name, key_expires_in_days)
        await audit.record(
            self.session,
            actor,
            action="client.created",
            target_type="client",
            target_id=client.id,
            target_name=client.slug,
            details={"default_effect": client.default_effect},
        )
        await self.session.commit()
        return client, key, plaintext

    async def update(self, actor: Actor, client: Client, changes: dict[str, Any]) -> Client:
        if "tool_separator" in changes and changes["tool_separator"] not in naming.SEPARATORS:
            raise UnprocessableError("The separator must be . or __.")
        changed: list[str] = []
        for key, value in changes.items():
            if isinstance(value, Effect | ClientStatus):
                value = value.value
            if isinstance(value, str) and key in {"name", "description"}:
                value = value.strip()
            if getattr(client, key) != value:
                setattr(client, key, value)
                changed.append(key)
        if not changed:
            return client
        action = "client.updated"
        if "status" in changed:
            action = (
                "client.suspended" if client.status == ClientStatus.SUSPENDED else "client.resumed"
            )
        await audit.record(
            self.session,
            actor,
            action=action,
            target_type="client",
            target_id=client.id,
            target_name=client.slug,
            details={"fields": sorted(changed)},
        )
        await self.session.commit()
        await self.c.cache.bump_client(client.id)
        return client

    async def delete(self, actor: Actor, client: Client) -> None:
        await audit.record(
            self.session,
            actor,
            action="client.deleted",
            target_type="client",
            target_id=client.id,
            target_name=client.slug,
        )
        await self.session.delete(client)
        await self.session.commit()
        await self.c.cache.bump_keys()
        await self.c.cache.bump_client(client.id)

    # Keys

    async def page_keys(
        self, *, state: str | None, q: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[ClientKey, Client]], int]:
        return await self.keys.page(
            state=state, q=q, now=datetime.now(UTC), limit=limit, offset=offset
        )

    async def list_keys(self, client: Client) -> list[ClientKey]:
        return await self.keys.for_client(client.id)

    async def _new_key(
        self, actor: Actor, client: Client, name: str, expires_in_days: int | None
    ) -> tuple[ClientKey, str]:
        generated = generate_api_key(self.c.settings.api_key_pepper.get_secret_value())
        key = await self.keys.add(
            ClientKey(
                client_id=client.id,
                name=name.strip(),
                prefix=generated.prefix,
                secret_hash=generated.secret_hash,
                created_by=actor.user_id,
                expires_at=(
                    datetime.now(UTC) + timedelta(days=expires_in_days) if expires_in_days else None
                ),
            )
        )
        return key, generated.plaintext

    async def create_key(
        self, actor: Actor, client: Client, name: str, expires_in_days: int | None
    ) -> tuple[ClientKey, str]:
        key, plaintext = await self._new_key(actor, client, name, expires_in_days)
        await audit.record(
            self.session,
            actor,
            action="key.created",
            target_type="client",
            target_id=client.id,
            target_name=client.slug,
            details={"key": key.name, "prefix": key.prefix},
        )
        await self.session.commit()
        return key, plaintext

    async def revoke_key(self, actor: Actor, client: Client, key_id: uuid.UUID) -> ClientKey:
        key = await self.keys.get(client.id, key_id)
        if key is None:
            raise NotFoundError("Key not found.")
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            await audit.record(
                self.session,
                actor,
                action="key.revoked",
                target_type="client",
                target_id=client.id,
                target_name=client.slug,
                details={"key": key.name, "prefix": key.prefix},
            )
            await self.session.commit()
            # Every cached key lookup was built before this revocation; none survives it.
            await self.c.cache.bump_keys()
        return key

    # Rules

    async def list_rules(self, client: Client) -> list[PolicyRule]:
        return await self.rules.for_client(client.id)

    def _validated(self, data: RuleInput) -> RuleInput:
        try:
            data.pattern = validate_pattern(data.pattern)
            parsed = parse_constraints(data.constraints)
        except ValueError as exc:
            raise UnprocessableError(str(exc), code="invalid_rule") from exc
        data.constraints = [c.model_dump(mode="json") for c in parsed]
        data.redact = _check_redact(data.redact)
        data.description = data.description.strip()
        return data

    async def _policy_changed(
        self, actor: Actor, client: Client, action: str, rule: PolicyRule
    ) -> None:
        await self.clients.bump_policy_version(client.id)
        await audit.record(
            self.session,
            actor,
            action=action,
            target_type="client",
            target_id=client.id,
            target_name=client.slug,
            details={"pattern": rule.pattern, "effect": rule.effect},
        )
        await self.session.commit()
        await self.c.cache.bump_client(client.id)

    async def add_rule(self, actor: Actor, client: Client, data: RuleInput) -> PolicyRule:
        data = self._validated(data)
        if await self.rules.find(client.id, data.pattern):
            raise ConflictError(f"This client already has a rule for {data.pattern}.")
        rule = await self.rules.add(
            PolicyRule(
                client_id=client.id,
                pattern=data.pattern,
                effect=data.effect.value,
                constraints=data.constraints,
                rate_limit_per_minute=data.rate_limit_per_minute,
                redact=data.redact,
                description=data.description,
            )
        )
        await self._policy_changed(actor, client, "rule.created", rule)
        return rule

    async def update_rule(
        self, actor: Actor, client: Client, rule_id: uuid.UUID, changes: dict[str, Any]
    ) -> PolicyRule:
        rule = await self.rules.get(client.id, rule_id)
        if rule is None:
            raise NotFoundError("Rule not found.")
        merged = self._validated(
            RuleInput(
                pattern=changes.get("pattern", rule.pattern),
                effect=Effect(changes.get("effect", rule.effect)),
                constraints=changes.get("constraints", rule.constraints),
                rate_limit_per_minute=changes.get(
                    "rate_limit_per_minute", rule.rate_limit_per_minute
                ),
                redact=changes.get("redact", rule.redact),
                description=changes.get("description", rule.description),
            )
        )
        if merged.pattern != rule.pattern and await self.rules.find(client.id, merged.pattern):
            raise ConflictError(f"This client already has a rule for {merged.pattern}.")
        rule.pattern = merged.pattern
        rule.effect = merged.effect.value
        rule.constraints = merged.constraints
        rule.rate_limit_per_minute = merged.rate_limit_per_minute
        rule.redact = merged.redact
        rule.description = merged.description
        await self._policy_changed(actor, client, "rule.updated", rule)
        return rule

    async def delete_rule(self, actor: Actor, client: Client, rule_id: uuid.UUID) -> None:
        rule = await self.rules.get(client.id, rule_id)
        if rule is None:
            raise NotFoundError("Rule not found.")
        await self.session.delete(rule)
        await self._policy_changed(actor, client, "rule.deleted", rule)

    # What the rules add up to

    async def access(self, client: Client) -> list[Access]:
        rules = await self.rules.for_client(client.id)
        catalog = await CatalogRepository(self.session).gateway_tools()
        return evaluate(client, rules, catalog)

    async def simulate(self, client: Client, tool: str, arguments: dict[str, Any]) -> Simulation:
        """What the gateway would do with this call, without calling anything."""
        parts = naming.split(tool) or naming.split(tool, client.tool_separator)
        if parts is None:
            return Simulation(tool, tool, False, False, "That is not a namespaced tool name.")
        canonical = naming.canonical(*parts)
        exposed = naming.qualify(*parts, client.tool_separator)
        catalog = [
            (server, item)
            for server, item in await CatalogRepository(self.session).gateway_tools()
            if (server.slug, item.name) == parts
        ]
        if not catalog:
            return Simulation(
                canonical, exposed, False, False, "No enabled server offers this tool right now."
            )
        rules = await self.rules.for_client(client.id)
        (access,) = evaluate(client, rules, catalog)
        matched = access.decision.rule.id if access.decision.rule else None
        rule = next((r for r in rules if r.id == matched), None)
        if not access.decision.allowed:
            return Simulation(canonical, exposed, True, False, access.decision.reason, rule)
        view = compile_view(client, rules, catalog, catalog_generation=0, client_generation=0)
        (view_tool,) = view.tools
        return Simulation(
            canonical,
            exposed,
            True,
            True,
            access.decision.reason,
            rule,
            schema_errors(view_tool, arguments),
            constraints.check(constraints_of(view_tool), arguments),
        )
