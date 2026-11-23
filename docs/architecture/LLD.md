# Low-level design

How the pieces described in the [HLD](HLD.md) are built: modules, tables, cache keys,
algorithms and the API surface. Paths are under `apps/api/src/mcphub/` unless stated.

## 1. Modules and layering

```text
mcphub/
├── main.py           app factory: middleware, routers, the /mcp mount, lifespan
├── worker.py         scheduler: health checks, discovery, retention (leader-elected)
├── cli.py            typer CLI: migrate, user, demo, discover, openapi
├── core/             config, logging, errors, request context, security, ids, rate limits, metrics
├── db/               engine, session factory, declarative base, migration runner
├── models/           SQLAlchemy models, one module per aggregate
├── migrations/       Alembic revisions (run in-process under an advisory lock)
├── schemas/          Pydantic request and response models
├── repositories/     the only code that touches the database
├── policy/           pure policy engine: patterns, decisions, constraints, redaction
├── catalog/          pure catalog logic: fingerprints and version diffs
├── upstream/         talking to upstream MCP servers: transports, pooled connections, probes
├── gateway/          the MCP server clients talk to: SDK server, auth wrapper, audit writer
├── integrations/     AWS clients and the secret vaults (KMS, Secrets Manager, local)
├── services/         business rules, transactions, cache invalidation
├── api/              routes and dependencies
└── demo/             the demo seeder and the demo MCP servers
```

| Layer               | May import                                                            | Must not                                         |
| ------------------- | --------------------------------------------------------------------- | ------------------------------------------------ |
| `api/routes`        | schemas, services, `api/deps`                                         | open sessions, call repositories or Valkey       |
| `gateway/server.py` | services, `gateway/*`                                                 | touch repositories (it is a route layer for MCP) |
| `services`          | repositories, `policy`, `catalog`, `upstream`, `integrations`, `core` | import FastAPI                                   |
| `repositories`      | models, `db`                                                          | commit, or call a service                        |
| `policy`, `catalog` | `core` only                                                           | perform I/O; they are pure and unit tested       |

Services own their transactions: a write method commits once; routes never commit.

## 2. Data model

All primary keys are UUIDv7 (time-ordered). Value sets are `text` with `CHECK`
constraints. Timestamps are `timestamptz`. Full column lists are in
[data-model.md](data-model.md); the essentials:

| Table                  | Purpose                                                                                     | Hot indexes                                                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `users`                | Dashboard accounts, role, lockout, session version                                          | unique `email` (citext)                                                                                                         |
| `servers`              | Catalog entries: transport, URL or command, health, discovery metadata, `config_version`    | unique `slug`                                                                                                                   |
| `server_secrets`       | Header or env secrets: ciphertext or Secrets Manager ARN, never plaintext                   | unique `(server_id, kind, name)`                                                                                                |
| `tools`                | Discovered tools with schemas, annotations, fingerprint, admin `enabled` flag, soft removal | unique `(server_id, name)`                                                                                                      |
| `resources`, `prompts` | Discovered resources (and templates) and prompts                                            | unique per server                                                                                                               |
| `server_versions`      | One row per observed change in server version or catalog fingerprint, with the diff         | `(server_id, created_at)`                                                                                                       |
| `health_checks`        | Result of every health check (retention 7 days)                                             | `(server_id, checked_at)`                                                                                                       |
| `clients`              | Callers of the gateway: status, default effect, separator, rate limit, `policy_version`     | unique `slug`                                                                                                                   |
| `client_keys`          | API keys: prefix, HMAC-SHA256 of the secret, expiry, revocation                             | unique `prefix`, `client_id`                                                                                                    |
| `policy_rules`         | Pattern, effect, constraints, rate limit, redaction paths                                   | unique `(client_id, pattern)`                                                                                                   |
| `tool_calls`           | The audit log (retention `AUDIT_RETENTION_DAYS`)                                            | `(created_at, id)`, `(client_id, created_at)`, `(server_id, created_at)`, `(status, created_at)`, GIN on a generated `tsvector` |
| `audit_events`         | Administrative changes: who changed which server, secret, client, rule, key or user         | `(created_at)`                                                                                                                  |

## 3. Policy engine (`policy/`)

### Patterns and specificity

A rule pattern is `<server>.<tool>` with `*` and `?` wildcards (`fnmatch` semantics on
the namespaced name): `tickets.create_ticket`, `tickets.get_*`, `tickets.*`, `*`. For a
tool, every matching rule is collected and the most specific wins:

```text
specificity(pattern) = (has no wildcard, count of literal characters)
```

So an exact name beats any wildcard, and among wildcards the longer literal wins
(`tickets.get_*` beats `tickets.*` beats `*`). Two rules of equal specificity resolve to
`deny`. When nothing matches, the client's `default_effect` applies (`deny` for new
clients: least privilege). A disabled tool, a disabled server, or a removed tool is never
visible, whatever the rules say.

