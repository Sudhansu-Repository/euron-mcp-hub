"""Upstream secrets: write-only values, encrypted by the configured vault.

A value comes in through `set`, is handed to the vault and never kept anywhere else.
Nothing in this module returns it: the API sees names, kinds, versions and dates only.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.errors import NotFoundError, UnprocessableError
from mcphub.core.logging import get_logger
from mcphub.integrations.vault import SecretContext, StoredSecret
from mcphub.models import Server, ServerSecret
from mcphub.models.enums import SecretKind, Transport
from mcphub.repositories.servers import SecretRepository
from mcphub.services import audit
from mcphub.services.actor import Actor
from mcphub.services.container import Container
from mcphub.services.servers import check_env_name, check_header_name
from mcphub.services.specs import stored

log = get_logger("mcphub.secrets")

# KMS encrypts at most 4 KiB directly; no header or token needs more.
MAX_VALUE_BYTES = 4096


class SecretService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.secrets = SecretRepository(session)

    async def list(self, server: Server) -> list[ServerSecret]:
        return await self.secrets.for_server(server.id)

    async def set(
        self, actor: Actor, server: Server, kind: SecretKind, name: str, value: str
    ) -> ServerSecret:
        if kind is SecretKind.HEADER:
            check_header_name(name)
        else:
            check_env_name(name)
            if server.transport != Transport.STDIO:
                raise UnprocessableError(
                    "Environment secrets apply to stdio servers; use a header for HTTP servers."
                )
        if not value or len(value.encode()) > MAX_VALUE_BYTES:
            raise UnprocessableError(f"A secret value must be 1 to {MAX_VALUE_BYTES} bytes.")
        existing = await self.secrets.find(server.id, kind.value, name)
        vault = self.c.vaults.active
        context = SecretContext(server.id, kind.value, name)
        same_backend = existing is not None and existing.backend == vault.backend
        result = await vault.store(
            context, value, stored(existing) if same_backend and existing else None
        )
        retired = stored(existing) if existing is not None and not same_backend else None
        if existing is None:
            secret = await self.secrets.add(
                ServerSecret(
                    server_id=server.id,
                    kind=kind.value,
                    name=name,
                    backend=result.backend,
                    ciphertext=result.ciphertext,
                    secret_arn=result.secret_arn,
                    key_ref=result.key_ref,
                    created_by=actor.user_id,
                    updated_by=actor.user_id,
                )
            )
        else:
            secret = existing
            secret.backend = result.backend
            secret.ciphertext = result.ciphertext
            secret.secret_arn = result.secret_arn
            secret.key_ref = result.key_ref
            secret.version += 1
            secret.updated_by = actor.user_id
        server.config_version += 1
        await audit.record(
            self.session,
            actor,
            action="secret.set",
            target_type="server",
            target_id=server.id,
            target_name=server.slug,
            details={
                "kind": kind.value,
                "name": name,
                "version": secret.version,
                "backend": vault.backend,
            },
        )
        await self.session.commit()
        await self._applied(server)
        if retired is not None:
            await self._destroy(retired, server.slug, name)
        return secret

    async def delete(self, actor: Actor, server: Server, secret_id: uuid.UUID) -> None:
        secret = await self.secrets.get(server.id, secret_id)
        if secret is None:
            raise NotFoundError("Secret not found.")
        value = stored(secret)
        await self.session.delete(secret)
        server.config_version += 1
        await audit.record(
            self.session,
            actor,
            action="secret.deleted",
            target_type="server",
            target_id=server.id,
            target_name=server.slug,
            details={"kind": secret.kind, "name": secret.name},
        )
        await self.session.commit()
        await self._applied(server)
        await self._destroy(value, server.slug, secret.name)

    async def _applied(self, server: Server) -> None:
        # The next call connects with the new values, here and (through the catalog
        # generation in every view) on every other gateway replica.
        self.c.pool.invalidate(server.id)
        await self.c.cache.bump_catalog()

    async def _destroy(self, value: StoredSecret, server: str, name: str) -> None:
        try:
            await self.c.vaults.for_backend(value.backend).destroy(value)
        except Exception:
            log.warning("secret_destroy_failed", server=server, secret=name)
