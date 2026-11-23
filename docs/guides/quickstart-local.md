# Quickstart: run MCPHub on your laptop

Everything runs in Docker Compose. No cloud account, no API key, no internet beyond pulling images.

## Prerequisites

- Docker with Compose v2 (Docker Desktop, Colima or Rancher Desktop) and about 4 GB of free memory
- `make` and `openssl`
- For development only: Python 3.12 with `uv`, Node 22 with `pnpm` 9

## Start it

```bash
make up      # builds the images, starts the stack, applies the Terraform against the AWS emulator
make demo    # seeds five servers, five clients and two weeks of real gateway calls
```

The first `make up` takes a few minutes (image builds, Terraform providers). `make env` runs first and
writes `deploy/compose/.env` with random local-only secrets, including the password of the demo
accounts: `grep DEMO deploy/compose/.env`.

| What             | Where                                              |
| ---------------- | -------------------------------------------------- |
| Dashboard        | http://localhost:3150                              |
| API reference    | http://localhost:8150/docs                         |
| MCP gateway      | http://localhost:8150/mcp                          |
| Demo MCP servers | ports 9150 (notes), 9151 (toolbox), 9152 (tickets) |

`make demo` prints the three demo logins (admin, operator, viewer) and a client key for the Support
copilot client together with a ready-to-run `curl`.

## Try the gateway

```bash
KEY=mch_...   # printed by make demo
curl -s http://localhost:8150/mcp \
  -H "authorization: Bearer $KEY" \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -H "mcp-protocol-version: 2025-11-25" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

You see only the tools that client's policy allows, named `server.tool`. Point an MCP client at the
same URL with the key as a bearer token: the **Connect** tab of any client in the dashboard has
snippets for the command line, IDEs, Python and the MCP Inspector.

## Use your own server

In the dashboard choose **Servers, Connect a server**. A server on your machine is on a private
address, so allow it first: add the host to `MCPHUB_UPSTREAM_ALLOWED_HOSTS` in
`deploy/compose/.env` (for example `host.docker.internal`) and run `make up` again. Public servers
need nothing.

## Stop it

```bash
make down    # stops everything and deletes the volumes (the Terraform provider cache is kept)
```

## Develop against it

```bash
cd apps/api && uv sync && uv run uvicorn mcphub.main:create_app --factory --reload --port 8150
pnpm install && pnpm dev          # the dashboard on 3150
make test                          # unit tests
make test-integration              # starts Postgres, Valkey and the emulator, then runs the suite
```
