# Contributing

Thanks for helping improve Euron MCPHub. This guide covers the workflow, the bar a change has to
clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak, so we can agree on the
  approach before you invest time.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. See [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Development setup

Requirements: Docker with Compose v2, Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node.js 22
with pnpm 9 (`corepack enable`).

```bash
make up          # Postgres, Valkey, the AWS emulator (provisioned by Terraform), api, worker, web, demo servers
make demo        # five servers, five clients and a fortnight of real gateway calls
make test        # unit tests for the API (pytest) and the web app (Vitest)
```

[docs/guides/quickstart-local.md](docs/guides/quickstart-local.md) walks through the local stack.

### A faster loop without the full stack

```bash
scripts/test-deps.sh                                   # Postgres (5455), Valkey (6415), Floci (4615)
cd apps/api && uv run uvicorn mcphub.main:create_app --factory --port 8150   # with MIGRATE_ON_BOOT=true
uv run mcphub-demo serve                               # the demo MCP servers on 9150 to 9152
pnpm --filter @mcphub/web dev                          # the dashboard on http://localhost:3150
```

For servers on your own machine, set `UPSTREAM_ALLOW_PRIVATE=true` (laptops only).

## Before you open a pull request

Each of these must pass:

```bash
make lint typecheck test
make test-integration                  # the API and gateway against real Postgres, Valkey and the AWS emulator
make e2e                               # when you touched a user flow, the web app or infrastructure
make tf-validate tf-lint tf-security   # when you touched infra/terraform
make sanitize                          # no credentials, account ids or resource ids
```

## Conventions

**Layers (api).** Routes declare the URL, the request and response models and the access dependency,
nothing else. Services hold the business rules, transactions and cache invalidation. Repositories are
the only code that issues SQL. The policy engine and the catalog logic are pure, so they are unit tested
without a database. [docs/architecture/LLD.md](docs/architecture/LLD.md) has the rules for each layer.

**Secrets never travel.** No schema, log line, audit row, export or error message contains a secret value
or a client key. New log fields and recorded text go through `policy/scrub.py`.

**The gateway fails closed.** A tool a client may not use looks like a tool that does not exist. A new
check goes before the call leaves the gateway, and every outcome (allowed or not) is recorded.

**The egress policy is a security boundary.** A change to `upstream/guard.py` needs a test for the refused
case and an update to the [threat model](docs/architecture/threat-model.md).

**Configuration is validated.** A new environment variable is declared in
`apps/api/src/mcphub/core/config.py` and documented in
[docs/guides/configuration.md](docs/guides/configuration.md) in the same PR. Settings that matter for
security are enforced at boot when `APP_ENV=production`.

**Database changes are new migrations.** `uv run alembic revision -m "describe it"` in `apps/api`. Never
edit an applied migration.

**Errors use the envelope.** Raise the classes in `core/errors.py`; the handlers turn them into
`{"error": {"code", "message", "request_id"}}`.

**Comments explain why.** The code says what it does. Comments are for the constraint, the incident, or the
trade-off that made it this way.

**Style.** ruff (lint and format) and mypy in strict mode for Python; ESLint, Prettier and strict
TypeScript for the web app.

## Writing style

Commits, pull request text, documentation, code comments and user interface copy use commas, colons,
parentheses, the word "to" or a plain hyphen where other writing would use a long dash. The commit hooks
and `make sanitize` reject typographic dashes.

Commit messages and pull request descriptions describe the change. Do not add authorship trailers, tool
footers or session links; the commit author is the person who wrote the change.

## Commit messages

Imperative mood with a scope: `gateway: refuse a call whose result is over the limit`,
`web: show the rule that decided each tool`. Explain the _why_ in the body when it is not obvious. Several
small commits that each build and pass tests are easier to review than one large one.

## Architecture decisions

A change that alters a documented decision (the gateway protocol mode, the policy model, secrets, the
egress policy, deployment topology) needs a new ADR in [docs/architecture/adr/](docs/architecture/adr/),
using the existing ones as a template.
