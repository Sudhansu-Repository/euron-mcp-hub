from __future__ import annotations

from datetime import datetime

from mcphub.schemas.common import ApiModel


class OverviewTotals(ApiModel):
    calls: int
    ok: int
    failed: int
    refused: int
    success_rate: float | None
    p50_ms: int
    p95_ms: int
    clients_seen: int
    tools_used: int
    active_clients: int
    exposed_tools: int


class ServersSummary(ApiModel):
    total: int
    enabled: int
    unknown: int
    healthy: int
    degraded: int
    down: int


class SeriesPoint(ApiModel):
    start: datetime
    ok: int
    tool_error: int
    denied: int
    blocked: int
    invalid_arguments: int
    rate_limited: int
    upstream_error: int
    timeout: int


class LatencyPoint(ApiModel):
    start: datetime
    p50_ms: int | None
    p95_ms: int | None


class TopItem(ApiModel):
    key: str
    label: str
    calls: int
    failed: int
    refused: int
    p95_ms: int


class OverviewOut(ApiModel):
    range: str
    generated_at: datetime
    bucket_seconds: int
    totals: OverviewTotals
    servers: ServersSummary
    series: list[SeriesPoint]
    latency: list[LatencyPoint]
    statuses: dict[str, int]
    top_tools: list[TopItem]
    top_clients: list[TopItem]
