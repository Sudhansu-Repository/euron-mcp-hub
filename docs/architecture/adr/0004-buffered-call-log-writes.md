# ADR 0004: Tool calls are recorded through a buffered, batched writer

## Status

Accepted.

## Context

Every call must be audited, but a database insert on the request path adds a round trip and ties gateway latency to database latency. Dropping audit records silently would make the log untrustworthy.

## Decision

- A call's record is appended to a bounded in-process queue (10,000) and a background task inserts batches every 500 ms or 200 rows, stamping `last_used_at` on keys and `last_seen_at` on clients in the same transaction.
- Shutdown drains the queue. A failed batch is retried; when the queue is full, new records are dropped **and counted** (`mcphub_audit_dropped_total`, with an alert), never silently.
- Records reference clients, keys, servers and rules by id with `ON DELETE SET NULL`, and carry their names as text, so history survives deletions.
- The log is read with keyset pagination and per-column indexes ending in `created_at`.

## Consequences

- A process crash loses at most half a second of records.
- Under sustained database failure the log can have gaps; the counter and the alert make them visible.
- Reads are slightly behind writes (the writer's interval).

## Alternatives considered

Synchronous inserts (latency and failure coupling); a message queue between gateway and database (another moving part for the same guarantee); writing only a log line (not queryable)..
