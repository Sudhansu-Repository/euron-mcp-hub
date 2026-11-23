"use client";

import { Activity, ArrowRight, Gauge, ShieldCheck, Timer, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AreaTrend, BarTrend, DonutChart, SERIES } from "@/components/charts";
import { CopyField } from "@/components/copy-field";
import { HealthBadge } from "@/components/domain/status-badge";
import { RelativeTime } from "@/components/domain/relative-time";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { StatCard } from "@/components/ui/stat-card";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCompact, formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { useOverview, useServers, useSystemInfo } from "@/lib/queries";
import type { Overview, StatsRange, TopItem } from "@/lib/types";

const RANGES = [
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
] as const;

const OK = "var(--success)";
const REFUSED = "var(--warning)";
const FAILED = "var(--danger)";

function bucketLabel(range: StatsRange): (iso: string) => string {
  return (iso) =>
    new Date(iso).toLocaleString("en-US", range === "24h" ? { hour: "numeric" } : { month: "short", day: "numeric" });
}

function TopTable({
  title,
  description,
  items,
  noun,
}: {
  title: string;
  description: string;
  items: TopItem[];
  noun: string;
}) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="px-0 pb-2">
        {items.length === 0 ? (
          <p className="text-muted-foreground px-5 pb-4 text-[13px]">No calls in this period.</p>
        ) : (
          <TableContainer label={title} className="rounded-none border-0 shadow-none">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{noun}</TableHead>
                  <TableHead className="text-right">Calls</TableHead>
                  <TableHead className="text-right">Refused</TableHead>
                  <TableHead className="text-right">Failed</TableHead>
                  <TableHead className="text-right">p95</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.key}>
                    <TableCell className="max-w-56 truncate font-medium">{item.label}</TableCell>
                    <TableCell className="tabular text-right">{formatNumber(item.calls)}</TableCell>
                    <TableCell className="tabular text-right">{formatNumber(item.refused)}</TableCell>
                    <TableCell className="tabular text-right">{formatNumber(item.failed)}</TableCell>
                    <TableCell className="tabular text-muted-foreground text-right">
                      {formatDuration(item.p95_ms)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
}

function Charts({ data, range }: { data: Overview; range: StatsRange }) {
  const points = data.series.map((point) => ({
    start: point.start,
    ok: point.ok,
    refused: point.denied + point.blocked + point.invalid_arguments + point.rate_limited,
    failed: point.tool_error + point.upstream_error + point.timeout,
  }));
  const latency = data.latency.map((point) => ({
    start: point.start,
    p50: point.p50_ms ?? 0,
    p95: point.p95_ms ?? 0,
  }));
  const formatBucket = bucketLabel(range);
  const { servers } = data;
  return (
    <>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Tool calls</CardTitle>
              <CardDescription>
                Answered, refused by a client&apos;s policy, and failed because of the server.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <BarTrend
              label="Tool calls over time, split into answered, refused and failed"
              data={points}
              xKey="start"
              xFormat={formatBucket}
              stacked
              series={[
                { key: "ok", name: "Answered", color: OK },
                { key: "refused", name: "Refused", color: REFUSED },
                { key: "failed", name: "Failed", color: FAILED },
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Server health</CardTitle>
              <CardDescription>{formatNumber(servers.enabled)} enabled servers</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <DonutChart
              label="Servers by health"
              size={150}
              centerValue={servers.total}
              centerLabel="servers"
              slices={[
                { name: "Healthy", value: servers.healthy, color: OK },
                { name: "Degraded", value: servers.degraded, color: REFUSED },
                { name: "Down", value: servers.down, color: FAILED },
                { name: "Not checked", value: servers.unknown, color: SERIES[5]! },
              ]}
            />
          </CardContent>
        </Card>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Latency</CardTitle>
              <CardDescription>Median and 95th percentile of the whole call, in milliseconds.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <AreaTrend
              label="Call latency over time"
              data={latency}
              xKey="start"
              xFormat={formatBucket}
              height={200}
              yFormat={(value) => `${formatCompact(value)} ms`}
              series={[
                { key: "p50", name: "Median", color: SERIES[1]! },
                { key: "p95", name: "p95", color: SERIES[0]! },
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Outcomes</CardTitle>
              <CardDescription>Every status a call can end in.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <DonutChart
              label="Calls by outcome"
              size={150}
              centerValue={formatCompact(data.totals.calls)}
              centerLabel="calls"
              slices={Object.entries(data.statuses)
                .filter(([, count]) => count > 0)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 6)
                .map(([status, count], index) => ({
                  name: status.replace(/_/g, " "),
                  value: count,
                  color: SERIES[index % SERIES.length]!,
                }))}
            />
          </CardContent>
        </Card>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <TopTable title="Busiest tools" description="Most called in this period." items={data.top_tools} noun="Tool" />
        <TopTable
          title="Busiest clients"
          description="Who is calling the most."
          items={data.top_clients}
          noun="Client"
        />
      </div>
    </>
  );
}

function ServerStrip() {
  const servers = useServers({ limit: 8 });
  if (!servers.data || servers.data.items.length === 0) return null;
  return (
    <Card className="mt-4">
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Servers</CardTitle>
          <CardDescription>Checked every few seconds by the worker.</CardDescription>
        </div>
        <Link
          href="/servers"
          className="text-primary inline-flex items-center gap-1 text-[13px] font-medium hover:underline"
        >
          All servers <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </CardHeader>
      <CardContent className="px-0 pb-2">
        <TableContainer label="Servers" className="rounded-none border-0 shadow-none">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Server</TableHead>
                <TableHead>Health</TableHead>
                <TableHead className="text-right">Tools</TableHead>
                <TableHead className="text-right">Uptime 24h</TableHead>
                <TableHead className="text-right">Latency</TableHead>
                <TableHead className="text-right">Last check</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {servers.data.items.map((server) => (
                <TableRow key={server.id}>
                  <TableCell>
                    <Link href={`/servers/${server.slug}`} className="hover:text-primary font-medium">
                      {server.name}
                    </Link>
                    <span className="text-muted-foreground ml-2 font-mono text-[12px]">{server.slug}</span>
                  </TableCell>
                  <TableCell>
                    <HealthBadge health={server.health} />
                  </TableCell>
                  <TableCell className="tabular text-right">{server.tool_count}</TableCell>
                  <TableCell className="tabular text-right">
                    {server.uptime_24h === null ? "n/a" : formatPercent(server.uptime_24h, 1)}
                  </TableCell>
                  <TableCell className="tabular text-muted-foreground text-right">
                    {server.last_latency_ms === null ? "n/a" : formatDuration(server.last_latency_ms)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    {server.last_check_at ? <RelativeTime iso={server.last_check_at} /> : "never"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

export function OverviewView() {
  const [range, setRange] = useState<StatsRange>("24h");
  const overview = useOverview(range);
  const system = useSystemInfo();
  const data = overview.data;

  return (
    <PageBody>
      <PageHeader
        title="Overview"
        description="Health and usage of every MCP server and client behind the gateway."
        actions={
          <SegmentedControl
            label="Time range"
            value={range}
            onValueChange={setRange}
            options={RANGES.map((r) => ({ value: r.value, label: r.label }))}
          />
        }
      />
      {system.data ? (
        <div className="mb-4">
          <p className="text-muted-foreground mb-1.5 text-[12.5px]">
            Gateway endpoint (give clients this URL and a key)
          </p>
          <CopyField value={system.data.gateway_url} label="Gateway endpoint" />
        </div>
      ) : null}
      {overview.error && !data ? (
        <ErrorState message={overview.error.message} onRetry={() => overview.refetch()} />
      ) : !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : data.totals.calls === 0 && data.servers.total === 0 ? (
        <EmptyState
          icon={<Activity />}
          title="Nothing to show yet"
          description="Register an MCP server, create a client and make a call. Usage appears here."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Tool calls"
              value={formatCompact(data.totals.calls)}
              icon={<Activity />}
              caption={`${formatNumber(data.totals.tools_used)} different tools used`}
            />
            <StatCard
              label="Success rate"
              value={data.totals.success_rate === null ? "n/a" : formatPercent(data.totals.success_rate, 1)}
              icon={<Gauge />}
              caption={`${formatNumber(data.totals.refused)} refused by policy, ${formatNumber(data.totals.failed)} failed`}
            />
            <StatCard
              label="Latency p95"
              value={formatDuration(data.totals.p95_ms)}
              icon={<Timer />}
              caption={`median ${formatDuration(data.totals.p50_ms)}`}
            />
            <StatCard
              label="Clients"
              value={`${data.totals.active_clients}`}
              icon={<ShieldCheck />}
              caption={`${formatNumber(data.totals.clients_seen)} called in this period`}
            />
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Servers"
              value={`${data.servers.healthy}/${data.servers.enabled}`}
              icon={<Wrench />}
              caption={data.servers.down ? `${data.servers.down} down` : "healthy of enabled"}
            />
            <StatCard
              label="Tools exposed"
              value={formatNumber(data.totals.exposed_tools)}
              caption="in the gateway catalog"
            />
            <StatCard label="Answered" value={formatCompact(data.totals.ok)} caption="calls that returned a result" />
            <StatCard
              label="Refused"
              value={formatCompact(data.totals.refused)}
              caption="denied, blocked or rate limited"
            />
          </div>
          <Charts data={data} range={range} />
          <ServerStrip />
        </>
      )}
    </PageBody>
  );
}