### Argument constraints

Each rule carries an optional list of constraints on argument paths (`priority`,
`filters.status`):

| Rule         | Passes when                                                                                                                   |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `equals`     | the value equals `value`                                                                                                      |
| `one_of`     | the value is one of `values`                                                                                                  |
| `pattern`    | the value is a string fully matching the regular expression `value` (at most 200 characters, compiled when the rule is saved) |
| `max_length` | the string (or list) is at most `value` long                                                                                  |
| `range`      | the number is within `min` and `max` (either may be omitted)                                                                  |
| `forbidden`  | the argument is absent                                                                                                        |

A missing argument passes every rule except `equals` (a pinned value must be present).
Violations are returned to the client as a tool error listing each violation, so a model
can correct its call.

### Redaction

Before a call is recorded, arguments are copied with redaction applied: every path in the
rule's `redact` list becomes `"[redacted]"`, and so does any key anywhere whose name
contains `password`, `secret`, `token`, `api_key`, `apikey`, `authorization` or
`credential`. Strings longer than 2,000 characters are truncated, and a record larger
than `AUDIT_MAX_ARGUMENT_BYTES` keeps only its top-level keys. A client can also turn off
argument recording entirely (`record_arguments = false`).

## 4. Gateway (`gateway/`)

- `server.py` builds the SDK's low-level `Server("mcphub")` with `on_list_tools` and
  `on_call_tool`. Handlers read the authenticated client from `ctx.request.state` (the
  Starlette request the SDK attaches to every message) and delegate to `GatewayService`.
- `asgi.py` is the ASGI app mounted at `/mcp`: it authenticates the bearer key, stores the
  resolved client on the request scope, and hands the request to the SDK's
  `StreamableHTTPSessionManager(stateless=True, json_response=True)`.
- `audit_writer.py` buffers call records in an `asyncio.Queue` (bounded, 10,000) and a
  background task inserts them in batches (every 500 ms or 200 rows), updating
  `client_keys.last_used_at` and `clients.last_seen_at` for the batch in the same
  transaction. Shutdown drains the queue. If the database is down the batch is retried;
  when the queue is full, new records are dropped and counted
  (`mcphub_audit_dropped_total`) rather than slowing calls.

### Errors returned to clients

| Situation                                | Response                                     | Audit status        |
| ---------------------------------------- | -------------------------------------------- | ------------------- |
| Unknown, hidden or denied tool           | JSON-RPC error `-32602` "Unknown tool"       | `denied`            |
| Arguments fail the input schema          | tool result with `isError: true`             | `invalid_arguments` |
| Arguments violate a constraint           | tool result with `isError: true`             | `blocked`           |
| Rate limit exceeded                      | tool result with `isError: true`, retry hint | `rate_limited`      |
| Upstream unreachable or protocol failure | tool result with `isError: true`             | `upstream_error`    |
| Upstream exceeded the server's timeout   | tool result with `isError: true`             | `timeout`           |
| Upstream returned `isError: true`        | passed through                               | `tool_error`        |
| Success                                  | passed through                               | `ok`                |

## 5. Upstream connections (`upstream/`)

- `transports.py` turns a server and its decrypted secrets into an SDK transport:
  `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=...))` or
  `stdio_client(StdioServerParameters(command, args, env))`. It enforces the stdio
  allowlist and the URL guard.
- `pool.py` keeps one `UpstreamConnection` per server id. A connection is a background
  task that enters the SDK `Client(transport, mode="auto", cache=None)` and holds it open
  until closed, because the SDK's task groups must be entered and exited by the same task.
  Calls are multiplexed on the open session. A connection whose task ended (transport
  failure) is replaced on the next call; a call that fails before reaching the upstream is
  retried once on a fresh connection, a call that fails after is not (it may have had
  side effects). Connections idle for `UPSTREAM_IDLE_TIMEOUT_S` are closed, and a change of
  the server's `config_version` (URL, command, headers, env or secrets) closes the old one.
- `guard.py` judges upstream targets: metadata and link-local always refused, private ranges and `localhost` refused unless allow-listed (checked on the URL as written and on every address a host name resolves to), stdio commands against the allow-list. `UpstreamConnection` also refuses results over `UPSTREAM_MAX_RESULT_BYTES` and masks the secrets it injected in the results it relays.
- `probe.py` opens a short-lived connection for discovery and health checks, separate from
  the pool, so a probe never interferes with live traffic.

## 6. Catalog (`catalog/`)

- `fingerprint(tool)` is the SHA-256 of the canonical JSON of name, title, description,
  input schema, output schema and annotations.
- `catalog_hash(server)` hashes the sorted tool fingerprints plus resource URIs and prompt
  names.
- `diff(previous, current)` returns added, removed and changed tool names. A discovery run
  writes a `server_versions` row only when the server version or the catalog hash changed.

## 7. Cache keys (Valkey)

