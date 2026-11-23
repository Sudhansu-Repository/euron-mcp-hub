import { Badge } from "@/components/ui/badge";
import { CALL_STATUS, HEALTH, TRANSPORT, type Tone } from "@/lib/labels";
import type { CallStatus, ClientStatus, Health, Transport } from "@/lib/types";

export function HealthBadge({ health, className }: { health: Health; className?: string }) {
  const { label, tone } = HEALTH[health];
  return (
    <Badge tone={tone} className={className}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {label}
    </Badge>
  );
}

export function CallStatusBadge({ status }: { status: CallStatus }) {
  const { label, tone } = CALL_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function ClientStatusBadge({ status }: { status: ClientStatus }) {
  const tone: Tone = status === "active" ? "success" : "warning";
  return <Badge tone={tone}>{status === "active" ? "Active" : "Suspended"}</Badge>;
}

export function TransportBadge({ transport }: { transport: Transport }) {
  return <Badge tone="outline">{TRANSPORT[transport]}</Badge>;
}

/** What the tool declares about itself (MCP annotations): reads only, or may destroy data. */
export function ToolHints({
  readOnly,
  destructive,
}: {
  readOnly: boolean | null | undefined;
  destructive: boolean | null | undefined;
}) {
  if (destructive) return <Badge tone="danger">Destructive</Badge>;
  if (readOnly) return <Badge tone="info">Read-only</Badge>;
  return <Badge tone="neutral">Writes</Badge>;
}
