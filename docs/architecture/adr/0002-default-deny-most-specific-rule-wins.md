# ADR 0002: Client policy is default deny, and the most specific matching rule wins

## Status

Accepted.

## Context

An agent should be able to do exactly what it was given. Policy systems that evaluate rules in order make the outcome depend on list order, which people cannot see or reason about; systems where deny always beats allow make it impossible to say "everything on this server except one tool, but allow one of those back".

## Decision

- A rule is a pattern (`server.tool` with `*` and `?`) with an effect, optional argument constraints, a rate limit and a redaction list.
- For a tool, every matching rule is collected and the most specific wins: an exact name beats `tickets.get_*`, which beats `tickets.*`, which beats `*`. Specificity is the pair (no wildcard, number of literal characters). Two rules of equal specificity resolve to deny.
- New clients default to deny. A client can opt into default allow, and the dashboard warns when it does.
- A tool a client may not use is absent from `tools/list` and refused on `tools/call` exactly like a tool that does not exist.
- The decision logic is a pure module (`policy/`) with property-based tests; the dashboard's permission matrix and dry run call the same code the gateway does.

## Consequences

- Rule order never matters, and the dashboard can show which rule decided each tool and why.
- Equal-specificity conflicts are deny, which may surprise an author who expected last-write-wins; the rule list says so.
- Hiding denied tools means a model cannot be told "you are not allowed", only that the tool is unknown. The audit log records the real reason.

## Alternatives considered

Ordered rule lists (hidden dependence on order); deny-always-wins (cannot express exceptions); RBAC roles per client (coarser than tools and cannot constrain arguments)..
