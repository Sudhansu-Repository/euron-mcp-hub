"use client";

import { useState } from "react";

import { RelativeTime } from "@/components/domain/relative-time";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ACTIVITY_LABEL } from "@/lib/labels";
import { useActivity } from "@/lib/queries";

const PAGE = 25;

/** Who changed what: servers, secrets, clients, rules, keys and accounts. */
export function ActivityPanel() {
  const [offset, setOffset] = useState(0);
  const activity = useActivity({ limit: PAGE, offset });
  if (activity.error && !activity.data)
    return <ErrorState message={activity.error.message} onRetry={() => activity.refetch()} />;
  if (!activity.data) return <Skeleton className="h-64" />;
  if (activity.data.items.length === 0) {
    return (
      <EmptyState title="No activity yet" description="Changes to servers, clients and accounts are listed here." />
    );
  }
  return (
    <div className="space-y-4">
      <TableContainer label="Administrative activity">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Who</TableHead>
              <TableHead>What</TableHead>
              <TableHead className="text-right">When</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {activity.data.items.map((event) => (
              <TableRow key={event.id}>
                <TableCell className="font-medium whitespace-nowrap">{event.actor_name}</TableCell>
                <TableCell>
                  {ACTIVITY_LABEL[event.action] ?? event.action}{" "}
                  {event.target_name ? <code className="font-mono text-[12.5px]">{event.target_name}</code> : null}
                  {typeof event.details.key === "string" ? (
                    <span className="text-muted-foreground"> ({event.details.key})</span>
                  ) : null}
                </TableCell>
                <TableCell className="text-muted-foreground text-right whitespace-nowrap">
                  <RelativeTime iso={event.created_at} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Pagination total={activity.data.total} limit={PAGE} offset={offset} noun="events" onOffsetChange={setOffset} />
    </div>
  );
}
