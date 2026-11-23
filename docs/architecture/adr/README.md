# Architecture Decision Records

Each record captures one significant decision: the context that forced it, what was decided,
what it costs, and what else was considered. Records are immutable once accepted; a change of
mind is a new record that supersedes the old one.

| ADR                                                           | Title                                                                                       | Status   |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | -------- |
| [0001](0001-stateless-streamable-http-gateway.md)             | The gateway is stateless streamable HTTP built on the official SDK                          | Accepted |
| [0002](0002-default-deny-most-specific-rule-wins.md)          | Client policy is default deny, and the most specific matching rule wins                     | Accepted |
| [0003](0003-envelope-encrypted-write-only-secrets.md)         | Upstream secrets are write-only and envelope-encrypted with KMS, bound to their server      | Accepted |
| [0004](0004-buffered-call-log-writes.md)                      | Tool calls are recorded through a buffered, batched writer                                  | Accepted |
| [0005](0005-egress-policy-for-upstream-urls.md)               | The gateway refuses cloud metadata and private network targets unless they are allow-listed | Accepted |
| [0006](0006-floci-for-local-aws.md)                           | Develop against an AWS emulator (Floci), provisioned by the production Terraform            | Accepted |
| [0007](0007-sessions-as-signed-cookies-with-origin-checks.md) | Dashboard sessions are signed cookies protected by origin checks; scripts use bearer tokens | Accepted |

## Template

```markdown
# ADR NNNN: <decision in one line>

## Status

Proposed | Accepted | Superseded by NNNN

## Context

What forces are at play, and why a decision is needed now.

## Decision

What was decided, concretely.

## Consequences

What gets easier, what gets harder, what to watch.

## Alternatives considered

What else was on the table and why it lost.
```
