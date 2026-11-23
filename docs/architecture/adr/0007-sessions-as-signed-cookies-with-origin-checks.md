# ADR 0007: Dashboard sessions are signed cookies protected by origin checks; scripts use bearer tokens

## Status

Accepted.

## Context

The dashboard is a browser app on one origin and the API is on another port or path. Tokens in `localStorage` are readable by any script on the page; cookies are sent by the browser to anyone who can make it send them.

## Decision

- Sign-in sets an `HttpOnly`, `SameSite=Lax` (and, in production, `Secure`) cookie holding a signed JWT. The same token is returned in the response body for scripts, which send it as a bearer token.
- A cookie-authenticated unsafe request must carry an `Origin` (or `Referer`) from the dashboard's own origins, otherwise it is refused as cross-site. Bearer callers have no ambient credential and skip the check.
- Sign-out and password changes revoke: the token id is recorded in Valkey until expiry, and the account's session version is bumped.
- Client API keys are a different credential for a different surface and are refused by the management API.

## Consequences

- The API and the web app must share a site for `SameSite=Lax` cookies to flow; the AWS deployment serves both on one host name, and locally `localhost` ports share cookies.
- Revocation needs Valkey; if it is unreachable, sign-out markers are not read (the token's short expiry bounds the exposure).

## Alternatives considered

Tokens in `localStorage` (script-readable); server-side sessions in the database (a lookup per request for little gain over signed tokens plus a revocation list); OAuth for the dashboard (heavy for a self-hosted admin tool)..
