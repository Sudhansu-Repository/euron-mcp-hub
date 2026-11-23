"use client";

import { RelativeTime } from "@/components/domain/relative-time";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useServerPrompts, useServerResources, useServerVersions } from "@/lib/queries";

export function ResourcesPanel({ slug }: { slug: string }) {
  const resources = useServerResources(slug);
  if (resources.error) return <ErrorState message={resources.error.message} onRetry={() => resources.refetch()} />;
  if (!resources.data) return <Skeleton className="h-40" />;
  if (resources.data.length === 0) {
    return <EmptyState title="No resources" description="This server does not expose resources." />;
  }
  return (
    <TableContainer label="Resources">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>URI</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Description</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {resources.data.map((resource) => (
            <TableRow key={resource.id}>
              <TableCell className="font-mono text-[12.5px]">
                {resource.uri} {resource.is_template ? <Badge tone="info">template</Badge> : null}
              </TableCell>
              <TableCell>{resource.title ?? resource.name}</TableCell>
              <TableCell className="text-muted-foreground">{resource.mime_type ?? "n/a"}</TableCell>
              <TableCell className="text-muted-foreground">{resource.description}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export function PromptsPanel({ slug }: { slug: string }) {
  const prompts = useServerPrompts(slug);
  if (prompts.error) return <ErrorState message={prompts.error.message} onRetry={() => prompts.refetch()} />;
  if (!prompts.data) return <Skeleton className="h-40" />;
  if (prompts.data.length === 0) {
    return <EmptyState title="No prompts" description="This server does not expose prompts." />;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {prompts.data.map((prompt) => (
        <Card key={prompt.id}>
          <CardContent>
            <p className="font-mono text-[13px] font-medium">{prompt.name}</p>
            <p className="text-muted-foreground mt-1 text-[13px]">{prompt.description}</p>
            {prompt.arguments.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {prompt.arguments.map((argument) => (
                  <Badge key={argument.name} tone={argument.required ? "primary" : "outline"} className="font-mono">
                    {argument.name}
                    {argument.required ? " *" : ""}
                  </Badge>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function Names({ label, names, tone }: { label: string; names: string[]; tone: "success" | "danger" | "warning" }) {
  if (names.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground w-16 text-[12px]">{label}</span>
      {names.map((name) => (
        <Badge key={name} tone={tone} className="font-mono">
          {name}
        </Badge>
      ))}
    </div>
  );
}

export function VersionsPanel({ slug }: { slug: string }) {
  const versions = useServerVersions(slug);
  if (versions.error) return <ErrorState message={versions.error.message} onRetry={() => versions.refetch()} />;
  if (!versions.data) return <Skeleton className="h-40" />;
  if (versions.data.items.length === 0) {
    return (
      <EmptyState
        title="No history yet"
        description="A version is recorded when discovery sees the server's version or any tool definition change."
      />
    );
  }
  return (
    <ol className="space-y-3">
      {versions.data.items.map((version) => (
        <li key={version.id}>
          <Card>
            <CardContent className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[14px] font-semibold">
                  {version.server_version ? `Server version ${version.server_version}` : "Catalog change"}
                  <span className="text-muted-foreground ml-2 text-[12.5px] font-normal">
                    protocol {version.protocol_version ?? "n/a"}
                  </span>
                </p>
                <RelativeTime iso={version.created_at} className="text-muted-foreground text-[12.5px]" />
              </div>
              <p className="text-muted-foreground text-[13px]">
                {version.tool_count} tools, {version.resource_count} resources, {version.prompt_count} prompts
              </p>
              <Names label="Added" names={version.tools_added} tone="success" />
              <Names label="Changed" names={version.tools_changed} tone="warning" />
              <Names label="Removed" names={version.tools_removed} tone="danger" />
              {version.tools_changed.length > 0 ? (
                <p className="text-warning text-[12.5px]">
                  A changed tool definition can change what an agent does with it. Review it before trusting it again.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </li>
      ))}
    </ol>
  );
}
