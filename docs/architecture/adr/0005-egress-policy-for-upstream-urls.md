# ADR 0005: The gateway refuses cloud metadata and private network targets unless they are allow-listed

## Status

Accepted.

## Context

Registering a server tells the gateway to open connections to an address an operator typed. On a cloud host that is a request-forgery primitive: `http://169.254.169.254/` returns instance credentials, and an internal admin service on a private address is one URL away. A stdio server goes further and runs a command.

## Decision

- Cloud metadata and link-local addresses are always refused, whether written as an address, a known metadata host name or a name that resolves to one.
- Loopback, private, carrier NAT and reserved ranges (and `localhost`, `*.internal`, `*.local`) are refused unless the host matches `UPSTREAM_ALLOWED_HOSTS`. `UPSTREAM_ALLOW_PRIVATE` opens them for laptops; production flags it. The demo servers are listed in the compose file, so the stack works offline without weakening the default.
- Host names are resolved and every address is judged. The check runs on registration, on edits and each time a connection opens.
- stdio servers need an executable on `STDIO_ALLOWED_COMMANDS` (empty by default; empty on AWS). Arguments are a list, never a shell string.
- URLs with embedded credentials are refused.

## Consequences

- Reaching an internal MCP server needs an explicit entry; this is a feature, but it is a step during onboarding.
- DNS rebinding between check and connect is not closed by the application. Network policy is the second layer (documented in the threat model).

## Alternatives considered

Allow everything and rely on network policy (a default that fails open); deny everything private (breaks legitimate internal servers and the offline demo); a custom HTTP transport that pins the resolved address (the right long-term fix, tracked in the roadmap)..
