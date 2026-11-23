# MCPHub API, gateway and worker

FastAPI service for Euron MCPHub: the management API (`/api/v1`), the MCP gateway (`/mcp`)
and the scheduler worker, from one image with different commands.

```bash
uv sync                                  # Python 3.12 and every dependency
uv run uvicorn mcphub.main:create_app --factory --reload --port 8150
uv run python -m mcphub.worker           # health checks, discovery, retention
uv run mcphub --help                     # CLI: migrations, users, demo data, discovery
uv run mcphub-demo serve                 # the demo MCP servers on 9150 to 9152
uv run pytest tests/unit                 # unit tests, no services needed
```

## Layout

```text
src/mcphub/
├── main.py          app factory: middleware, routers, the /mcp mount, lifespan
├── worker.py        scheduler: health checks, discovery, retention (leader-elected)
├── cli.py           typer CLI
├── core/            config, logging, errors, request context, security, rate limits, metrics
├── db/              engine, session, declarative base, migration runner
├── models/          SQLAlchemy models, one module per aggregate
├── migrations/      Alembic revisions
├── schemas/         Pydantic request and response models
├── repositories/    the only code that touches the database
├── policy/          pure policy engine: patterns, decisions, constraints, redaction
├── catalog/         pure catalog logic: tool fingerprints and version diffs
├── upstream/        upstream MCP connections: transports, the pool, discovery probes
├── gateway/         the MCP server clients call: SDK server, key authentication, audit writer
├── integrations/    AWS clients and the secret vaults (KMS, Secrets Manager, local)
├── services/        business rules, transactions, cache invalidation
├── api/             routes and dependencies (sessions, roles, rate limits)
└── demo/            demo seeder and the demo MCP servers
```

## The rules

| Layer | May import | Must not |
| --- | --- | --- |
| `api/routes`, `gateway/server.py` | schemas, services, `api/deps` | open a session, call a repository or Valkey |
| `services` | repositories, `policy`, `catalog`, `upstream`, `integrations`, `core` | import FastAPI |
| `repositories` | models, `db` | commit, or call a service |
| `policy`, `catalog` | `core` only | do I/O; they are pure and unit tested |

**Transactions.** A service method that writes opens and commits its own transaction.
Routes never commit.

**Errors.** Raise the typed errors in `core/errors.py`. The handlers turn them into the one
envelope every response uses: `{"error": {"code", "message", "request_id", "details?"}}`.

**Secrets.** Upstream secret values enter through `services/secrets.py`, leave only through
`upstream/transports.py`, and are never part of a response model or a log line.

## Tests

| Suite | Needs | Run |
| --- | --- | --- |
| `tests/unit` | nothing | `uv run pytest tests/unit` |
| `tests/integration` | Postgres, Valkey, the AWS emulator | `make test-integration` from the repo root |
