# ADR 0001: The gateway is stateless streamable HTTP built on the official SDK

## Status

Accepted.

## Context

Clients reach many servers through one endpoint. MCP offers a stateful session transport (an `Mcp-Session-Id` that pins a client to a process) and a stateless mode in which every request stands alone. A stateful gateway needs sticky routing, loses sessions when a task is replaced and cannot scale by adding replicas. Writing a protocol implementation by hand would drift from the specification as it moves (`2025-11-25` handshake clients and the per-request `2026-07-28` protocol both exist).

## Decision

- The gateway is the SDK's low-level `Server`, mounted at `/mcp` inside the API process behind a thin ASGI endpoint that authenticates the client key.
- It runs the SDK's `StreamableHTTPSessionManager` with `stateless=True` and `json_response=True`: any replica can answer any request, and a response is a plain JSON body.
- The authenticated client travels to the handlers on the request scope, so policy needs no session state.
- Upstream connections are held per server per process (the pool), because those are expensive and the clients' requests are not.

## Consequences

- Server-to-client requests (sampling, elicitation) cannot flow through a stateless JSON gateway; an upstream tool that needs them fails with a clear error. Proxying resources and prompts is deferred for the same reason.
- Each request re-authenticates, which is why key lookups and compiled views are cached in Valkey.
- Following the SDK means following its releases; the version is shown on the Deployment page.

## Alternatives considered

Hand-written JSON-RPC (drifts from the spec); a stateful gateway with sticky sessions (operational cost for a feature this product does not need); proxying at the HTTP level without understanding MCP (cannot enforce per-tool policy)..
