"""Initial schema: users, catalog, secrets, clients, policy, the call log and admin activity.

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from mcphub.models.tool_call import SEARCH_EXPRESSION

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
EMPTY_LIST = sa.text("'[]'::jsonb")
EMPTY_OBJECT = sa.text("'{}'::jsonb")


def _id() -> sa.Column[object]:
    return sa.Column("id", UUID, nullable=False)


def _created() -> sa.Column[object]:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def _updated() -> sa.Column[object]:
    return sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now())


def _fk(column: str, table: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [f"{table}.id"], ondelete=ondelete)


def _one_of(column: str, values: Sequence[str], name: str | None = None) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name or column)


CALL_STATUSES = (
    "ok",
    "tool_error",
    "denied",
    "blocked",
    "invalid_arguments",
    "rate_limited",
    "upstream_error",
    "timeout",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        _id(),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", TS),
        sa.Column("last_login_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        _one_of("role", ("admin", "operator", "viewer")),
    )

    op.create_table(
        "servers",
        _id(),
        sa.Column("slug", sa.String(48), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("command", sa.String(300)),
        sa.Column("args", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("env", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("headers", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column(
            "tags",
            pg.ARRAY(sa.String(40)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("owner", sa.String(120), nullable=False, server_default=""),
        sa.Column("homepage_url", sa.String(500)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("refresh_interval_s", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("health", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_check_at", TS),
        sa.Column("last_healthy_at", TS),
        sa.Column("last_latency_ms", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("server_name", sa.String(200)),
        sa.Column("server_version", sa.String(80)),
        sa.Column("protocol_version", sa.String(20)),
        sa.Column("instructions", sa.Text()),
        sa.Column("capabilities", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("catalog_hash", sa.String(64)),
        sa.Column("last_discovered_at", TS),
        sa.Column("discovery_error", sa.Text()),
        sa.Column("tool_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resource_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        _fk("created_by", "users", "SET NULL"),
        _one_of("transport", ("streamable_http", "stdio")),
        _one_of("health", ("unknown", "healthy", "degraded", "down")),
        # Each transport needs its own way to reach the server.
        sa.CheckConstraint(
            "(transport = 'streamable_http' AND url IS NOT NULL) OR "
            "(transport = 'stdio' AND command IS NOT NULL)",
            name="endpoint",
        ),
        sa.CheckConstraint("timeout_s BETWEEN 1 AND 600", name="timeout_s"),
        sa.CheckConstraint("refresh_interval_s >= 30", name="refresh_interval_s"),
    )

    op.create_table(
        "server_secrets",
        _id(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("backend", sa.String(16), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column("secret_arn", sa.String(400)),
        sa.Column("key_ref", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", UUID),
        sa.Column("updated_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "kind", "name"),
        _fk("server_id", "servers", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        _fk("updated_by", "users", "SET NULL"),
        _one_of("kind", ("header", "env")),
        _one_of("backend", ("kms", "secretsmanager", "local")),
        sa.CheckConstraint("ciphertext IS NOT NULL OR secret_arn IS NOT NULL", name="value"),
    )

    op.create_table(
        "tools",
        _id(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_schema", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("output_schema", pg.JSONB()),
        sa.Column("annotations", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("changed_at", TS),
        sa.Column("removed_at", TS),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "name"),
        _fk("server_id", "servers", "CASCADE"),
    )

    op.create_table(
        "resources",
        _id(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("uri", sa.String(1000), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("mime_type", sa.String(120)),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("removed_at", TS),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "uri"),
        _fk("server_id", "servers", "CASCADE"),
    )

    op.create_table(
        "prompts",
        _id(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("arguments", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("first_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("removed_at", TS),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "name"),
        _fk("server_id", "servers", "CASCADE"),
    )

    op.create_table(
        "server_versions",
        _id(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("server_version", sa.String(80)),
        sa.Column("protocol_version", sa.String(20)),
        sa.Column("catalog_hash", sa.String(64), nullable=False),
        sa.Column("tool_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resource_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tools_added", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("tools_removed", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("tools_changed", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("server_id", "servers", "CASCADE"),
    )
    op.create_index(
        "ix_server_versions_server_id_created_at", "server_versions", ["server_id", "created_at"]
    )

    op.create_table(
        "health_checks",
        _id(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("checked_at", TS, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        _fk("server_id", "servers", "CASCADE"),
    )
    op.create_index(
        "ix_health_checks_server_id_checked_at", "health_checks", ["server_id", "checked_at"]
    )
    # Retention deletes by age across every server.
    op.create_index("ix_health_checks_checked_at", "health_checks", ["checked_at"])

    op.create_table(
        "clients",
        _id(),
        sa.Column("slug", sa.String(48), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("default_effect", sa.String(8), nullable=False, server_default="deny"),
        sa.Column("tool_separator", sa.String(4), nullable=False, server_default="."),
        sa.Column("rate_limit_per_minute", sa.Integer()),
        sa.Column("record_arguments", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", UUID),
        sa.Column("last_seen_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        _fk("created_by", "users", "SET NULL"),
        _one_of("status", ("active", "suspended")),
        _one_of("default_effect", ("allow", "deny")),
        _one_of("tool_separator", (".", "__")),
        sa.CheckConstraint(
            "rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0", name="rate_limit"
        ),
    )

    op.create_table(
        "client_keys",
        _id(),
        sa.Column("client_id", UUID, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("created_by", UUID),
        _created(),
        sa.Column("last_used_at", TS),
        sa.Column("expires_at", TS),
        sa.Column("revoked_at", TS),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prefix"),
        _fk("client_id", "clients", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
    )
    op.create_index("ix_client_keys_client_id", "client_keys", ["client_id"])

    op.create_table(
        "policy_rules",
        _id(),
        sa.Column("client_id", UUID, nullable=False),
        sa.Column("pattern", sa.String(260), nullable=False),
        sa.Column("effect", sa.String(8), nullable=False),
        sa.Column("constraints", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("rate_limit_per_minute", sa.Integer()),
        sa.Column("redact", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("description", sa.String(300), nullable=False, server_default=""),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "pattern"),
        _fk("client_id", "clients", "CASCADE"),
        _one_of("effect", ("allow", "deny")),
        sa.CheckConstraint(
            "rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0", name="rate_limit"
        ),
    )

    op.create_table(
        "tool_calls",
        _id(),
        sa.Column("client_id", UUID),
        sa.Column("client_key_id", UUID),
        sa.Column("server_id", UUID),
        sa.Column("rule_id", UUID),
        sa.Column("actor_user_id", UUID),
        sa.Column("client_name", sa.String(120), nullable=False),
        sa.Column("server_slug", sa.String(48), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("qualified_name", sa.String(200), nullable=False),
        sa.Column("source", sa.String(12), nullable=False, server_default="gateway"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("arguments", pg.JSONB()),
        sa.Column("result_bytes", sa.Integer()),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upstream_ms", sa.Integer()),
        sa.Column("request_id", sa.String(64)),
        sa.Column("protocol_version", sa.String(20)),
        sa.Column("user_agent", sa.String(200)),
        sa.Column("search", pg.TSVECTOR(), sa.Computed(SEARCH_EXPRESSION, persisted=True)),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("client_id", "clients", "SET NULL"),
        _fk("client_key_id", "client_keys", "SET NULL"),
        _fk("server_id", "servers", "SET NULL"),
        _fk("rule_id", "policy_rules", "SET NULL"),
        _fk("actor_user_id", "users", "SET NULL"),
        _one_of("status", CALL_STATUSES),
        _one_of("source", ("gateway", "playground")),
    )
    # The call log pages newest first by (created_at, id); filters narrow by one dimension.
    op.create_index("ix_tool_calls_created_at_id", "tool_calls", ["created_at", "id"])
    op.create_index("ix_tool_calls_client_id_created_at", "tool_calls", ["client_id", "created_at"])
    op.create_index("ix_tool_calls_server_id_created_at", "tool_calls", ["server_id", "created_at"])
    op.create_index("ix_tool_calls_status_created_at", "tool_calls", ["status", "created_at"])
    op.create_index("ix_tool_calls_search", "tool_calls", ["search"], postgresql_using="gin")

    op.create_table(
        "audit_events",
        _id(),
        sa.Column("actor_user_id", UUID),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64)),
        sa.Column("target_name", sa.String(200)),
        sa.Column("details", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("actor_user_id", "users", "SET NULL"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    for table in (
        "audit_events",
        "tool_calls",
        "policy_rules",
        "client_keys",
        "clients",
        "health_checks",
        "server_versions",
        "prompts",
        "resources",
        "tools",
        "server_secrets",
        "servers",
        "users",
    ):
        op.drop_table(table)
