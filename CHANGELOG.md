# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-17

First release.

### Added

- **Catalog.** Register streamable HTTP and stdio MCP servers. Discovery lists every tool, resource and
  prompt, fingerprints each tool definition and records a dated version with the diff whenever a server's
  version or catalog changes, so a silent change to a tool is visible. The worker checks health on a
  schedule (three failures mean down), rediscovers on an interval and rediscovers a server the moment it
  recovers.
- **One gateway endpoint.** `/mcp` speaks streamable HTTP, stateless and JSON, on the official SDK, for
  handshake clients and the per-request protocol. Tools appear as `server.tool` (or `server__tool` for
  model APIs that reject dots).
- **Per-client permissions.** Default deny, rules by pattern where the most specific wins, argument
  constraints (`one_of`, `equals`, `pattern`, `max_length`, `range`, `forbidden`), per-client and per-rule
  rate limits, redaction paths and a dry run that explains a call without making it.
- **Secrets.** Write-only header and environment secrets, envelope-encrypted with KMS under an encryption
  context that binds each value to its server, or kept in Secrets Manager. Plaintext lives only in the
  memory of an open upstream connection.
- **Egress and launch policy.** Cloud metadata and link-local targets are always refused; private networks
  need an allow-list entry; stdio commands need an allow-list entry. Tool results are size limited, and
  credentials are scrubbed from logs, audit rows and relayed results.
- **Audit log.** Every call, allowed or refused, is recorded off the request path with its redacted
  arguments, searchable and filterable, with CSV export, retention and usage charts. Administrative
  changes are recorded with who made them.
- **Dashboard.** Overview with usage and health, server catalog and connect flow, server pages (tools,
  resources, prompts, versions, health, secrets), cross-server tool search, clients with a tool permission
  matrix, rules, keys, connection snippets and a dry run, an API keys page, a tool tester, the audit log,
  and settings with accounts, roles and activity, in light and dark.
- **Operations.** Accounts with admin, operator and viewer roles, sign-in lockout and rate limits, health
  probes, Prometheus metrics, structured logs, graceful shutdown and a leader-elected worker.
- **Local stack and AWS.** Docker Compose runs everything with no cloud account, with KMS and Secrets
  Manager emulated by Floci and provisioned by the same Terraform that builds `aws-dev` and `aws-prod`
  (VPC, RDS, ElastiCache, ECS Fargate, ALB with WAF, KMS, Secrets Manager, observability).
- **Demo.** Three bundled MCP servers (notes, toolbox, tickets) and a stdio weather server, plus a seeder
  that sends a fortnight of real traffic through the gateway.
