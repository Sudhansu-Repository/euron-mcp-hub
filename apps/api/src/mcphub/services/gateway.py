"""The gateway pipeline: authenticate a client key, resolve its view, and run tool calls.

Every call, whatever its outcome, produces exactly one call log record:

    client rate limit -> find the tool in the client's view -> input schema ->
    argument constraints -> rule rate limit -> upstream call

The checks run in that order, cheapest first, and each failure is reported in the shape
MCP clients expect: an unknown or hidden tool is a protocol error (`-32602`), everything
else is a tool result with `isError: true`, so a model can read why and correct itself.
"""

from __future__ import annotations

import base64
import functools
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import mcp_types as types
from jsonschema import SchemaError
from jsonschema.validators import validator_for
from mcp import MCPError
from mcp_types import INVALID_PARAMS
from redis.exceptions import RedisError

from mcphub.core import metrics
from mcphub.core.errors import ForbiddenError, ServiceUnavailableError, UnauthorizedError
from mcphub.core.logging import get_logger
from mcphub.core.security import parse_api_key, verify_api_key_secret
from mcphub.core.text import truncate
from mcphub.models.enums import CallSource, CallStatus
from mcphub.policy import constraints, naming
from mcphub.policy.redaction import redact
from mcphub.policy.scrub import scrub_patterns
from mcphub.repositories.catalog import CatalogRepository
from mcphub.repositories.clients import ClientRepository, KeyRepository, RuleRepository
from mcphub.services import cache as cache_keys
from mcphub.services.call_log import CallRecord
from mcphub.services.container import Container
from mcphub.services.specs import load_spec
from mcphub.services.views import ClientView, ViewTool, as_uuid, compile_view, constraints_of
from mcphub.upstream.spec import UpstreamError, UpstreamTimeoutError

log = get_logger("mcphub.gateway")

TOOLS_PAGE_SIZE = 500
_MAX_SCHEMA_ERRORS = 5
_UNKNOWN_TOOL = "Unknown tool, or not permitted for this client."


@dataclass(frozen=True, slots=True)
class CallContext:
    """Where a call came from, for the call log."""

    key_id: uuid.UUID | None = None
    source: CallSource = CallSource.GATEWAY
    actor_user_id: uuid.UUID | None = None
    request_id: str | None = None
    protocol_version: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """What a call produced: a result for the client (or a protocol error) and its record."""

    result: types.CallToolResult | None
    error: MCPError | None
    record: CallRecord

    def unwrap(self) -> types.CallToolResult:
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise RuntimeError("a call outcome carries either a result or an error")
        return self.result


def error_result(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], is_error=True
    )


class _Validators:
    """Compiled JSON Schema validators by tool fingerprint (a changed tool gets a new one)."""

    def __init__(self, size: int = 1024) -> None:
        self._size = size
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, fingerprint: str, schema: dict[str, Any]) -> Any:
        validator = self._cache.get(fingerprint)
        if validator is None:
            cls = validator_for(schema)
            try:
                cls.check_schema(schema)
            except SchemaError:
                # A server with a malformed schema validates its own input; do not block it.
                validator = False
            else:
                validator = cls(schema)
            self._cache[fingerprint] = validator
            if len(self._cache) > self._size:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(fingerprint)
        return validator


_validators = _Validators()


def schema_errors(tool: ViewTool, arguments: dict[str, Any]) -> list[str]:
    """Readable problems with the arguments under the tool's input schema."""
    validator = _validators.get(tool.fingerprint, tool.input_schema or {"type": "object"})
    if not validator:
        return []
    messages = []
    for error in sorted(validator.iter_errors(arguments), key=lambda e: list(e.path)):
        location = ".".join(str(part) for part in error.path) or "arguments"
        messages.append(f"{location}: {truncate(error.message, 200)}")
        if len(messages) >= _MAX_SCHEMA_ERRORS:
            break
    return messages


def _result_text(result: types.CallToolResult) -> str | None:
    for block in result.content:
        if isinstance(block, types.TextContent):
            return truncate(block.text, 500)
    return None


def _tool_listing(tool: ViewTool) -> types.Tool:
    return types.Tool(
        name=tool.exposed,
        title=tool.title,
        description=tool.description or None,
        input_schema=tool.input_schema or {"type": "object"},
        output_schema=tool.output_schema,
        annotations=(
            types.ToolAnnotations.model_validate(tool.annotations) if tool.annotations else None
        ),
        _meta={"io.euron.mcphub/server": tool.server_slug},
    )


