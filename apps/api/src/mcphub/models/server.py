from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mcphub.db.base import Base, IdMixin, TimestampMixin


class Server(IdMixin, TimestampMixin, Base):
    """An upstream MCP server in the catalog. Its slug is the namespace of its tools."""

    __tablename__ = "servers"

    slug: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    transport: Mapped[str] = mapped_column(String(16))
    url: Mapped[str | None] = mapped_column(String(500))
    command: Mapped[str | None] = mapped_column(String(300))
    args: Mapped[list[str]] = mapped_column(default=list)
    # Non-secret settings. Secret ones live in server_secrets.
    env: Mapped[dict[str, Any]] = mapped_column(default=dict)
    headers: Mapped[dict[str, Any]] = mapped_column(default=dict)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    owner: Mapped[str] = mapped_column(String(120), default="")
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(default=True)
    timeout_s: Mapped[int] = mapped_column(default=30)
    refresh_interval_s: Mapped[int] = mapped_column(default=300)
    # Bumped whenever anything used to connect changes (URL, command, headers, env,
    # secrets), so pooled connections built from the old values are replaced.
    config_version: Mapped[int] = mapped_column(default=1)

    health: Mapped[str] = mapped_column(String(16), default="unknown")
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_check_at: Mapped[datetime | None]
    last_healthy_at: Mapped[datetime | None]
    last_latency_ms: Mapped[int | None]
    last_error: Mapped[str | None] = mapped_column(Text)

    # What the server reports about itself, from the last successful discovery.
    server_name: Mapped[str | None] = mapped_column(String(200))
    server_version: Mapped[str | None] = mapped_column(String(80))
    protocol_version: Mapped[str | None] = mapped_column(String(20))
    instructions: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[dict[str, Any]] = mapped_column(default=dict)
    catalog_hash: Mapped[str | None] = mapped_column(String(64))
    last_discovered_at: Mapped[datetime | None]
    discovery_error: Mapped[str | None] = mapped_column(Text)
    tool_count: Mapped[int] = mapped_column(default=0)
    resource_count: Mapped[int] = mapped_column(default=0)
    prompt_count: Mapped[int] = mapped_column(default=0)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ServerSecret(IdMixin, TimestampMixin, Base):
    """A header or environment value an upstream server needs. Never stored in plaintext."""

    __tablename__ = "server_secrets"
    __table_args__ = (UniqueConstraint("server_id", "kind", "name"),)

    server_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(128))
    backend: Mapped[str] = mapped_column(String(16))
    # kms and local backends: the ciphertext. secretsmanager: the secret's ARN.
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    secret_arn: Mapped[str | None] = mapped_column(String(400))
    key_ref: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class Tool(IdMixin, Base):
    """A tool an upstream server advertises, as of its last discovery."""

    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("server_id", "name"),)

    server_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output_schema: Mapped[dict[str, Any] | None]
    annotations: Mapped[dict[str, Any]] = mapped_column(default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64))
    # An operator can take a tool out of the gateway without touching any policy.
    enabled: Mapped[bool] = mapped_column(default=True)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    changed_at: Mapped[datetime | None]
    # Set when a discovery no longer finds the tool; kept so history still reads well.
    removed_at: Mapped[datetime | None]


class Resource(IdMixin, Base):
    """A resource or resource template an upstream server advertises."""

    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("server_id", "uri"),)

    server_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    uri: Mapped[str] = mapped_column(String(1000))
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    mime_type: Mapped[str | None] = mapped_column(String(120))
    is_template: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    removed_at: Mapped[datetime | None]


class Prompt(IdMixin, Base):
    """A prompt an upstream server advertises."""

    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("server_id", "name"),)

    server_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    arguments: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    removed_at: Mapped[datetime | None]


class ServerVersion(IdMixin, Base):
    """One observed change of a server's reported version or of its catalog."""

    __tablename__ = "server_versions"
    __table_args__ = (Index("ix_server_versions_server_id_created_at", "server_id", "created_at"),)

    server_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    server_version: Mapped[str | None] = mapped_column(String(80))
    protocol_version: Mapped[str | None] = mapped_column(String(20))
    catalog_hash: Mapped[str] = mapped_column(String(64))
    tool_count: Mapped[int] = mapped_column(default=0)
    resource_count: Mapped[int] = mapped_column(default=0)
    prompt_count: Mapped[int] = mapped_column(default=0)
    tools_added: Mapped[list[str]] = mapped_column(default=list)
    tools_removed: Mapped[list[str]] = mapped_column(default=list)
    tools_changed: Mapped[list[str]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class HealthCheck(IdMixin, Base):
    """The result of one health check (kept for a week, for uptime and latency charts)."""

    __tablename__ = "health_checks"
    __table_args__ = (
        Index("ix_health_checks_server_id_checked_at", "server_id", "checked_at"),
        # Retention deletes by age across every server.
        Index("ix_health_checks_checked_at", "checked_at"),
    )

    server_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    ok: Mapped[bool]
    latency_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(server_default=func.now())
