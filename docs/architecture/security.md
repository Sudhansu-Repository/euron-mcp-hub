# Security

How MCPHub protects the things it holds: the credentials of upstream servers, the keys of
clients and the record of what agents did. The threats behind these controls are analysed in
the [threat model](threat-model.md).

## Who can do what

| Caller     | Authenticates with                               | Can                                                                                                  |
| ---------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Admin      | session (cookie or bearer token)                 | Everything, including accounts and roles                                                             |
| Operator   | session                                          | Register servers, set secrets, manage clients, rules and keys, use the tool tester                   |
| Viewer     | session                                          | Read the catalog, clients, call log and usage; never secrets                                         |
| MCP client | client API key (`Authorization: Bearer mch_...`) | Call the gateway at `/mcp`, only the tools its policy allows. A key is refused by the management API |
| Worker     | none (an internal process)                       | Health checks, discovery, retention                                                                  |

Roles are checked by one dependency per route (`api/deps.py`), so a route cannot forget to say
who may call it. The last administrator cannot be demoted or deactivated.

## Dashboard sessions

- Passwords are hashed with Argon2id. Verification of an unknown email costs the same as a
  wrong password, and both give the same answer.
- Eight failed sign-ins lock the account for 15 minutes; the sign-in route is also rate limited per
  address (`RATE_LIMIT_LOGIN`, default ten a minute). Uvicorn trusts `X-Forwarded-For` only from
  the VPC range (`FORWARDED_ALLOW_IPS`), never `*`.
- A session is a signed JWT (HS256, issuer and audience checked) in an `HttpOnly`, `SameSite=Lax`
  cookie (`Secure` in production). Signing out records its `jti` in Valkey until it would have
  expired; changing the password bumps the account's session version, which ends every other
  session at once.
- Cookie-authenticated writes must carry an `Origin` (or `Referer`) from the dashboard's own
  origins, which defends against cross-site request forgery. Bearer-token callers have no
  ambient credential and are not subject to it.
- Production refuses to boot with development secrets, equal secrets, insecure cookies, wildcard
  CORS, an emulator endpoint or a non-HTTPS gateway address (`Settings.production_problems`).

## Client keys

A key is `mch_<10 character prefix>_<43 character secret>`. The secret part is shown once, when the key
is created. The database stores only `HMAC-SHA256(pepper, secret)`, compared in constant time; the
prefix is the lookup handle. Keys can expire, and a revoked key stops working on the next request:
revocation bumps a generation counter in Valkey, so no cached lookup survives it. Suspending a
client has the same effect for all of its keys.

## Upstream secrets

Header and environment secrets of upstream servers are write-only.

- **Encryption.** With `SECRETS_BACKEND=kms` (the default on AWS and on the local Floci stack) a
  value is encrypted by a KMS key with an **encryption context** naming the server and the secret.
  A ciphertext copied into another row, or another server, does not decrypt. With
  `secretsmanager` the value lives in one Secrets Manager secret and the database keeps only its
  ARN. `local` (AES-256-GCM under a key from the environment, associated data naming the secret)
  exists for laptops without an emulator and is refused in production.
- **Never returned.** No endpoint, schema or export includes a value. The API returns names, kinds,
  versions and timestamps.
- **Short exposure.** Plaintext exists only in the memory of the process that opens an upstream
  connection, and only while it is open. A changed secret closes the old connection.
- **Scrubbed.** Anything shaped like a credential is masked in logs (`policy/scrub.py`), in recorded
  arguments and in audit error messages. The exact secret values injected into a connection are
  also masked in the results relayed to clients, so a careless or hostile server that echoes its
  token back does not hand it to an agent.
- **Least privilege on AWS.** The task roles may use the deployment key only with MCPHub's
  encryption context and may touch only this deployment's secret names.

## Egress and launch policy

Registering a server makes the gateway open connections on the operator's behalf, so what it may
reach and run is restricted (`upstream/guard.py`):

| Rule                                                                                                                            | Behaviour                                                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Cloud metadata and link-local addresses (`169.254.0.0/16`, `fd00:ec2::254`, `metadata.google.internal`, multicast, unspecified) | Always refused, including when a name resolves to one                                                                          |
| Loopback, private (RFC 1918, unique local), carrier-grade NAT and reserved ranges, `localhost`, `*.internal`, `*.local`         | Refused unless the host matches `UPSTREAM_ALLOWED_HOSTS` (or `UPSTREAM_ALLOW_PRIVATE=true`, laptops only; production flags it) |
| Public hosts                                                                                                                    | Allowed                                                                                                                        |
| Credentials in the URL                                                                                                          | Refused: put them in a header secret so they are encrypted                                                                     |
| stdio servers                                                                                                                   | Refused unless the command is on `STDIO_ALLOWED_COMMANDS`; arguments are a list and never pass through a shell                 |

The check runs when a server is registered or edited and again every time a connection opens, so
tightening the policy stops servers registered before it. Host names are resolved at check time and
every address they resolve to is judged. A name that changes its answer between the check and the
connection (DNS rebinding) is a residual risk, listed in the threat model.

## Limits

| Limit                           | Default                 | Setting                       |
| ------------------------------- | ----------------------- | ----------------------------- |
| Request body                    | 4 MiB                   | `MAX_REQUEST_MB`              |
| Tool result relayed to a client | 1 MiB                   | `UPSTREAM_MAX_RESULT_BYTES`   |
| Upstream connect                | 10 s                    | `UPSTREAM_CONNECT_TIMEOUT_S`  |
| Tool call                       | per server, 30 s        | server `timeout_s` (1 to 600) |
| Recorded arguments per call     | 16 KiB                  | `AUDIT_MAX_ARGUMENT_BYTES`    |
| Calls per minute                | per client and per rule | client and rule settings      |

## The audit log

Every gateway call, allowed or refused, becomes a row: client, key, tool, status, latency, request
id and the arguments after redaction (paths named by the rule, any value under a key such as
`password`, `token` or `api_key`, and credential-shaped text). A client can turn argument recording
off. Administrative changes (servers, secrets, clients, rules, keys, accounts) are recorded
separately with who made them. Rows are written in batches off the request path; a full queue drops
and counts records (`mcphub_audit_dropped_total`) rather than slowing calls.

## HTTP hygiene

Responses carry `X-Request-Id`; errors use one envelope and never include internals. The web
app sets `nosniff`, `X-Frame-Options: DENY`, a strict referrer policy and a restrictive permissions
policy. `/metrics` is not routed by the load balancer. Containers run as an unprivileged user with
pinned base images, and the AWS stack uses private subnets, encrypted storage and a WAF in
production.
