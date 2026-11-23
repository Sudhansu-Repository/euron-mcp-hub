"""Client views: the tools one client may see, compiled from its rules and the catalog.

A view is what the gateway consults on every request, so it holds everything a call
needs without another query: the exposed name, schemas, and the rule that admitted the
tool with its constraints, rate limit and redaction paths. It is plain data so it can
be cached in Valkey as JSON.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import orjson

from mcphub.models import Client, PolicyRule, Server, Tool
from mcphub.models.enums import Effect
from mcphub.policy import naming
from mcphub.policy.constraints import Constraint, parse_constraints
from mcphub.policy.engine import Decision, Rule, decide


@dataclass(frozen=True, slots=True)
class ViewTool:
    server_id: str
    server_slug: str
    server_name: str
    config_version: int
    timeout_s: int
    name: str
    exposed: str
    qualified: str
    title: str | None
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]
    fingerprint: str
    rule_id: str | None
    constraints: list[dict[str, Any]]
    rate_limit: int | None
    redact: list[str]


@dataclass(frozen=True)
class ClientView:
    client_id: str
    client_name: str
    slug: str
    status: str
    separator: str
    rate_limit: int | None
    record_arguments: bool
    catalog_generation: int
    client_generation: int
    tools: list[ViewTool]
    _index: dict[str, ViewTool] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", {tool.exposed: tool for tool in self.tools})

    @property
    def active(self) -> bool:
        return self.status == "active"

    def find(self, exposed_name: str) -> ViewTool | None:
        return self._index.get(exposed_name)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_index", None)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ClientView:
        tools = [ViewTool(**tool) for tool in data.pop("tools")]
        return cls(**data, tools=tools)


def to_rule(rule: PolicyRule) -> Rule:
    return Rule(
        pattern=rule.pattern,
        effect=Effect(rule.effect),
        id=rule.id,
        constraints=tuple(parse_constraints(rule.constraints)),
        rate_limit_per_minute=rule.rate_limit_per_minute,
        redact=tuple(rule.redact),
    )


@functools.lru_cache(maxsize=2048)
def _parsed(raw: bytes) -> tuple[Constraint, ...]:
    return tuple(parse_constraints(orjson.loads(raw)))


def constraints_of(tool: ViewTool) -> tuple[Constraint, ...]:
    """Typed constraints for a view entry, parsed once per distinct rule body."""
    if not tool.constraints:
        return ()
    return _parsed(orjson.dumps(tool.constraints, option=orjson.OPT_SORT_KEYS))


@dataclass(frozen=True, slots=True)
class Access:
    """One catalog tool as one client sees it, for the effective-access screen."""

    server: Server
    tool: Tool
    exposed: str
    decision: Decision


def evaluate(
    client: Client, rules: Sequence[PolicyRule], catalog: Sequence[tuple[Server, Tool]]
) -> list[Access]:
    typed = [to_rule(rule) for rule in rules]
    default = Effect(client.default_effect)
    return [
        Access(
            server=server,
            tool=tool,
            exposed=naming.qualify(server.slug, tool.name, client.tool_separator),
            decision=decide(typed, default, naming.canonical(server.slug, tool.name)),
        )
        for server, tool in catalog
    ]


def compile_view(
    client: Client,
    rules: Sequence[PolicyRule],
    catalog: Sequence[tuple[Server, Tool]],
    *,
    catalog_generation: int,
    client_generation: int,
) -> ClientView:
    tools: list[ViewTool] = []
    for access in evaluate(client, rules, catalog):
        if not access.decision.allowed:
            continue
        server, tool, rule = access.server, access.tool, access.decision.rule
        tools.append(
            ViewTool(
                server_id=str(server.id),
                server_slug=server.slug,
                server_name=server.name,
                config_version=server.config_version,
                timeout_s=server.timeout_s,
                name=tool.name,
                exposed=access.exposed,
                qualified=naming.canonical(server.slug, tool.name),
                title=tool.title,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                annotations=tool.annotations,
                fingerprint=tool.fingerprint,
                rule_id=str(rule.id) if rule and rule.id else None,
                constraints=[c.model_dump(mode="json") for c in rule.constraints] if rule else [],
                rate_limit=rule.rate_limit_per_minute if rule else None,
                redact=list(rule.redact) if rule else [],
            )
        )
    return ClientView(
        client_id=str(client.id),
        client_name=client.name,
        slug=client.slug,
        status=client.status,
        separator=client.tool_separator,
        rate_limit=client.rate_limit_per_minute,
        record_arguments=client.record_arguments,
        catalog_generation=catalog_generation,
        client_generation=client_generation,
        tools=tools,
    )


def as_uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None
