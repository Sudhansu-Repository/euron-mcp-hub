"""Where upstream secrets live: KMS ciphertext, a Secrets Manager secret, or local AES-GCM.

Every backend binds a stored value to the server and the secret it belongs to (a KMS
encryption context, a Secrets Manager name, or AES-GCM associated data), so a ciphertext
copied into another server's row does not decrypt there. Plaintext only ever leaves a
vault through `reveal()`, which the upstream connection code calls at connect time.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import anyio
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from mcphub.core.config import Settings
from mcphub.core.errors import ServiceUnavailableError
from mcphub.core.logging import get_logger
from mcphub.integrations import aws

if TYPE_CHECKING:
    from mypy_boto3_kms import KMSClient
    from mypy_boto3_secretsmanager import SecretsManagerClient

log = get_logger("mcphub.vault")


class SecretUnavailableError(ServiceUnavailableError):
    code = "secret_unavailable"
    message = "A secret for this server could not be read from the secret store."


@dataclass(frozen=True, slots=True)
class SecretContext:
    """Which secret a value belongs to. Part of every encryption, so it cannot be moved."""

    server_id: uuid.UUID
    kind: str
    name: str

    def kms_context(self) -> dict[str, str]:
        return {"mcphub:server": str(self.server_id), "mcphub:secret": f"{self.kind}:{self.name}"}

    def associated_data(self) -> bytes:
        return f"mcphub/{self.server_id}/{self.kind}/{self.name}".encode()

    def secret_name(self, prefix: str) -> str:
        return f"{prefix.strip('/')}/servers/{self.server_id}/{self.kind}/{self.name}"


@dataclass(frozen=True, slots=True)
class StoredSecret:
    """What the database keeps for a secret: never the plaintext."""

    backend: str
    ciphertext: bytes | None = None
    secret_arn: str | None = None
    key_ref: str | None = None


class SecretVault(Protocol):
    backend: str

    async def store(
        self, context: SecretContext, value: str, existing: StoredSecret | None
    ) -> StoredSecret: ...

    async def reveal(self, context: SecretContext, stored: StoredSecret) -> str: ...

    async def destroy(self, stored: StoredSecret) -> None: ...

    async def check(self) -> None: ...


def _unavailable(action: str, exc: Exception) -> SecretUnavailableError:
    # The AWS error code is safe to log; the request (which may hold the value) is not.
    code = exc.response.get("Error", {}).get("Code") if isinstance(exc, ClientError) else None
    log.warning("secret_store_error", action=action, error=type(exc).__name__, aws_code=code)
    return SecretUnavailableError()


class KmsVault:
    """Ciphertext in Postgres, encrypted by a KMS key under an encryption context."""

    backend = "kms"

    def __init__(self, settings: Settings) -> None:
        if not settings.secrets_kms_key_id:
            raise ValueError("SECRETS_KMS_KEY_ID is required for SECRETS_BACKEND=kms")
        self._key_id = settings.secrets_kms_key_id
        self._client: KMSClient = aws.kms_client(settings)

    async def store(
        self, context: SecretContext, value: str, existing: StoredSecret | None
    ) -> StoredSecret:
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._client.encrypt(
                    KeyId=self._key_id,
                    Plaintext=value.encode(),
                    EncryptionContext=context.kms_context(),
                )
            )
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("encrypt", exc) from exc
        return StoredSecret(
            backend=self.backend,
            ciphertext=response["CiphertextBlob"],
            key_ref=response.get("KeyId", self._key_id),
        )

    async def reveal(self, context: SecretContext, stored: StoredSecret) -> str:
        if stored.ciphertext is None:
            raise SecretUnavailableError()
        blob = stored.ciphertext
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._client.decrypt(
                    CiphertextBlob=blob, EncryptionContext=context.kms_context()
                )
            )
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("decrypt", exc) from exc
        return bytes(response["Plaintext"]).decode()

    async def destroy(self, stored: StoredSecret) -> None:
        # The ciphertext is the database row; deleting the row is the deletion.
        return None

    async def check(self) -> None:
        try:
            await anyio.to_thread.run_sync(lambda: self._client.describe_key(KeyId=self._key_id))
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("describe_key", exc) from exc


class SecretsManagerVault:
    """One Secrets Manager secret per value; Postgres keeps only its ARN."""

    backend = "secretsmanager"

    def __init__(self, settings: Settings) -> None:
        self._prefix = settings.secrets_name_prefix
        self._kms_key_id = settings.secrets_kms_key_id
        self._recovery_days = settings.secrets_recovery_window_days
        self._client: SecretsManagerClient = aws.secrets_client(settings)

    async def store(
        self, context: SecretContext, value: str, existing: StoredSecret | None
    ) -> StoredSecret:
        name = context.secret_name(self._prefix)
        target = existing.secret_arn if existing and existing.secret_arn else None
        try:
            if target is not None:
                await anyio.to_thread.run_sync(
                    lambda: self._client.put_secret_value(SecretId=target, SecretString=value)
                )
                return StoredSecret(backend=self.backend, secret_arn=target)
            return await anyio.to_thread.run_sync(lambda: self._create(context, name, value))
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("store", exc) from exc

    def _create(self, context: SecretContext, name: str, value: str) -> StoredSecret:
        options: dict[str, Any] = {
            "Name": name,
            "SecretString": value,
            "Description": f"MCPHub {context.kind} secret {context.name}",
            "Tags": [
                {"Key": "mcphub:server", "Value": str(context.server_id)},
                {"Key": "mcphub:secret", "Value": f"{context.kind}:{context.name}"},
            ],
        }
        if self._kms_key_id:
            options["KmsKeyId"] = self._kms_key_id
        try:
            arn = self._client.create_secret(**options)["ARN"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceExistsException":
                raise
            # Left over from a deleted server or a deletion still in its recovery window:
            # take it back rather than failing the operator's save.
            try:
                self._client.restore_secret(SecretId=name)
            except ClientError:
                log.info("secret_restore_skipped")
            arn = self._client.put_secret_value(SecretId=name, SecretString=value)["ARN"]
        return StoredSecret(backend=self.backend, secret_arn=arn, key_ref=self._kms_key_id)

    async def reveal(self, context: SecretContext, stored: StoredSecret) -> str:
        arn = stored.secret_arn
        if arn is None:
            raise SecretUnavailableError()
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._client.get_secret_value(SecretId=arn)
            )
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("get_secret_value", exc) from exc
        return str(response["SecretString"])

    async def destroy(self, stored: StoredSecret) -> None:
        arn = stored.secret_arn
        if arn is None:
            return
        options: dict[str, Any] = (
            {"RecoveryWindowInDays": self._recovery_days}
            if self._recovery_days >= 7
            else {"ForceDeleteWithoutRecovery": True}
        )
        try:
            await anyio.to_thread.run_sync(
                lambda: self._client.delete_secret(SecretId=arn, **options)
            )
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("delete_secret", exc) from exc

    async def check(self) -> None:
        try:
            await anyio.to_thread.run_sync(lambda: self._client.list_secrets(MaxResults=1))
        except (ClientError, BotoCoreError) as exc:
            raise _unavailable("list_secrets", exc) from exc


class LocalVault:
    """AES-256-GCM under a key from the environment. Laptops only; production refuses it."""

    backend = "local"
    _VERSION = b"\x01"

    def __init__(self, settings: Settings) -> None:
        self._aead = AESGCM(_local_key(settings))

    async def store(
        self, context: SecretContext, value: str, existing: StoredSecret | None
    ) -> StoredSecret:
        nonce = os.urandom(12)
        sealed = self._aead.encrypt(nonce, value.encode(), context.associated_data())
        return StoredSecret(backend=self.backend, ciphertext=self._VERSION + nonce + sealed)

    async def reveal(self, context: SecretContext, stored: StoredSecret) -> str:
        blob = stored.ciphertext
        if blob is None or blob[:1] != self._VERSION:
            raise SecretUnavailableError()
        try:
            plain = self._aead.decrypt(blob[1:13], blob[13:], context.associated_data())
        except Exception as exc:
            log.warning("local_secret_decrypt_failed")
            raise SecretUnavailableError() from exc
        return plain.decode()

    async def destroy(self, stored: StoredSecret) -> None:
        return None

    async def check(self) -> None:
        return None


def _local_key(settings: Settings) -> bytes:
    if settings.secrets_local_key is not None:
        key = base64.b64decode(settings.secrets_local_key.get_secret_value())
        if len(key) != 32:
            raise ValueError("SECRETS_LOCAL_KEY must be 32 random bytes, base64 encoded")
        return key
    # Development only (production refuses the local backend): a key derived from the
    # session secret, so a laptop needs no extra configuration.
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=hashlib.sha256(b"mcphub-local-vault").digest(),
        info=b"mcphub upstream secrets",
    ).derive(settings.session_secret.get_secret_value().encode())


def _construct(backend: str, settings: Settings) -> SecretVault:
    if backend == "kms":
        return KmsVault(settings)
    if backend == "secretsmanager":
        return SecretsManagerVault(settings)
    if backend == "local":
        return LocalVault(settings)
    raise ValueError(f"unknown secrets backend {backend!r}")


class Vaults:
    """The configured vault for new values, and readers for values stored elsewhere.

    Each stored secret records its backend, so switching SECRETS_BACKEND does not strand
    existing secrets: they stay readable (as long as that backend is still configured) and
    move to the new backend the next time an operator saves them.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.active: SecretVault = _construct(settings.secrets_backend, settings)
        self._readers: dict[str, SecretVault] = {self.active.backend: self.active}

    def for_backend(self, backend: str) -> SecretVault:
        reader = self._readers.get(backend)
        if reader is None:
            try:
                reader = _construct(backend, self._settings)
            except ValueError as exc:
                log.warning("secret_backend_not_configured", backend=backend)
                raise SecretUnavailableError() from exc
            self._readers[backend] = reader
        return reader

    async def reveal(self, context: SecretContext, stored: StoredSecret) -> str:
        return await self.for_backend(stored.backend).reveal(context, stored)
