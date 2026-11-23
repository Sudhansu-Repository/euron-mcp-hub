"use client";

import { ChevronLeft, ChevronRight, Download, ScrollText } from "lucide-react";
import { useState } from "react";

import { CallDetail } from "@/components/calls/call-detail";
import { RelativeTime } from "@/components/domain/relative-time";
import { CallStatusBadge } from "@/components/domain/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiUrl } from "@/lib/api";
import { formatDateTime, formatDuration, formatNumber } from "@/lib/format";
import { CALL_STATUS, CALL_STATUSES } from "@/lib/labels";
import { callsExportUrl, useCalls, useClients, useServers, type CallParams } from "@/lib/queries";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";
import type { CallStatus } from "@/lib/types";

const WINDOWS = [
  { value: "", label: "All time", ms: 0 },
  { value: "1h", label: "Last hour", ms: 3_600_000 },
  { value: "24h", label: "Last 24 hours", ms: 86_400_000 },
  { value: "7d", label: "Last 7 days", ms: 7 * 86_400_000 },
];

/** The audit log: every tool call, filtered by who, what, when and how it ended. */
export function CallsView() {
  const { params, update, getAll } = useUrlParams();
  const client = params.get("client") ?? "";
  const server = params.get("server") ?? "";
  const source = params.get("source") ?? "";
  const window = params.get("window") ?? "";
  const statuses = getAll("status") as CallStatus[];
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDebouncedValue(text);
  const [stack, setStack] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  // The window start is fixed when the window is chosen (and kept in the address), so the
  // query key stays the same between renders and the list does not refetch itself in a loop.
  const since = params.get("since") ?? undefined;

  const filters: CallParams = {
    client: client || undefined,
    server: server || undefined,
    status: statuses.length ? statuses : undefined,
    source: source || undefined,
    q: q || undefined,
    since,
  };
  const calls = useCalls({ ...filters, cursor: stack.at(-1), limit: 50 });
  const clients = useClients({ limit: 200 });
  const servers = useServers({ limit: 200 });
  const items = calls.data?.items ?? [];
  const filtered = Boolean(client || server || source || window || statuses.length || q);

  function change(updates: Record<string, string | readonly string[] | null>) {
    setStack([]);
    update(updates);
  }

  return (
    <PageBody className="max-w-7xl">
      <PageHeader
        title="Audit log"
        description="Every tool call through the gateway, allowed or refused, with its outcome and redacted arguments."
        actions={
          <Button asChild variant="secondary">
            <a href={apiUrl(callsExportUrl(filters))} download>
              <Download /> Export CSV
            </a>
          </Button>
        }
      />
      <FilterBar className="mb-4">
        <SearchField
          value={text}
          onChange={(value) => {
            setText(value);
            setStack([]);
            update({ q: value || null });
          }}
          label="Search calls"
          placeholder="Search tools, errors, arguments"
        />
        <NativeSelect
          aria-label="Filter by client"
          value={client}
          onChange={(event) => change({ client: event.target.value || null })}
          className="w-44"
        >
          <option value="">Every client</option>
          {clients.data?.items.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by server"
          value={server}
          onChange={(event) => change({ server: event.target.value || null })}
          className="w-44"
        >
          <option value="">Every server</option>
          {servers.data?.items.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.name}
            </option>
          ))}
        </NativeSelect>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary">Outcome{statuses.length ? `: ${statuses.length}` : ""}</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel>Show calls that ended as</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {CALL_STATUSES.map((status) => (
              <DropdownMenuCheckboxItem
                key={status}
                checked={statuses.includes(status)}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={(checked) =>
                  change({ status: checked ? [...statuses, status] : statuses.filter((s) => s !== status) })
                }
              >
                {CALL_STATUS[status].label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <NativeSelect
          aria-label="Filter by time"
          value={window}
          onChange={(event) => {
            const ms = WINDOWS.find((w) => w.value === event.target.value)?.ms ?? 0;
            change({
              window: event.target.value || null,
              since: ms ? new Date(Date.now() - ms).toISOString() : null,
            });
          }}
          className="w-40"
        >
          {WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>
              {w.label}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by source"
          value={source}
          onChange={(event) => change({ source: event.target.value || null })}
          className="w-40"
        >
          <option value="">Any source</option>
          <option value="gateway">Gateway</option>
          <option value="playground">Tool tester</option>
        </NativeSelect>
        {filtered ? (
          <Button
            variant="ghost"
            onClick={() => {
              setText("");
              change({ client: null, server: null, status: null, window: null, since: null, source: null, q: null });
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </FilterBar>

      {calls.error && !calls.data ? (
        <ErrorState message={calls.error.message} onRetry={() => calls.refetch()} />
      ) : !calls.data ? (
        <Skeleton className="h-96" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ScrollText />}
          title={filtered ? "No calls match" : "No calls yet"}
          description={
            filtered
              ? "Try fewer filters or a longer time window."
              : "Calls appear here as soon as a client uses the gateway."
          }
        />
      ) : (
        <div className="space-y-3">
          <p className="text-muted-foreground tabular text-[13px]" aria-live="polite">
            {calls.data.total != null ? `${formatNumber(calls.data.total)} matching calls` : null}
          </p>
          <TableContainer label="Tool calls">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Tool</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead className="text-right">Latency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((call) => (
                  <TableRow key={call.id}>
                    <TableCell className="text-muted-foreground whitespace-nowrap">
                      <time dateTime={call.created_at} title={formatDateTime(call.created_at)}>
                        <RelativeTime iso={call.created_at} />
                      </time>
                    </TableCell>
                    <TableCell className="font-medium">{call.client_name}</TableCell>
                    <TableCell>
                      <button
                        type="button"
                        onClick={() => setSelected(call.id)}
                        className="hover:text-primary text-left font-mono text-[12.5px]"
                      >
                        {call.qualified_name}
                      </button>
                      {call.source === "playground" ? (
                        <Badge tone="outline" className="ml-2">
                          tester
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <CallStatusBadge status={call.status} />
                    </TableCell>
                    <TableCell className="tabular text-muted-foreground text-right">
                      {formatDuration(call.latency_ms)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <nav aria-label="Pagination" className="flex items-center justify-between">
            <Button
              variant="secondary"
              size="sm"
              disabled={stack.length === 0}
              onClick={() => setStack((s) => s.slice(0, -1))}
            >
              <ChevronLeft /> Newer
            </Button>
            <span className="text-muted-foreground text-[13px]">Page {stack.length + 1}</span>
            <Button
              variant="secondary"
              size="sm"
              disabled={!calls.data.next_cursor}
              onClick={() => calls.data?.next_cursor && setStack((s) => [...s, calls.data!.next_cursor!])}
            >
              Older <ChevronRight />
            </Button>
          </nav>
        </div>
      )}
      <CallDetail id={selected} onClose={() => setSelected(null)} />
    </PageBody>
  );
}
