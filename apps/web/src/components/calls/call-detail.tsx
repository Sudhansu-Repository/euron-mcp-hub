"use client";

import Link from "next/link";

import { JsonView } from "@/components/domain/json-view";
import { RelativeTime } from "@/components/domain/relative-time";
import { CallStatusBadge } from "@/components/domain/status-badge";
import { Badge } from "@/components/ui/badge";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { CALL_STATUS } from "@/lib/labels";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { useCall } from "@/lib/queries";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 py-1.5 text-[13px]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

/** One call in full: who, what, how it ended and the arguments as the audit log kept them. */
export function CallDetail({ id, onClose }: { id: string | null; onClose: () => void }) {
  const call = useCall(id);
  const data = call.data;
  return (
    <Sheet open={id !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        title={data?.qualified_name ?? "Call"}
        description={data ? formatDateTime(data.created_at) : undefined}
        className="w-[min(94vw,34rem)]"
      >
        <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5 pt-4 pb-6">
          {call.error ? (
            <ErrorState message={call.error.message} onRetry={() => call.refetch()} />
          ) : !data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                <CallStatusBadge status={data.status} />
                <Badge tone="outline">{data.source === "playground" ? "Tool tester" : "Gateway"}</Badge>
                <span className="text-muted-foreground text-[12.5px]">{CALL_STATUS[data.status].hint}</span>
              </div>
              {data.error_message ? (
                <p role="alert" className="bg-muted rounded-lg px-3 py-2 text-[13px]">
                  {data.error_message}
                </p>
              ) : null}
              <dl className="divide-border divide-y">
                <Row label="When">
                  {formatDateTime(data.created_at)} (<RelativeTime iso={data.created_at} />)
                </Row>
                <Row label="Client">
                  {data.client_id ? (
                    <Link
                      href={`/clients?q=${encodeURIComponent(data.client_name)}`}
                      className="text-primary hover:underline"
                    >
                      {data.client_name}
                    </Link>
                  ) : (
                    data.client_name
                  )}
                </Row>
                <Row label="Tool">
                  <code className="font-mono text-[12.5px]">{data.qualified_name}</code>
                </Row>
                {data.actor_name ? <Row label="Called by">{data.actor_name} (in the tool tester)</Row> : null}
                <Row label="Latency">
                  {formatDuration(data.latency_ms)}
                  {data.upstream_ms !== null ? `, of which ${formatDuration(data.upstream_ms)} at the server` : ""}
                </Row>
                {data.result_bytes !== null ? <Row label="Result size">{formatBytes(data.result_bytes)}</Row> : null}
                {data.protocol_version ? <Row label="Protocol">{data.protocol_version}</Row> : null}
                {data.user_agent ? <Row label="User agent">{data.user_agent}</Row> : null}
                {data.request_id ? (
                  <Row label="Request id">
                    <code className="font-mono text-[12px]">{data.request_id}</code>
                  </Row>
                ) : null}
              </dl>
              <section>
                <h3 className="mb-1.5 text-[13px] font-semibold">Arguments as recorded</h3>
                {data.arguments === null ? (
                  <p className="text-muted-foreground text-[13px]">
                    This client does not record arguments. Credentials are always masked when they are.
                  </p>
                ) : (
                  <JsonView value={data.arguments} label="Recorded arguments" />
                )}
              </section>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
