"""Gateway clients, their API keys, policy rules, effective access and simulations."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from mcphub.api.deps import ContainerDep, OperatorDep, SessionDep, ViewerDep
from mcphub.models import Client, ClientKey
from mcphub.models.enums import Effect
from mcphub.repositories.clients import ClientSummary
from mcphub.schemas.clients import (
    AccessOut,
    ClientCreate,
    ClientCreated,
    ClientOut,
    ClientUpdate,
    KeyCreate,
    KeyCreated,
    KeyOut,
    RuleCreate,
    RuleOut,
    RuleUpdate,
    SimulateOut,
    SimulateRequest,
    ViolationOut,
)
from mcphub.schemas.common import Page
from mcphub.services.clients import ClientInput, ClientService, RuleInput

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


def client_out(client: Client, summary: ClientSummary | None = None) -> ClientOut:
    out = ClientOut.model_validate(client)
    if summary is not None:
        out = out.model_copy(
            update={
                "active_keys": summary.active_keys,
                "rules": summary.rules,
                "calls_24h": summary.calls_24h,
            }
        )
    return out


def key_created(key: ClientKey, plaintext: str) -> KeyCreated:
    return KeyCreated.model_validate({**KeyOut.model_validate(key).model_dump(), "key": plaintext})


@router.get("", summary="Clients")
async def list_clients(
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[Literal["active", "suspended"] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ClientOut]:
    summaries, total = await ClientService(container, session).page(
        q=q, status=status_, limit=limit, offset=offset
    )
    return Page[ClientOut](
        items=[client_out(s.client, s) for s in summaries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    summary="Create a client and its first key (shown once)",
    status_code=status.HTTP_201_CREATED,
)
async def create_client(
    body: ClientCreate, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> ClientCreated:
    client, key, plaintext = await ClientService(container, session).create(
        actor,
        ClientInput(
            name=body.name,
            slug=body.slug,
            description=body.description,
            default_effect=Effect(body.default_effect),
            tool_separator=body.tool_separator,
            rate_limit_per_minute=body.rate_limit_per_minute,
            record_arguments=body.record_arguments,
        ),
        key_name=body.key_name,
        key_expires_in_days=body.key_expires_in_days,
    )
    return ClientCreated(
        client=client_out(client),
        key=key_created(key, plaintext),
        gateway_url=container.settings.public_gateway_url,
    )


@router.get("/{slug}", summary="One client")
async def get_client(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> ClientOut:
    service = ClientService(container, session)
    client = await service.get(slug)
    return client_out(client, await service.summary(client))


@router.patch("/{slug}", summary="Change a client's settings, suspend or resume it")
async def update_client(
    slug: str, body: ClientUpdate, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> ClientOut:
    service = ClientService(container, session)
    client = await service.update(
        actor, await service.get(slug), body.model_dump(exclude_unset=True)
    )
    return client_out(client, await service.summary(client))


@router.delete("/{slug}", summary="Delete a client, its keys and rules", status_code=204)
async def delete_client(
    slug: str, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = ClientService(container, session)
    await service.delete(actor, await service.get(slug))


@router.get("/{slug}/keys", summary="The client's API keys")
async def list_keys(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[KeyOut]:
    service = ClientService(container, session)
    return [KeyOut.model_validate(k) for k in await service.list_keys(await service.get(slug))]


@router.post(
    "/{slug}/keys",
    summary="Create a key (the secret is shown once)",
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    slug: str, body: KeyCreate, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> KeyCreated:
    service = ClientService(container, session)
    key, plaintext = await service.create_key(
        actor, await service.get(slug), body.name, body.expires_in_days
    )
    return key_created(key, plaintext)


@router.delete("/{slug}/keys/{key_id}", summary="Revoke a key", status_code=204)
async def revoke_key(
    slug: str, key_id: uuid.UUID, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = ClientService(container, session)
    await service.revoke_key(actor, await service.get(slug), key_id)


@router.get("/{slug}/rules", summary="The client's policy rules")
async def list_rules(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[RuleOut]:
    service = ClientService(container, session)
    return [RuleOut.model_validate(r) for r in await service.list_rules(await service.get(slug))]


@router.post("/{slug}/rules", summary="Add a rule", status_code=status.HTTP_201_CREATED)
async def create_rule(
    slug: str, body: RuleCreate, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> RuleOut:
    service = ClientService(container, session)
    rule = await service.add_rule(
        actor,
        await service.get(slug),
        RuleInput(
            pattern=body.pattern,
            effect=Effect(body.effect),
            constraints=[c.model_dump(mode="json") for c in body.constraints],
            rate_limit_per_minute=body.rate_limit_per_minute,
            redact=body.redact,
            description=body.description,
        ),
    )
    return RuleOut.model_validate(rule)


@router.patch("/{slug}/rules/{rule_id}", summary="Change a rule")
async def update_rule(
    slug: str,
    rule_id: uuid.UUID,
    body: RuleUpdate,
    actor: OperatorDep,
    container: ContainerDep,
    session: SessionDep,
) -> RuleOut:
    service = ClientService(container, session)
    changes = body.model_dump(exclude_unset=True, mode="json")
    rule = await service.update_rule(actor, await service.get(slug), rule_id, changes)
    return RuleOut.model_validate(rule)


@router.delete("/{slug}/rules/{rule_id}", summary="Delete a rule", status_code=204)
async def delete_rule(
    slug: str, rule_id: uuid.UUID, actor: OperatorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = ClientService(container, session)
    await service.delete_rule(actor, await service.get(slug), rule_id)


@router.get("/{slug}/tools", summary="Every catalog tool, and whether this client may call it")
async def client_access(
    slug: str, actor: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[AccessOut]:
    service = ClientService(container, session)
    rows = await service.access(await service.get(slug))
    return [
        AccessOut(
            server_slug=row.server.slug,
            server_name=row.server.name,
            tool=row.tool.name,
            qualified_name=f"{row.server.slug}.{row.tool.name}",
            exposed_name=row.exposed,
            title=row.tool.title,
            description=row.tool.description,
            allowed=row.decision.allowed,
            reason=row.decision.reason,
            rule_id=row.decision.rule.id if row.decision.rule else None,
            rule_pattern=row.decision.rule.pattern if row.decision.rule else None,
            read_only=row.tool.annotations.get("readOnlyHint"),
            destructive=row.tool.annotations.get("destructiveHint"),
        )
        for row in rows
    ]


@router.post(
    "/{slug}/simulate", summary="What the gateway would do with a call (nothing is called)"
)
async def simulate(
    slug: str,
    body: SimulateRequest,
    actor: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
) -> SimulateOut:
    service = ClientService(container, session)
    result = await service.simulate(await service.get(slug), body.tool, body.arguments)
    return SimulateOut(
        tool=result.tool,
        exposed_name=result.exposed,
        found=result.found,
        allowed=result.allowed,
        reason=result.reason,
        rule_id=result.rule.id if result.rule else None,
        rule_pattern=result.rule.pattern if result.rule else None,
        schema_errors=result.schema_errors,
        violations=[
            ViolationOut(argument=v.argument, rule=v.rule, message=v.message)
            for v in result.violations
        ],
        would_call=result.would_call,
    )
