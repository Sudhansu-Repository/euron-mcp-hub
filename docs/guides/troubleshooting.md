# Troubleshooting

## `make up`

| Symptom                                                                             | Cause and fix                                                                                                                                                                             |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run make env first`                                                                | `deploy/compose/.env` is missing: `make env` writes it (random local secrets).                                                                                                            |
| The `terraform` container fails with `unexpected EOF` from `releases.hashicorp.com` | A network flake while downloading providers. Run `make up` again; the provider cache volume keeps what was fetched.                                                                       |
| A port is already in use                                                            | Another stack holds it. Run one stack at a time, or override `MCPHUB_WEB_PORT`, `MCPHUB_API_PORT`, `MCPHUB_PG_PORT`, `MCPHUB_REDIS_PORT` or `MCPHUB_FLOCI_PORT` in `deploy/compose/.env`. |
| `Cannot connect to the Docker daemon`                                               | Start Docker (`colima start` on a Mac without Docker Desktop).                                                                                                                            |
| The first start is slow                                                             | Images build and Terraform applies against the emulator; later starts reuse both.                                                                                                         |

## Servers

| Symptom                                                   | Cause and fix                                                                                                                |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| "is on a private or local network" when registering       | The egress policy. Add the host to `UPSTREAM_ALLOWED_HOSTS` (compose: `MCPHUB_UPSTREAM_ALLOWED_HOSTS`).                      |
| "Link-local and cloud metadata addresses are not allowed" | Never allowed, by design. Use the server's real address.                                                                     |
| "The server refused the gateway's credentials (HTTP 401)" | The header secret is missing or wrong: set it on the server's Secrets tab, then Refresh.                                     |
| "stdio servers are disabled"                              | Set `STDIO_ALLOWED_COMMANDS` to the executables the gateway may launch. Not available on the AWS deployment.                 |
| A server is `down` but works in a browser                 | The gateway reaches it from its own network. Check the address from inside the `api` container and that the host is allowed. |
| Tools missing after a server upgrade                      | Click Refresh (the worker rediscovers every few minutes). Check the Versions tab for what changed.                           |

## Clients and the gateway

| Symptom                                               | Cause and fix                                                                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `401` from `/mcp`                                     | The key is wrong, expired or revoked. Keys look like `mch_<10 characters>_<43 characters>`.                                                                        |
| `403 client_suspended`                                | The client is suspended on its page.                                                                                                                               |
| `tools/list` is empty                                 | A new client denies everything until a rule allows something. Open Tool access and allow a tool, or a whole server.                                                |
| "Unknown tool" for a tool that exists                 | The client's policy does not allow it (denied tools look unknown on purpose), or the server's tool is switched off. Use the Dry run tab to see which rule decides. |
| A call is refused with a policy message               | An argument broke a constraint. The message names the argument and the rule.                                                                                       |
| "Rate limit exceeded"                                 | The client or the rule's calls per minute. Raise it on the client or the rule.                                                                                     |
| A tool result is "larger than the gateway's limit"    | Raise `UPSTREAM_MAX_RESULT_BYTES`, or change what the tool returns.                                                                                                |
| An agent's model API rejects dot-separated tool names | Set the client's tool names to `server__tool`.                                                                                                                     |

## Dashboard

| Symptom                       | Cause and fix                                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------------- |
| "Cannot reach the MCPHub API" | The API is down, or `API_URL` of the web container does not match the address the browser uses.         |
| Signed out on every reload    | The browser blocks the cookie (a different site than the API), or `COOKIE_SECURE=true` over plain HTTP. |
| `Cross-site request blocked`  | A cookie-authenticated write from an origin not in `CORS_ORIGINS`. Add the dashboard's origin.          |
| "Too many sign-in attempts"   | The per-address limit or the account lockout. Wait a minute (or fifteen for a locked account).          |

## Secrets

| Symptom                                                            | Cause and fix                                                                                                                                         |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| "A secret for this server could not be read from the secret store" | KMS or Secrets Manager is unreachable or the key is wrong. Check `/readyz` (`secrets`), the key id and, locally, that the Floci container is healthy. |
| Secrets stopped working after changing `SECRETS_BACKEND`           | Each secret remembers its backend and stays readable while that backend is configured; switch back, or set the values again.                          |

## Tests

| Symptom                          | Cause and fix                                                                                                 |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Integration tests cannot connect | `scripts/test-deps.sh` starts Postgres (5455), Valkey (6415) and the emulator (4615); `docker ps` shows them. |
| E2E fails to sign in             | Run `make demo` first, and export `DEMO_PASSWORD` (the Makefile reads it from `deploy/compose/.env`).         |
| 429 during e2e                   | The sign-in limit: the suites reuse saved sessions in `e2e/.auth`; delete it after `make down`.               |