| Key                            | Value                                                               | TTL            | Invalidated by                                                  |
| ------------------------------ | ------------------------------------------------------------------- | -------------- | --------------------------------------------------------------- |
| `mcphub:key:<prefix>`          | key id, client id, HMAC, expiry                                     | 300 s          | key revoke, client suspend or delete                            |
| `mcphub:catalog:gen`           | integer generation                                                  | none           | `INCR` on any catalog or server change                          |
| `mcphub:view:<client_id>`      | compiled view + the generation and policy version it was built from | 120 s          | rule change, client change (`DEL`); generation mismatch on read |
| `mcphub:rl:<scope>:<window>`   | fixed-window counter                                                | window + 1 s   | expiry                                                          |
| `mcphub:session:revoked:<jti>` | marker                                                              | token lifetime | expiry                                                          |
| `mcphub:lease:scheduler`       | worker id                                                           | 30 s, renewed  | expiry                                                          |
| `mcphub:stats:<range>`         | overview JSON                                                       | 30 s           | expiry                                                          |

## 8. Worker

The leader loop runs every 5 seconds:

1. Servers due a health check (`last_check_at` older than `HEALTH_INTERVAL_S`) are probed,
   at most 8 at a time. A status change is recorded as an administrative event.
2. Servers due discovery (`last_discovered_at` older than the server's
   `refresh_interval_s`) are rediscovered.
3. Once an hour: delete `tool_calls` older than `AUDIT_RETENTION_DAYS` and
   `health_checks` older than 7 days, in batches of 5,000 rows.

SIGTERM stops the loop after the current round and releases the lease.

## 9. API surface

All management routes are under `/api/v1`, take a session cookie or a bearer session token,
and answer errors as `{"error": {"code", "message", "request_id", "details?"}}`. Lists take
`limit` (at most 200) and `offset`; the call log uses an opaque keyset `cursor`.

| Area          | Endpoints                                                                                                                                                                                                                                                                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth          | `POST /auth/setup` (first account), `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me`, `POST /auth/password`                                                                                                                                                                                               |
| Users (admin) | `GET /users`, `POST /users`, `PATCH /users/{id}`                                                                                                                                                                                                                                                                                   |
| Servers       | `GET /servers`, `POST /servers`, `GET/PATCH/DELETE /servers/{slug}`, `POST /servers/{slug}/refresh`, `POST /servers/{slug}/check`, `GET /servers/{slug}/tools`, `PATCH /servers/{slug}/tools/{name}`, `GET /servers/{slug}/resources`, `GET /servers/{slug}/prompts`, `GET /servers/{slug}/versions`, `GET /servers/{slug}/health` |
| Secrets       | `GET /servers/{slug}/secrets`, `PUT /servers/{slug}/secrets`, `DELETE /servers/{slug}/secrets/{id}`                                                                                                                                                                                                                                |
| Catalog       | `GET /tools` (search across servers)                                                                                                                                                                                                                                                                                               |
| Clients       | `GET /clients`, `POST /clients`, `GET/PATCH/DELETE /clients/{slug}`, `GET/POST /clients/{slug}/keys`, `DELETE /clients/{slug}/keys/{id}`, `GET/POST /clients/{slug}/rules`, `PATCH/DELETE /clients/{slug}/rules/{id}`, `GET /clients/{slug}/tools` (effective access), `POST /clients/{slug}/simulate`                             |
| Keys          | `GET /keys` (every client's keys with their client and state, never the secrets)                                                                                                                                                                                                                                                   |
| Playground    | `POST /playground/call` (a real call through the gateway pipeline as a chosen client, audited with the operator's name)                                                                                                                                                                                                            |
| Audit         | `GET /calls`, `GET /calls/{id}`, `GET /calls/export` (CSV)                                                                                                                                                                                                                                                                         |
| Usage         | `GET /stats/overview?range=24h                                                                                                                                                                                                                                                                                                     | 7d  | 30d` |
| Activity      | `GET /activity`                                                                                                                                                                                                                                                                                                                    |
| System        | `GET /system/info`, `/livez`, `/readyz`, `/metrics`                                                                                                                                                                                                                                                                                |
| Gateway       | `POST /mcp` (and `GET`, `DELETE` for handshake-era clients)                                                                                                                                                                                                                                                                        |

## 10. Metrics

| Metric                                                               | Labels                |
| -------------------------------------------------------------------- | --------------------- |
| `mcphub_http_requests_total`, `mcphub_http_request_duration_seconds` | method, route, status |
| `mcphub_tool_calls_total`                                            | server, status        |
| `mcphub_tool_call_duration_seconds`                                  | server                |
| `mcphub_upstream_connections`                                        | state (gauge)         |
| `mcphub_audit_written_total`, `mcphub_audit_dropped_total`           | none                  |
| `mcphub_view_cache_total`                                            | result                |
| `mcphub_health_checks_total`                                         | status                |
| `mcphub_discovery_runs_total`                                        | outcome               |
