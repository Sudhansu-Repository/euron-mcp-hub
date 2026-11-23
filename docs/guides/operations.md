# Operations

## Health and metrics

| Endpoint       | Meaning                                                                                                                                                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /livez`   | The process is up (load balancer and container health checks)                                                                                                                                                             |
| `GET /readyz`  | Postgres and Valkey answer, and the secret store is reachable                                                                                                                                                             |
| `GET /metrics` | Prometheus metrics: HTTP, tool calls by server and status, call latency, upstream connections, audit writes and drops, view cache hits, health checks, discovery runs. The worker serves its own on `WORKER_METRICS_PORT` |

Keep `/metrics` off the public load balancer (the AWS stack does).

## What to alert on

- `mcphub_audit_dropped_total` rising: the call log is dropping records because the database is slow or down.
- `mcphub_health_checks_total{status="down"}`: a server stopped answering. The dashboard shows it too.
- A burst of `denied`, `blocked` or `rate_limited` calls from one client: a misbehaving agent.
- `upstream_error` and `timeout` rates per server.

## Routine tasks

| Task                      | How                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------ |
| Create an account         | `mcphub user create --email ... --name ... --role admin` (a one-off task on AWS: `make aws-cli`) |
| Rediscover a server now   | Dashboard, or `mcphub discover --server tickets`                                                 |
| Apply migrations          | Automatic on boot; or `mcphub migrate` / `make aws-migrate`                                      |
| Purge old calls now       | `mcphub purge` (the worker does it hourly)                                                       |
| Rotate a client key       | Create a new key on the client's page, switch the caller, revoke the old one                     |
| Rotate an upstream secret | Set the new value on the server's Secrets tab; the gateway reconnects with it                    |
| Rotate `SESSION_SECRET`   | Replace the secret and restart: everyone signs in again                                          |
| Rotate `API_KEY_PEPPER`   | Invalidates every client key: create new keys first                                              |

## The worker

One worker leads at a time (a lease in Valkey, renewed every five seconds); others wait as hot standbys and
take over within half a minute. It checks servers older than `HEALTH_INTERVAL_S`, rediscovers servers when
their interval passes or when one recovers from `down`, and purges expired rows hourly. SIGTERM finishes the
round and releases the lease.

## Backups and retention

Postgres holds everything that matters; use RDS backups (the AWS stack enables them). Valkey holds only
caches, rate limits, revocation markers and the lease. Calls are deleted after `AUDIT_RETENTION_DAYS`; export
CSV from the audit log first if you need them longer.

## Upgrading

Deploy the new image: the API applies migrations under an advisory lock, so rolling out several tasks is safe.
The gateway is stateless, so a rolling restart drops no sessions.
