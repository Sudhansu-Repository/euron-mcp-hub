"use client";

import { AreaTrend, BarTrend } from "@/components/charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { StatCard } from "@/components/ui/stat-card";
import { formatDuration, formatPercent } from "@/lib/format";
import { useServerHealth } from "@/lib/queries";
import type { Server } from "@/lib/types";

export function HealthPanel({ server }: { server: Server }) {
  const health = useServerHealth(server.slug, 24);
  if (health.error) return <ErrorState message={health.error.message} onRetry={() => health.refetch()} />;
  if (!health.data) return <Skeleton className="h-64" />;
  const buckets = health.data.buckets;
  if (buckets.every((bucket) => bucket.checks === 0)) {
    return (
      <EmptyState
        title="No health checks yet"
        description="The worker checks enabled servers on a schedule. You can also run a check from the header."
      />
    );
  }
  const label = (iso: string) => new Date(iso).toLocaleString("en-US", { hour: "numeric", minute: "2-digit" });
  const checks = buckets.map((bucket) => ({
    start: bucket.start,
    ok: bucket.ok,
    failed: bucket.checks - bucket.ok,
  }));
  const latency = buckets.map((bucket) => ({ start: bucket.start, latency: bucket.avg_latency_ms ?? 0 }));
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Uptime, last 24 hours"
          value={health.data.uptime === null ? "n/a" : formatPercent(health.data.uptime, 1)}
          caption={`${buckets.reduce((sum, b) => sum + b.checks, 0)} checks`}
        />
        <StatCard
          label="Latest latency"
          value={server.last_latency_ms === null ? "n/a" : formatDuration(server.last_latency_ms)}
          caption="connect and list tools"
        />
        <StatCard
          label="Consecutive failures"
          value={server.consecutive_failures}
          caption={server.consecutive_failures > 0 ? (server.last_error ?? "") : "none"}
        />
      </div>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Checks</CardTitle>
            <CardDescription>Passed and failed checks per {health.data.bucket_minutes} minutes.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <BarTrend
            label="Health checks over the last 24 hours"
            data={checks}
            xKey="start"
            xFormat={label}
            stacked
            height={180}
            series={[
              { key: "ok", name: "Passed", color: "var(--success)" },
              { key: "failed", name: "Failed", color: "var(--danger)" },
            ]}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Latency</CardTitle>
            <CardDescription>Average time to connect and list tools.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <AreaTrend
            label="Health check latency over the last 24 hours"
            data={latency}
            xKey="start"
            xFormat={label}
            height={180}
            legend={false}
            yFormat={(value) => `${value} ms`}
            series={[{ key: "latency", name: "Latency" }]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
