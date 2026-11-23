"use client";

import { Plus, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { RelativeTime } from "@/components/domain/relative-time";
import { ClientStatusBadge } from "@/components/domain/status-badge";
import { CreateClientDialog } from "@/components/clients/create-client-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import { useCan, useClients } from "@/lib/queries";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";

export function ClientsView() {
  const { params, update } = useUrlParams();
  const status = params.get("status") ?? "";
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDebouncedValue(text);
  const clients = useClients({ q: q || undefined, status: status || undefined });
  const canWrite = useCan("operator");
  const [creating, setCreating] = useState(false);
  const items = clients.data?.items ?? [];

  return (
    <PageBody>
      <PageHeader
        title="Clients"
        description="Agents, IDEs and apps that call the gateway. Each has its own keys and its own tool permissions."
        actions={
          canWrite ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New client
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
          label="Search clients"
          placeholder="Search by name or slug"
        />
        <NativeSelect
          aria-label="Filter by status"
          value={status}
          onChange={(event) => update({ status: event.target.value || null })}
          className="w-40"
        >
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </NativeSelect>
      </FilterBar>
      {clients.error && !clients.data ? (
        <ErrorState message={clients.error.message} onRetry={() => clients.refetch()} />
      ) : !clients.data ? (
        <Skeleton className="h-64" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck />}
          title={q || status ? "No clients match" : "No clients yet"}
          description="A client is one caller of the gateway. Create one, give it a key and decide which tools it may use."
          action={
            canWrite && !q && !status ? (
              <Button onClick={() => setCreating(true)}>
                <Plus /> New client
              </Button>
            ) : undefined
          }
        />
      ) : (
        <TableContainer label="Clients">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Client</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Default</TableHead>
                <TableHead className="text-right">Rules</TableHead>
                <TableHead className="text-right">Keys</TableHead>
                <TableHead className="text-right">Calls 24h</TableHead>
                <TableHead className="text-right">Last seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((client) => (
                <TableRow key={client.id}>
                  <TableCell className="min-w-64">
                    <Link href={`/clients/${client.slug}`} className="hover:text-primary font-medium">
                      {client.name}
                    </Link>
                    <p className="text-muted-foreground mt-0.5 line-clamp-1 text-[12.5px]">
                      <code className="font-mono">{client.slug}</code>
                      {client.description ? ` - ${client.description}` : ""}
                    </p>
                  </TableCell>
                  <TableCell>
                    <ClientStatusBadge status={client.status} />
                  </TableCell>
                  <TableCell>
                    <Badge tone={client.default_effect === "allow" ? "warning" : "outline"}>
                      {client.default_effect === "allow" ? "Allow unless denied" : "Deny unless allowed"}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular text-right">{client.rules}</TableCell>
                  <TableCell className="tabular text-right">{client.active_keys}</TableCell>
                  <TableCell className="tabular text-right">{formatNumber(client.calls_24h)}</TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    <RelativeTime iso={client.last_seen_at} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <CreateClientDialog open={creating} onOpenChange={setCreating} />
    </PageBody>
  );
}
