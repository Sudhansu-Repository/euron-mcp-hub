# API

Two surfaces share one process and one port:

- the **management API** under `/api/v1` (the dashboard uses it; so can your scripts), described by
  [openapi.json](openapi.json) and browsable at `/docs` on a running stack;
- the **MCP gateway** at `/mcp` (streamable HTTP, stateless, JSON responses), which MCP clients use.

Regenerate the document from the code with `make openapi`.

## Management API

**Authentication.** `POST /api/v1/auth/login` sets an `HttpOnly` session cookie and also returns the token, which
scripts send as `Authorization: Bearer <token>`. Cookie-authenticated writes must come from the dashboard's own
origin. Client API keys (`mch_...`) are refused here.

**Roles.** `viewer` reads; `operator` also changes servers, secrets, clients, rules and keys and uses the tool
tester; `admin` also manages accounts.

**Errors.** Every failure has one shape, and every response carries `X-Request-Id`:

```json
{ "error": { "code": "target_refused", "message": "...", "request_id": "01JB...", "details": null } }
```

**Pagination.** Lists take `limit` (at most 200) and `offset` and return `{items, total, limit, offset}`. The
call log is paged with an opaque keyset `cursor` and returns `{items, next_cursor}`.

| Area               | Endpoints                                                                                                                                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Auth               | `POST /auth/setup` (first account), `/auth/login`, `/auth/logout`, `GET/PATCH /auth/me`, `POST /auth/password`                                                                                                                             |
| Accounts (admin)   | `GET/POST /users`, `PATCH /users/{id}`                                                                                                                                                                                                     |
| Servers            | `GET/POST /servers`, `GET/PATCH/DELETE /servers/{slug}`, `POST /servers/{slug}/refresh`, `POST /servers/{slug}/check`, `GET /servers/{slug}/tools`, `PATCH /servers/{slug}/tools/{name}`, `/resources`, `/prompts`, `/versions`, `/health` |
| Secrets (operator) | `GET/PUT /servers/{slug}/secrets`, `DELETE /servers/{slug}/secrets/{id}`. Values are write-only                                                                                                                                            |
| Catalog            | `GET /tools`                                                                                                                                                                                                                               |
| Clients            | `GET/POST /clients`, `GET/PATCH/DELETE /clients/{slug}`, `/keys`, `/rules`, `GET /clients/{slug}/tools` (effective access), `POST /clients/{slug}/simulate`                                                                                |
| Keys               | `GET /keys` (every client's keys, never the secrets)                                                                                                                                                                                       |
| Call log           | `GET /calls`, `GET /calls/{id}`, `GET /calls/export` (CSV)                                                                                                                                                                                 |
| Tool tester        | `POST /playground/call`                                                                                                                                                                                                                    |
| Usage              | `GET /stats/overview?range=24h`, `GET /activity`                                                                                                                                                                                           |
| System             | `GET /system/info`, `/livez`, `/readyz`, `/metrics`                                                                                                                                                                                        |

## Gateway

```bash
curl -s http://localhost:8150/mcp \
  -H "authorization: Bearer $MCPHUB_KEY" \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  -H "mcp-protocol-version: 2025-11-25" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"toolbox.calculate","arguments":{"expression":"6 * 7"}}}'
```

| Situation                                        | Response                                                  |
| ------------------------------------------------ | --------------------------------------------------------- |
| No, invalid, expired or revoked key              | HTTP 401 with `WWW-Authenticate: Bearer`                  |
| Suspended client                                 | HTTP 403 `client_suspended`                               |
| A tool the client may not use, or does not exist | JSON-RPC error `-32602` "Unknown tool"                    |
| Arguments break the input schema or a constraint | A tool result with `isError: true` and a readable message |
| Rate limit exceeded                              | A tool result with `isError: true`                        |
| Upstream unreachable, timed out or too large     | A tool result with `isError: true` that names the server  |
| Success, or an upstream tool error               | The upstream result, passed through                       |
