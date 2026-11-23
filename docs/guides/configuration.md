# Configuration

Every setting is an environment variable read once at boot into a validated, frozen `Settings`
object (`apps/api/src/mcphub/core/config.py`). Lists are comma separated. In the local stack the
compose files set them; on AWS the Terraform deployment module sets them and takes the secrets from
Secrets Manager.

With `APP_ENV=production` the API refuses to start with unsafe values and prints every problem at
once: development secrets, equal secrets, insecure cookies, wildcard CORS, a local secrets backend,
an emulator endpoint, an `http://` gateway address or `UPSTREAM_ALLOW_PRIVATE`.

## Core

| Variable                             | Default           | Meaning                                                                       |
| ------------------------------------ | ----------------- | ----------------------------------------------------------------------------- |
| `APP_ENV`                            | `development`     | `development`, `test` or `production`                                         |
| `PRODUCT_NAME`                       | `Euron MCPHub`    | Name shown in the dashboard                                                   |
| `LOG_LEVEL`, `LOG_FORMAT`            | `info`, `json`    | `console` is friendlier on a laptop                                           |
| `DATABASE_URL`                       | local Postgres    | `postgresql+asyncpg://...`                                                    |
| `DATABASE_SECRET_ARN`                | none              | Read the database password from an RDS-managed secret for each new connection |
| `MIGRATE_ON_BOOT`                    | `false`           | Apply migrations when the process starts (advisory-locked)                    |
| `REDIS_URL`                          | local Valkey      | Caches, rate limits, sessions, the worker lease                               |
| `SESSION_SECRET`, `API_KEY_PEPPER`   | development value | Two different random strings of 32 or more characters                         |
| `SESSION_TTL_HOURS`                  | `168`             | Dashboard session lifetime                                                    |
| `COOKIE_SECURE`, `COOKIE_DOMAIN`     | `false`, none     | `COOKIE_SECURE=true` behind HTTPS                                             |
| `CORS_ORIGINS`, `WEB_URL`, `API_URL` | localhost         | Origins of the dashboard and address of the API                               |
| `GATEWAY_URL`                        | `<API_URL>/mcp`   | The address given to MCP clients when it differs from the API                 |
| `MAX_REQUEST_MB`                     | `4`               | Request body limit                                                            |
| `RATE_LIMIT_LOGIN`                   | `10`              | Sign-in attempts per minute per address                                       |

## Upstream servers

| Variable                     | Default   | Meaning                                                                |
| ---------------------------- | --------- | ---------------------------------------------------------------------- |
| `UPSTREAM_ALLOWED_HOSTS`     | empty     | Host patterns (fnmatch) the gateway may reach even on private networks |
| `UPSTREAM_ALLOW_PRIVATE`     | `false`   | Allow every private address (laptops only)                             |
| `UPSTREAM_MAX_RESULT_BYTES`  | `1048576` | Larger tool results are refused instead of relayed                     |
| `UPSTREAM_CONNECT_TIMEOUT_S` | `10`      | Connection and handshake timeout                                       |
| `UPSTREAM_IDLE_TIMEOUT_S`    | `300`     | Idle connections are closed after this                                 |
| `STDIO_ALLOWED_COMMANDS`     | empty     | Executables a stdio server may use; empty disables stdio               |
| `HEALTH_INTERVAL_S`          | `30`      | How often the worker checks each server                                |
| `HEALTH_FAILURE_THRESHOLD`   | `3`       | Consecutive failures before a server is `down`                         |
| `DEFAULT_REFRESH_INTERVAL_S` | `300`     | How often servers are rediscovered                                     |

## Secrets

| Variable                         | Default           | Meaning                                                             |
| -------------------------------- | ----------------- | ------------------------------------------------------------------- |
| `SECRETS_BACKEND`                | `local`           | `kms`, `secretsmanager` or `local` (not in production)              |
| `SECRETS_KMS_KEY_ID`             | none              | Key id, ARN or alias for `kms` (and for Secrets Manager encryption) |
| `SECRETS_NAME_PREFIX`            | `mcphub/local`    | Prefix of Secrets Manager names                                     |
| `SECRETS_RECOVERY_WINDOW_DAYS`   | `7`               | Deleted secrets stay recoverable this long (0 deletes at once)      |
| `SECRETS_LOCAL_KEY`              | derived           | 32 random bytes, base64, for the `local` backend                    |
| `AWS_REGION`, `AWS_ENDPOINT_URL` | `us-east-1`, none | The endpoint is set only for the emulator                           |

## Audit log

| Variable                                                          | Default               | Meaning                                                           |
| ----------------------------------------------------------------- | --------------------- | ----------------------------------------------------------------- |
| `AUDIT_RETENTION_DAYS`                                            | `90`                  | Older calls are deleted by the worker                             |
| `AUDIT_MAX_ARGUMENT_BYTES`                                        | `16384`               | A larger record keeps only its top-level keys                     |
| `AUDIT_FLUSH_INTERVAL_MS`, `AUDIT_BATCH_SIZE`, `AUDIT_QUEUE_SIZE` | `500`, `200`, `10000` | Writer tuning                                                     |
| `GATEWAY_ALLOWED_ORIGINS`                                         | empty                 | When set, browser requests to `/mcp` must come from these origins |

## Compose-only variables

Prefixed `MCPHUB_` in `deploy/compose/.env`: `SESSION_SECRET`, `API_KEY_PEPPER`, `DEMO_PASSWORD`,
`DEMO_TICKETS_TOKEN`, `DEMO_WEATHER_KEY`, `UPSTREAM_ALLOWED_HOSTS`, `PRODUCT_NAME`, `LOG_LEVEL` and the
ports (`WEB_PORT` 3150, `API_PORT` 8150, `PG_PORT` 5455, `REDIS_PORT` 6415, `FLOCI_PORT` 4615).

The dashboard container reads `API_URL` and `PRODUCT_NAME` at request time from `/env.js`, so one image
serves every environment.
