"use client";

import { Plug, Server as ServerIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { HealthBadge, TransportBadge } from "@/components/domain/status-badge";
import { RelativeTime } from "@/components/domain/relative-time";
import { ConnectDialog } from "@/components/servers/connect-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { useCan, useServers } from "@/lib/queries";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";

export function ServersView() {
  const { params, update } = useUrlParams();
  const q = params.get("q") ?? "";
  const health = params.get("health") ?? "";
  const [text, setText] = useState(q);
  const debounced = useDebouncedValue(text);
  const servers = useServers({ q: debounced || undefined, health: health || undefined });
  const canWrite = useCan("operator");
  const [connecting, setConnecting] = useState(false);
  const items = servers.data?.items ?? [];
  const filtered = Boolean(debounced || health);

  return (
    <PageBody>
      <PageHeader
        title="Servers"
        description="Every MCP server behind the gateway, checked on a schedule and rediscovered when it changes."
        actions={
          canWrite ? (
            <Button onClick={() => setConnecting(true)}>
              <Plug /> Connect a server
            </Button>
          ) : null
        }
      />
      <FilterBar className="mb-4">
        <SearchField
          value={text}
          onChange={(value) => {
            setText(value);
            update({ q: value || null });
          }}
          label="Search servers"
          placeholder="Search by name, namespace or tag"
        />
        <NativeSelect
          aria-label="Filter by health"
          value={health}
          onChange={(event) => update({ health: event.target.value || null })}
          className="w-40"
        >
          <option value="">Any health</option>
          <option value="healthy">Healthy</option>
          <option value="degraded">Degraded</option>
          <option value="down">Down</option>
          <option value="unknown">Not checked</option>
        </NativeSelect>
      </FilterBar>

      {servers.error && !servers.data ? (
        <ErrorState message={servers.error.message} onRetry={() => servers.refetch()} />
      ) : !servers.data ? (
        <div className="space-y-2" aria-busy>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ServerIcon />}
          title={filtered ? "No servers match" : "No servers yet"}
          description={
            filtered
              ? "Try a different search or clear the filters."
              : "Connect your first MCP server to put its tools behind the gateway."
          }
          action={
            !filtered && canWrite ? (
              <Button onClick={() => setConnecting(true)}>
                <Plug /> Connect a server
              </Button>
            ) : undefined
          }
        />
      ) : (
        <TableContainer label="Servers">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Server</TableHead>
                <TableHead>Health</TableHead>
                <TableHead className="text-right">Tools</TableHead>
                <TableHead className="text-right">Uptime 24h</TableHead>
                <TableHead className="text-right">Latency</TableHead>
                <TableHead className="text-right">Calls 24h</TableHead>
                <TableHead className="text-right">Discovered</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((server) => (
                <TableRow key={server.id}>
                  <TableCell className="min-w-64">
                    <div className="flex items-center gap-2">
                      <Link href={`/servers/${server.slug}`} className="hover:text-primary font-medium">
                        {server.name}
                      </Link>
                      {!server.enabled ? <Badge>Disabled</Badge> : null}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <code className="text-muted-foreground font-mono text-[12px]">{server.slug}</code>
                      <TransportBadge transport={server.transport} />
                      {server.tags.slice(0, 3).map((tag) => (
                        <Badge key={tag} tone="primary">
                          {tag}
                        </Badge>
                      ))}
                    </div>
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
                  <TableCell className="tabular text-right">
                    {formatNumber(server.calls_24h)}
                    {server.failed_24h > 0 ? (
                      <span className="text-danger ml-1 text-xs">({formatNumber(server.failed_24h)} failed)</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    <RelativeTime iso={server.last_discovered_at} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <ConnectDialog open={connecting} onOpenChange={setConnecting} />
    </PageBody>
  );
}
