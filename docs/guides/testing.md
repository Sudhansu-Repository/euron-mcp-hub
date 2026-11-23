# Testing

| Suite           | Command                 | What it covers                                                                                                                                      | Needs          |
| --------------- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| API unit        | `make test`             | Policy patterns, specificity, constraints, redaction and scrubbing, the egress guard, fingerprints and diffs, naming, result vetting                | nothing        |
| Web unit        | `make test`             | API client, formatting, runtime env, themes, constraint editing, schema forms, connection snippets, navigation                                      | nothing        |
| API integration | `make test-integration` | The real app over ASGI against real Postgres, Valkey and the Floci emulator, with the bundled demo MCP servers as upstreams                         | Docker         |
| Browser         | `make e2e`              | User journeys in Chromium against the running stack                                                                                                 | `make up demo` |
| QA crawl        | `make qa`               | Every page at 1440 and 390 pixels wide, and in dark mode: console errors, failed requests, sideways scrolling, broken links, serious axe violations | `make up demo` |
| Screenshots     | `make screenshots`      | Captures `docs/assets/screenshots` (1440x900 at 2x) and builds `docs/assets/tour.gif`                                                               | `make up demo` |

Static checks: `make lint` (ruff, ESLint, Prettier), `make typecheck` (mypy strict, tsc), `make sanitize`,
`make tf-fmt tf-validate tf-lint tf-security`, `make gitleaks`.

## Integration suite

`scripts/test-deps.sh` starts Postgres (5455), Valkey (6415) and Floci (4615) from the compose files. The
suite recreates its own database `mcphub_test`, flushes Valkey database 15 and creates a KMS key for the run,
so development data is never touched. Point it elsewhere with `TEST_DATABASE_ADMIN_URL`, `TEST_REDIS_URL`
and `TEST_AWS_ENDPOINT_URL`.

The upstream servers are real: the notes, toolbox and tickets demo servers run on free local ports for the
whole session (the tickets server demands a bearer token, like a hosted one) and a stdio server is launched as
a subprocess. A test that calls a tool therefore travels the whole path: MCP client, gateway, key
authentication, compiled view, policy, constraints, rate limit, pooled upstream connection, server, call log.

| File              | Covers                                                                                                                                                                                                                                                            |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_servers.py` | Registration and discovery, version history with diffs, health and the down threshold, the egress policy on registration and edit, stdio allow-list, tool switches, roles, removal, filters                                                                       |
| `test_secrets.py` | Secrets never in any response, KMS ciphertext in the database, rotation and reconnect, ciphertext bound to its server (replay refused), Secrets Manager and local vaults, validation                                                                              |
| `test_gateway.py` | Per-client tool lists, calls, denied and hidden tools, constraints, schema errors, rate limits, separators, key revocation and expiry, suspension, policy changes taking effect at once, upstream errors, outages and timeouts, concurrent calls, the tool tester |
| `test_clients.py` | Keys shown once, rule validation, the permission matrix, dry runs, suspend and delete, client keys refused by the management API, roles, key listing                                                                                                              |
| `test_audit.py`   | Filters, keyset paging, credential scrubbing in recorded arguments, argument recording off, CSV export, retention, usage statistics, activity                                                                                                                     |
| `test_auth.py`    | First-run setup, cookies, origin checks, uniform failures, lockout, password change ending other sessions, sign-out, deactivation, the last admin, the error envelope                                                                                             |
| `test_worker.py`  | Scheduled checks and discovery, recovery handling, disabled servers, leader election and standby takeover, the pool reaper, hourly retention                                                                                                                      |

## Browser suites

The suites sign in once per role and reuse the saved session (`e2e/.auth`, ignored by git), because the API
limits sign-ins per address. They create their own scratch servers and clients with unique names and remove
them again.

Run the screenshots first on a fresh stack: the end-to-end suite adds scratch rows, and the pictures should
show the demo data only.

```bash
make down up demo screenshots e2e qa down     # in this order
```

On a machine shared with other builds, wrap the sequence in `_tooling/heavy.sh` so it holds the lock.
