"""Runtime configuration, validated once at boot.

Every setting comes from the environment. `get_settings()` is cached, so the whole process
shares one frozen `Settings`. In production, `production_problems()` refuses development
defaults and reports every problem at once instead of one per restart.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Shipped so `uvicorn` starts with zero configuration on a laptop. Production refuses it.
DEV_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105

AppEnv = Literal["development", "test", "production"]
SecretsBackend = Literal["kms", "secretsmanager", "local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: AppEnv = "development"
    product_name: str = "Euron MCPHub"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "console"] = "json"

    # HTTP
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3150", "http://127.0.0.1:3150"]
    )
    web_url: str = "http://localhost:3150"
    api_url: str = "http://localhost:8150"
    # The address MCP clients are given. Behind a load balancer or a proxy it differs from
    # the API's own address, so it is configurable on its own.
    gateway_url: str | None = None
    max_request_mb: int = Field(default=4, ge=1, le=64)

    # Postgres
    database_url: str = "postgresql+asyncpg://mcphub:mcphub@localhost:5455/mcphub"
    # On AWS the URL carries no password; it is read from this RDS-managed secret for each
    # new connection, so a rotation needs no redeploy.
    database_secret_arn: str | None = None
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_echo: bool = False
    migrate_on_boot: bool = False

    # Valkey (or Redis): key and view caches, rate limits, signed-out sessions, the worker lease
    redis_url: str = "redis://localhost:6415/0"

    # Dashboard sessions and client API keys
    session_secret: SecretStr = SecretStr(DEV_SECRET)
    session_ttl_hours: int = Field(default=168, ge=1, le=2160)
    api_key_pepper: SecretStr = SecretStr(DEV_SECRET)
    cookie_secure: bool = False
    cookie_domain: str | None = None

    # AWS (KMS and Secrets Manager hold upstream secrets)
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None

    # Upstream secrets. "local" encrypts with a key from the environment: for laptops
    # without an emulator, refused in production.
    secrets_backend: SecretsBackend = "local"
    secrets_kms_key_id: str | None = None
    # Secrets Manager names: <prefix>/servers/<server id>/<kind>/<name>
    secrets_name_prefix: str = "mcphub/local"
    secrets_recovery_window_days: int = Field(default=7, ge=0, le=30)
    # 32 random bytes, base64. Unset in development: derived from SESSION_SECRET.
    secrets_local_key: SecretStr | None = None

    # Upstream MCP servers
    # Executables a stdio server may be launched with. Registering a stdio server runs a
    # command on the gateway host, so nothing is allowed unless the operator lists it.
    stdio_allowed_commands: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Egress policy for HTTP servers. Cloud metadata and link-local addresses are always
    # refused. Loopback, private (RFC 1918, unique local, carrier NAT) and reserved
    # ranges are refused too, whether written as an IP address or reached through a name
    # that resolves to one, unless the host matches a pattern here (fnmatch, for example
    # "demo-servers" or "*.corp.example") or UPSTREAM_ALLOW_PRIVATE is on (laptops only).
    upstream_allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    upstream_allow_private: bool = False
    # A tool result larger than this is refused instead of relayed and stored.
    upstream_max_result_bytes: int = Field(default=1_048_576, ge=1024, le=64 * 1024 * 1024)
    upstream_connect_timeout_s: float = Field(default=10.0, gt=0, le=120)
    upstream_idle_timeout_s: int = Field(default=300, ge=10, le=86_400)
    default_call_timeout_s: int = Field(default=30, ge=1, le=600)
    health_interval_s: int = Field(default=30, ge=5, le=3600)
    default_refresh_interval_s: int = Field(default=300, ge=30, le=86_400)
    health_failure_threshold: int = Field(default=3, ge=1, le=20)

    # Gateway
    # When set, a request carrying an Origin header (a browser) must come from one of these.
    gateway_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Audit log of tool calls
    audit_retention_days: int = Field(default=90, ge=1, le=3650)
    audit_max_argument_bytes: int = Field(default=16_384, ge=256, le=1_048_576)
    audit_flush_interval_ms: int = Field(default=500, ge=50, le=10_000)
    audit_batch_size: int = Field(default=200, ge=1, le=5000)
    audit_queue_size: int = Field(default=10_000, ge=100, le=1_000_000)

    # Rate limits for the dashboard, requests per minute
    rate_limit_login: int = Field(default=10, ge=1)

    demo_password: SecretStr | None = None

    @field_validator(
        "cors_origins",
        "stdio_allowed_commands",
        "upstream_allowed_hosts",
        "gateway_allowed_origins",
        mode="before",
    )
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1024 * 1024

    @property
    def public_gateway_url(self) -> str:
        return self.gateway_url or f"{self.api_url.rstrip('/')}/mcp"

    def production_problems(self) -> list[str]:
        """Every reason this configuration is unsafe to serve real users."""
        problems: list[str] = []
        session = self.session_secret.get_secret_value()
        pepper = self.api_key_pepper.get_secret_value()
        for name, value in (("SESSION_SECRET", session), ("API_KEY_PEPPER", pepper)):
            if value == DEV_SECRET or len(value) < 32:
                problems.append(f"{name} must be a random value of at least 32 characters")
        if session == pepper:
            problems.append("SESSION_SECRET and API_KEY_PEPPER must differ")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true behind HTTPS")
        if not self.cors_origins or "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list the web app origins explicitly")
        if self.secrets_backend == "local":
            problems.append("SECRETS_BACKEND must be kms or secretsmanager")
        if self.secrets_backend == "kms" and not self.secrets_kms_key_id:
            problems.append("SECRETS_KMS_KEY_ID is required with SECRETS_BACKEND=kms")
        if self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL points at an emulator; unset it in production")
        if self.upstream_allow_private:
            problems.append(
                "UPSTREAM_ALLOW_PRIVATE is for laptops; list hosts in UPSTREAM_ALLOWED_HOSTS"
            )
        if not self.public_gateway_url.startswith("https://"):
            problems.append("GATEWAY_URL (or API_URL) must be an https:// address")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
