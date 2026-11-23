"""Turning a catalog entry and its secrets into a connectable UpstreamSpec.

This is the one place secret values are decrypted. The spec lives in memory while a
connection opens, and the guards run again here, so a server registered before an
operator tightened STDIO_ALLOWED_COMMANDS or UPSTREAM_ALLOWED_HOSTS stops connecting.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from mcphub.core.config import Settings
from mcphub.integrations.vault import SecretContext, StoredSecret, Vaults
from mcphub.models import Server, ServerSecret
from mcphub.models.enums import SecretKind, Transport
from mcphub.repositories.servers import SecretRepository, ServerRepository
from mcphub.services.container import Container
from mcphub.upstream.guard import check_command, check_resolved, check_url
from mcphub.upstream.spec import UpstreamSpec, UpstreamUnavailableError


def stored(secret: ServerSecret) -> StoredSecret:
    return StoredSecret(
        backend=secret.backend,
        ciphertext=secret.ciphertext,
        secret_arn=secret.secret_arn,
        key_ref=secret.key_ref,
    )


def context(secret: ServerSecret) -> SecretContext:
    return SecretContext(secret.server_id, secret.kind, secret.name)


async def check_target(server: Server, settings: Settings) -> None:
    """Refuse a target the egress policy does not allow (also run again at connect time)."""
    if server.transport == Transport.STREAMABLE_HTTP:
        allowed, private = settings.upstream_allowed_hosts, settings.upstream_allow_private
        check_url(server.url or "", allowed, allow_private=private)
        await check_resolved(server.url or "", allowed, allow_private=private)
    else:
        check_command(server.command or "", settings.stdio_allowed_commands)


async def build_spec(
    server: Server, secrets: Sequence[ServerSecret], vaults: Vaults, settings: Settings
) -> UpstreamSpec:
    await check_target(server, settings)
    # HTTP header names are case-insensitive; a secret replaces a plain header of the same name.
    headers = {str(name).lower(): str(value) for name, value in server.headers.items()}
    env = {str(name): str(value) for name, value in server.env.items()}
    for secret in secrets:
        value = await vaults.reveal(context(secret), stored(secret))
        if secret.kind == SecretKind.HEADER:
            headers[secret.name.lower()] = value
        else:
            env[secret.name] = value
    return UpstreamSpec(
        server_id=server.id,
        slug=server.slug,
        transport=Transport(server.transport),
        config_version=server.config_version,
        url=server.url,
        command=server.command,
        args=tuple(str(arg) for arg in server.args),
        headers=headers,
        env=env,
    )


async def load_spec(container: Container, server_id: uuid.UUID) -> UpstreamSpec:
    async with container.db.session() as session:
        server = await ServerRepository(session).get(server_id)
        if server is None or not server.enabled:
            raise UpstreamUnavailableError("This server is disabled or no longer registered.")
        secrets = await SecretRepository(session).for_server(server_id)
    return await build_spec(server, secrets, container.vaults, container.settings)