class GatewayService:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.settings = container.settings

    # Authentication and views

    async def authenticate(self, raw_key: str) -> tuple[uuid.UUID, ClientView]:
        """The key id and the client view behind a bearer key; raises 401 or 403."""
        parsed = parse_api_key(raw_key)
        if parsed is None:
            raise UnauthorizedError("That API key is not valid.", code="invalid_api_key")
        prefix, secret = parsed
        try:
            entry, catalog_generation, keys_generation = await self.c.cache.key_lookup(prefix)
            cacheable = True
        except RedisError:
            log.warning("gateway_cache_unavailable")
            entry, catalog_generation, keys_generation, cacheable = None, 0, 0, False
        if entry is None or entry.get("gen") != keys_generation:
            entry = await self._load_key(prefix, keys_generation, cache=cacheable)
        if entry.get("missing") or not verify_api_key_secret(
            secret, entry["hash"], self.settings.api_key_pepper.get_secret_value()
        ):
            raise UnauthorizedError("That API key is not valid.", code="invalid_api_key")
        expires_at = entry.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) <= datetime.now(UTC):
            raise UnauthorizedError("That API key has expired.", code="expired_api_key")
        view = await self.view(
            uuid.UUID(entry["client_id"]), catalog_generation if cacheable else None
        )
        if not view.active:
            raise ForbiddenError("This client is suspended.", code="client_suspended")
        return uuid.UUID(entry["key_id"]), view

    async def _load_key(self, prefix: str, generation: int, *, cache: bool) -> dict[str, Any]:
        async with self.c.db.session() as session:
            found = await KeyRepository(session).by_prefix(prefix)
        if found is None or found[0].revoked_at is not None:
            entry: dict[str, Any] = {"missing": True, "gen": generation}
            ttl = cache_keys.MISSING_KEY_TTL_S
        else:
            key, client = found
            entry = {
                "key_id": str(key.id),
                "client_id": str(client.id),
                "hash": key.secret_hash,
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "gen": generation,
            }
            ttl = cache_keys.KEY_TTL_S
        if cache:
            await self.c.cache.put(cache_keys.api_key_key(prefix), entry, ttl)
        return entry

    async def view(self, client_id: uuid.UUID, catalog_generation: int | None) -> ClientView:
        """The client's compiled view, from the cache when its generations still match."""
        client_generation: int | None = None
        cached: Any = None
        if catalog_generation is not None:
            try:
                client_generation, cached = await self.c.cache.client_state(str(client_id))
            except RedisError:
                catalog_generation = None
        if (
            cached is not None
            and cached.get("catalog_generation") == catalog_generation
            and cached.get("client_generation") == client_generation
        ):
            metrics.VIEW_CACHE.labels("hit").inc()
            return ClientView.from_json(cached)
        metrics.VIEW_CACHE.labels("miss").inc()
        view = await self.build_view(client_id, catalog_generation or 0, client_generation or 0)
        if catalog_generation is not None and client_generation is not None:
            await self.c.cache.put(
                cache_keys.view_key(client_id), view.to_json(), cache_keys.VIEW_TTL_S
            )
        return view

    async def build_view(
        self, client_id: uuid.UUID, catalog_generation: int, client_generation: int
    ) -> ClientView:
        async with self.c.db.session() as session:
            client = await ClientRepository(session).get(client_id)
            if client is None:
                raise UnauthorizedError("That API key is not valid.", code="invalid_api_key")
            rules = await RuleRepository(session).for_client(client_id)
            catalog = await CatalogRepository(session).gateway_tools()
        return compile_view(
            client,
            rules,
            catalog,
            catalog_generation=catalog_generation,
            client_generation=client_generation,
        )

    # tools/list

    def list_tools(self, view: ClientView, cursor: str | None = None) -> types.ListToolsResult:
        start = 0
        if cursor:
            try:
                start = int(base64.urlsafe_b64decode(cursor.encode()).decode())
            except (ValueError, UnicodeDecodeError) as exc:
                raise MCPError(code=INVALID_PARAMS, message="Invalid cursor") from exc
        page = view.tools[start : start + TOOLS_PAGE_SIZE]
        following = start + TOOLS_PAGE_SIZE
        next_cursor = (
            base64.urlsafe_b64encode(str(following).encode()).decode()
            if following < len(view.tools)
            else None
        )
        return types.ListToolsResult(
            tools=[_tool_listing(tool) for tool in page], next_cursor=next_cursor
        )

    # tools/call

    async def call(
        self,
        view: ClientView,
        name: str,
        arguments: dict[str, Any] | None,
        context: CallContext,
    ) -> types.CallToolResult:
        """Run a call for the MCP handler: a result, or an MCPError for unknown tools."""
        return (await self.execute(view, name, arguments, context)).unwrap()

    async def execute(
        self,
        view: ClientView,
        name: str,
        arguments: dict[str, Any] | None,
        context: CallContext,
    ) -> CallOutcome:
        started = time.perf_counter()
        args = dict(arguments or {})
        record = functools.partial(self._record, view, context, started, args)

        if view.rate_limit and not await self._within_limit(
            f"client:{view.client_id}", view.rate_limit
        ):
            message = f"Rate limit exceeded: this client may make {view.rate_limit} calls a minute."
            entry = record(None, name, CallStatus.RATE_LIMITED, message)
            return CallOutcome(error_result(message + " Try again shortly."), None, entry)

        tool = view.find(name)
        if tool is None:
            entry = record(None, name, CallStatus.DENIED, _UNKNOWN_TOOL)
            error = MCPError(code=INVALID_PARAMS, message=f"Unknown tool: {name}")
            return CallOutcome(None, error, entry)

        problems = schema_errors(tool, args)
        if problems:
            message = "The arguments do not match the tool's input schema: " + "; ".join(problems)
            entry = record(tool, name, CallStatus.INVALID_ARGUMENTS, message)
            return CallOutcome(error_result(message), None, entry)

        violations = constraints.check(constraints_of(tool), args)
        if violations:
            message = "This client's policy does not allow these arguments: " + " ".join(
                v.message for v in violations
            )
            entry = record(tool, name, CallStatus.BLOCKED, message)
            return CallOutcome(error_result(message), None, entry)

        if tool.rate_limit and not await self._within_limit(
            f"rule:{tool.rule_id}", tool.rate_limit
        ):
            message = (
                f"Rate limit exceeded: {tool.qualified} allows {tool.rate_limit} calls a minute."
            )
            entry = record(tool, name, CallStatus.RATE_LIMITED, message)
            return CallOutcome(error_result(message + " Try again shortly."), None, entry)

        server_id = uuid.UUID(tool.server_id)
        upstream_started = time.perf_counter()
        try:
            result = await self.c.pool.call_tool(
                server_id,
                tool.config_version,
                functools.partial(load_spec, self.c, server_id),
                tool.name,
                args,
                tool.timeout_s,
            )
        except UpstreamTimeoutError as exc:
            entry = record(
                tool, name, CallStatus.TIMEOUT, exc.message, upstream_started=upstream_started
            )
            return CallOutcome(error_result(exc.message), None, entry)
        except (UpstreamError, ServiceUnavailableError) as exc:
            entry = record(
                tool,
                name,
                CallStatus.UPSTREAM_ERROR,
                exc.message,
                upstream_started=upstream_started,
            )
            return CallOutcome(
                error_result(f"{tool.server_name} is unavailable: {exc.message}"), None, entry
            )

        status = CallStatus.TOOL_ERROR if result.is_error else CallStatus.OK
        entry = record(
            tool,
            name,
            status,
            _result_text(result) if result.is_error else None,
            upstream_started=upstream_started,
            result_bytes=len(result.model_dump_json(by_alias=True, exclude_none=True)),
        )
        return CallOutcome(result, None, entry)

    async def _within_limit(self, key: str, limit: int) -> bool:
        try:
            return (await self.c.limiter.hit(key, limit)).allowed
        except RedisError:
            # Rate limits need Valkey; without it the gateway keeps serving (fail open).
            log.warning("rate_limit_unavailable", key=key.split(":", 1)[0])
            return True

    def _record(
        self,
        view: ClientView,
        context: CallContext,
        started: float,
        arguments: dict[str, Any],
        tool: ViewTool | None,
        requested: str,
        status: CallStatus,
        error: str | None,
        *,
        upstream_started: float | None = None,
        result_bytes: int | None = None,
    ) -> CallRecord:
        now = time.perf_counter()
        if tool is not None:
            server_slug, tool_name, qualified = tool.server_slug, tool.name, tool.qualified
        else:
            parts = naming.split(requested, view.separator)
            server_slug, tool_name = parts if parts else ("", requested)
            qualified = naming.canonical(server_slug, tool_name) if parts else requested
        recorded = (
            redact(
                arguments,
                tool.redact if tool else (),
                max_bytes=self.settings.audit_max_argument_bytes,
            )
            if view.record_arguments
            else None
        )
        latency_ms = int((now - started) * 1000)
        entry = CallRecord(
            client_name=view.client_name,
            server_slug=server_slug[:48],
            tool_name=tool_name[:128],
            qualified_name=qualified[:200],
            status=status.value,
            latency_ms=latency_ms,
            client_id=uuid.UUID(view.client_id),
            client_key_id=context.key_id,
            server_id=uuid.UUID(tool.server_id) if tool else None,
            rule_id=as_uuid(tool.rule_id) if tool else None,
            actor_user_id=context.actor_user_id,
            source=context.source.value,
            error_message=truncate(scrub_patterns(error), 1000) if error else None,
            arguments=recorded,
            result_bytes=result_bytes,
            upstream_ms=int((now - upstream_started) * 1000) if upstream_started else None,
            request_id=context.request_id,
            protocol_version=context.protocol_version,
            user_agent=truncate(context.user_agent, 200) if context.user_agent else None,
        )
        self.c.call_log.submit(entry)
        label = server_slug or "unknown"
        metrics.TOOL_CALLS.labels(label, status.value).inc()
        metrics.TOOL_CALL_DURATION.labels(label).observe(latency_ms / 1000)
        return entry
