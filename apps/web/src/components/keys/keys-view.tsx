"use client";

import { KeyRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { KeyStateBadge } from "@/components/clients/keys-panel";
import { RelativeTime } from "@/components/domain/relative-time";
import { ClientStatusBadge } from "@/components/domain/status-badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAllKeys } from "@/lib/queries";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";

const PAGE = 50;

/** Every key of every client: which are live, which were revoked, which have gone quiet. */
export function KeysView() {
  const { params, update } = useUrlParams();
  const state = params.get("state") ?? "";
  const offset = Number(params.get("offset") ?? 0) || 0;
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDebouncedValue(text);
  const keys = useAllKeys({ q: q || undefined, state: state || undefined, limit: PAGE, offset });
  const items = keys.data?.items ?? [];

  return (
    <PageBody>
      <PageHeader
        title="API keys"
        description="Keys clients use to call the gateway. A key is shown once, when it is created, on the client's page."
      />
      <FilterBar className="mb-4">
        <SearchField
          value={text}
          onChange={(value) => {
            setText(value);
            update({ q: value || null, offset: null });
          }}
          label="Search keys"
          placeholder="Search by key or client name"
        />
        <NativeSelect
          aria-label="Filter by state"
          value={state}
          onChange={(event) => update({ state: event.target.value || null, offset: null })}
          className="w-40"
        >
          <option value="">Any state</option>
          <option value="active">Active</option>
          <option value="revoked">Revoked</option>
          <option value="expired">Expired</option>
        </NativeSelect>
      </FilterBar>
      {keys.error && !keys.data ? (
        <ErrorState message={keys.error.message} onRetry={() => keys.refetch()} />
      ) : !keys.data ? (
        <Skeleton className="h-64" />
      ) : items.length === 0 ? (
        <EmptyState icon={<KeyRound />} title="No keys found" description="Create a client to get its first key." />
      ) : (
        <div className="space-y-4">
          <TableContainer label="API keys">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead className="text-right">Created</TableHead>
                  <TableHead className="text-right">Last used</TableHead>
                  <TableHead className="text-right">Expires</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell>
                      <p className="font-medium">{key.name}</p>
                      <p className="text-muted-foreground font-mono text-[12px]">mch_{key.prefix}_...</p>
                    </TableCell>
                    <TableCell>
                      <Link href={`/clients/${key.client_slug}?tab=keys`} className="hover:text-primary font-medium">
                        {key.client_name}
                      </Link>{" "}
                      {key.client_status === "suspended" ? <ClientStatusBadge status={key.client_status} /> : null}
                    </TableCell>
                    <TableCell>
                      <KeyStateBadge keyData={key} />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right">
                      <RelativeTime iso={key.created_at} />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right">
                      <RelativeTime iso={key.last_used_at} />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right">
                      {key.expires_at ? <RelativeTime iso={key.expires_at} /> : "never"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Pagination
            total={keys.data.total}
            limit={PAGE}
            offset={offset}
            noun="keys"
            onOffsetChange={(next) => update({ offset: next || null })}
          />
        </div>
      )}
    </PageBody>
  );
}
