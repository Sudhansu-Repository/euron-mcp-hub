"""Prometheus metrics, exposed at GET /metrics (and on the worker's metrics port).

One API process per container (scale out with containers, not uvicorn workers), so the
default registry is accurate without multiprocess mode.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "mcphub_http_requests_total", "HTTP requests by route template.", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "mcphub_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
TOOL_CALLS = Counter(
    "mcphub_tool_calls_total", "Gateway tool calls by server and outcome.", ["server", "status"]
)
TOOL_CALL_DURATION = Histogram(
    "mcphub_tool_call_duration_seconds",
    "End-to-end gateway tool call latency, including the upstream call.",
    ["server"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
UPSTREAM_CONNECTIONS = Gauge(
    "mcphub_upstream_connections", "Open upstream MCP connections in this process."
)
AUDIT_WRITTEN = Counter("mcphub_audit_written_total", "Tool call records written to Postgres.")
AUDIT_DROPPED = Counter(
    "mcphub_audit_dropped_total", "Tool call records dropped because the buffer was full."
)
VIEW_CACHE = Counter("mcphub_view_cache_total", "Client view cache lookups by result.", ["result"])
HEALTH_CHECKS = Counter(
    "mcphub_health_checks_total", "Upstream health checks by result.", ["status"]
)
DISCOVERY_RUNS = Counter(
    "mcphub_discovery_runs_total", "Upstream discovery runs by outcome.", ["outcome"]
)
