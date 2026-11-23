"use client";

import { Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ToolHints } from "@/components/domain/status-badge";
import { ToolDetail } from "@/components/servers/tools-panel";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useServers, useTools } from "@/lib/queries";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";
import type { Tool } from "@/lib/types";

const PAGE = 50;

/** Every tool of every server in one searchable list: what an agent could ever be given. */
export function ToolsView() {
  const { params, update } = useUrlParams();
  const server = params.get("server") ?? "";
  const offset = Number(params.get("offset") ?? 0) || 0;
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDebouncedValue(text);
  const servers = useServers({ limit: 200 });
  const tools = useTools({ q: q || undefined, server: server || undefined, limit: PAGE, offset });
  const [selected, setSelected] = useState<Tool | null>(null);
  const items = tools.data?.items ?? [];

  return (
    <PageBody>
      <PageHeader
        title="Tools"
        description="Every tool discovered across the catalog. Clients get these through the gateway, named server.tool."
      />
      <FilterBar className="mb-4">
        <SearchField
          value={text}
          onChange={(value) => {
            setText(value);
            update({ q: value || null, offset: null });
          }}
          label="Search tools"
          placeholder="Search by name or description"
        />
        <NativeSelect
          aria-label="Filter by server"
          value={server}
          onChange={(event) => update({ server: event.target.value || null, offset: null })}
          className="w-52"
        >
          <option value="">Every server</option>
          {servers.data?.items.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.name}
            </option>
          ))}
        </NativeSelect>
      </FilterBar>
      {tools.error && !tools.data ? (
        <ErrorState message={tools.error.message} onRetry={() => tools.refetch()} />
      ) : !tools.data ? (
        <Skeleton className="h-72" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Wrench />}
          title="No tools found"
          description={q || server ? "Try a different search." : "Connect a server to see its tools here."}
        />
      ) : (
        <div className="space-y-4">
          <TableContainer label="Tools">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tool</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Server</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((tool) => (
                  <TableRow key={tool.id}>
                    <TableCell className="min-w-52">
                      <button
                        type="button"
                        onClick={() => setSelected(tool)}
                        className="hover:text-primary text-left font-mono text-[12.5px] font-medium"
                      >
                        {tool.qualified_name}
                      </button>
                      {!tool.enabled ? (
                        <Badge tone="warning" className="ml-2">
                          Switched off
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <ToolHints
                        readOnly={tool.annotations.readOnlyHint as boolean | undefined}
                        destructive={tool.annotations.destructiveHint as boolean | undefined}
                      />
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-lg">
                      <span className="line-clamp-2">{tool.description}</span>
                    </TableCell>
                    <TableCell>
                      <Link href={`/servers/${tool.server_slug}`} className="text-primary hover:underline">
                        {tool.server_slug}
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Pagination
            total={tools.data.total}
            limit={PAGE}
            offset={offset}
            noun="tools"
            onOffsetChange={(next) => update({ offset: next || null })}
          />
        </div>
      )}
      <ToolDetail tool={selected} onClose={() => setSelected(null)} />
    </PageBody>
  );
}
