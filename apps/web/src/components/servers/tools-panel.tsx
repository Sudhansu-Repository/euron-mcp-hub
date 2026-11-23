"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { JsonView } from "@/components/domain/json-view";
import { SchemaView } from "@/components/domain/schema-view";
import { ToolHints } from "@/components/domain/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RelativeTime } from "@/components/domain/relative-time";
import { useCan, useServerTools, useSetToolEnabled } from "@/lib/queries";
import type { Tool } from "@/lib/types";

export function ToolDetail({ tool, onClose }: { tool: Tool | null; onClose: () => void }) {
  return (
    <Sheet open={tool !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        title={tool?.qualified_name ?? "Tool"}
        description={tool?.title ?? undefined}
        className="w-[min(94vw,32rem)]"
      >
        {tool ? (
          <div className="scroll-quiet min-h-0 flex-1 space-y-5 overflow-y-auto px-5 pt-4 pb-6">
            <p className="text-muted-foreground text-[13.5px] whitespace-pre-line">
              {tool.description || "This tool has no description."}
            </p>
            <div className="flex flex-wrap gap-1.5">
              <ToolHints
                readOnly={tool.annotations.readOnlyHint as boolean | undefined}
                destructive={tool.annotations.destructiveHint as boolean | undefined}
              />
              {!tool.enabled ? <Badge tone="warning">Switched off</Badge> : null}
              <Badge tone="outline">
                Seen <RelativeTime iso={tool.first_seen_at} />
              </Badge>
              {tool.changed_at ? (
                <Badge tone="warning">
                  Changed <RelativeTime iso={tool.changed_at} />
                </Badge>
              ) : null}
            </div>
            <section>
              <h3 className="mb-1 text-[13px] font-semibold">Arguments</h3>
              <SchemaView schema={tool.input_schema} />
            </section>
            <section>
              <h3 className="mb-1.5 text-[13px] font-semibold">Input schema</h3>
              <JsonView
                value={tool.input_schema}
                label={`Input schema of ${tool.qualified_name}`}
                className="max-h-72"
              />
            </section>
            <p className="text-subtle font-mono text-[11.5px]">fingerprint {tool.fingerprint.slice(0, 16)}</p>
            <Button asChild variant="secondary" size="sm">
              <Link href={`/playground?tool=${encodeURIComponent(tool.qualified_name)}`}>
                <FlaskConical /> Try it in the tool tester
              </Link>
            </Button>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

export function ToolsPanel({ slug }: { slug: string }) {
  const tools = useServerTools(slug);
  const toggle = useSetToolEnabled(slug);
  const canWrite = useCan("operator");
  const [selected, setSelected] = useState<Tool | null>(null);

  if (tools.error) return <ErrorState message={tools.error.message} onRetry={() => tools.refetch()} />;
  if (!tools.data) return <Skeleton className="h-48" />;
  if (tools.data.length === 0) {
    return (
      <EmptyState
        title="No tools discovered"
        description="The server has not listed any tools yet. Refresh it once it is reachable."
      />
    );
  }
  return (
    <>
      <TableContainer label="Tools">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tool</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="text-right">In the gateway</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tools.data.map((tool) => (
              <TableRow key={tool.id}>
                <TableCell className="min-w-52">
                  <button
                    type="button"
                    onClick={() => setSelected(tool)}
                    className="hover:text-primary text-left font-mono text-[12.5px] font-medium"
                  >
                    {tool.qualified_name}
                  </button>
                </TableCell>
                <TableCell>
                  <ToolHints
                    readOnly={tool.annotations.readOnlyHint as boolean | undefined}
                    destructive={tool.annotations.destructiveHint as boolean | undefined}
                  />
                </TableCell>
                <TableCell className="text-muted-foreground max-w-md">
                  <span className="line-clamp-2">{tool.description}</span>
                </TableCell>
                <TableCell className="text-right">
                  <Switch
                    aria-label={`${tool.enabled ? "Switch off" : "Switch on"} ${tool.qualified_name}`}
                    checked={tool.enabled}
                    disabled={!canWrite || toggle.isPending}
                    onCheckedChange={(enabled) => toggle.mutate({ name: tool.name, enabled })}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <ToolDetail tool={selected} onClose={() => setSelected(null)} />
    </>
  );
}
