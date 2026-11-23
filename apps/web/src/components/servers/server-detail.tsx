"use client";

import { Activity, ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useState } from "react";

import { RelativeTime } from "@/components/domain/relative-time";
import { HealthBadge, TransportBadge } from "@/components/domain/status-badge";
import { HealthPanel } from "@/components/servers/health-panel";
import { PromptsPanel, ResourcesPanel, VersionsPanel } from "@/components/servers/catalog-panels";
import { SecretsPanel } from "@/components/servers/secrets-panel";
import { ServerSettings } from "@/components/servers/server-settings";
import { ToolsPanel } from "@/components/servers/tools-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { StatCard } from "@/components/ui/stat-card";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { useCan, useCheckServer, useDeleteServer, useRefreshServer, useServer, useUpdateServer } from "@/lib/queries";
import { useUrlParams } from "@/lib/use-url-params";
import type { Server } from "@/lib/types";

function Header({ server }: { server: Server }) {
  const router = useRouter();
  const canWrite = useCan("operator");
  const check = useCheckServer(server.slug);
  const refresh = useRefreshServer(server.slug);
  const update = useUpdateServer(server.slug);
  const remove = useDeleteServer();
  const [deleting, setDeleting] = useState(false);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Servers", href: "/servers" }, { label: server.name }]}
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            {server.name}
            <HealthBadge health={server.health} />
            {!server.enabled ? <Badge>Disabled</Badge> : null}
          </span>
        }
        documentTitle={server.name}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <code className="font-mono text-[12.5px]">{server.slug}</code>
            <TransportBadge transport={server.transport} />
            <span className="font-mono text-[12.5px] break-all">
              {server.transport === "streamable_http" ? server.url : [server.command, ...server.args].join(" ")}
            </span>
          </span>
        }
        actions={
          canWrite ? (
            <>
              <label className="text-muted-foreground flex items-center gap-2 text-[13px]">
                <Switch
                  checked={server.enabled}
                  disabled={update.isPending}
                  aria-label="Server enabled"
                  onCheckedChange={(enabled) => update.mutate({ enabled })}
                />
                Enabled
              </label>
              <Button
                variant="secondary"
                loading={check.isPending}
                onClick={async () => {
                  const result = await check.mutateAsync();
                  if (result.ok) toast.success(`Healthy: answered in ${result.latency_ms} ms.`);
                  else toast.error(result.error ?? "The health check failed.");
                }}
              >
                <Activity /> Check now
              </Button>
              <Button
                variant="secondary"
                loading={refresh.isPending}
                onClick={async () => {
                  const result = await refresh.mutateAsync();
                  if (!result.ok) toast.error(result.error ?? "Discovery failed.");
                  else if (result.new_version) toast.success("Discovered changes: see Versions.");
                  else toast.success("Discovered: nothing changed.");
                }}
              >
                <RefreshCw /> Refresh
              </Button>
              <Button
                variant="danger-ghost"
                size="icon"
                aria-label="Remove this server"
                onClick={() => setDeleting(true)}
              >
                <Trash2 />
              </Button>
            </>
          ) : null
        }
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Remove ${server.name}?`}
        description="Its tools leave every client's list at once, and its secrets are deleted. The call log keeps what happened."
        confirmLabel="Remove server"
        destructive
        requireText={server.slug}
        onConfirm={async () => {
          await remove.mutateAsync(server.slug);
          toast.success("Server removed.");
          router.replace("/servers");
        }}
      />
    </>
  );
}

function Summary({ server }: { server: Server }) {
  return (
    <div className="mb-6 space-y-4">
      {server.discovery_error || (server.health === "down" && server.last_error) ? (
        <div role="alert" className="bg-danger-soft text-danger rounded-lg px-3.5 py-2.5 text-[13px]">
          {server.discovery_error ?? server.last_error}
        </div>
      ) : null}
      {server.description ? <p className="text-muted-foreground max-w-3xl text-[14px]">{server.description}</p> : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Tools"
          value={server.tool_count}
          caption={`${server.resource_count} resources, ${server.prompt_count} prompts`}
        />
        <StatCard
          label="Uptime, 24 hours"
          value={server.uptime_24h === null ? "n/a" : formatPercent(server.uptime_24h, 1)}
          caption={
            server.last_latency_ms === null ? "not checked yet" : `last check ${formatDuration(server.last_latency_ms)}`
          }
        />
        <StatCard
          label="Calls, 24 hours"
          value={formatNumber(server.calls_24h)}
          caption={`${formatNumber(server.failed_24h)} failed`}
        />
        <StatCard
          label="Server"
          value={<span className="text-[20px]">{server.server_version ? `v${server.server_version}` : "n/a"}</span>}
          caption={
            <span className="flex flex-wrap gap-x-2">
              {server.server_name ?? "unknown"}
              <span>
                discovered <RelativeTime iso={server.last_discovered_at} />
              </span>
            </span>
          }
        />
      </div>
      {server.homepage_url ? (
        <a
          href={server.homepage_url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-primary inline-flex items-center gap-1 text-[13px] hover:underline"
        >
          Documentation <ExternalLink className="size-3.5" aria-hidden />
        </a>
      ) : null}
    </div>
  );
}

const TABS = ["tools", "resources", "prompts", "versions", "health", "secrets", "settings"] as const;
type TabName = (typeof TABS)[number];

export function ServerDetail({ slug }: { slug: string }) {
  const server = useServer(slug);
  const canWrite = useCan("operator");
  const { params, update } = useUrlParams();
  const requested = params.get("tab") as TabName | null;
  const tab: TabName = requested && TABS.includes(requested) ? requested : "tools";

  if (server.error instanceof ApiError && server.error.status === 404) {
    return (
      <PageBody>
        <EmptyState
          title="Server not found"
          description="It was removed, or the address is wrong."
          action={
            <Button asChild variant="secondary">
              <Link href="/servers">Back to servers</Link>
            </Button>
          }
        />
      </PageBody>
    );
  }
  if (server.error && !server.data) {
    return (
      <PageBody>
        <ErrorState message={server.error.message} onRetry={() => server.refetch()} />
      </PageBody>
    );
  }
  if (!server.data) {
    return (
      <PageBody>
        <Skeleton className="mb-4 h-10 w-72" />
        <Skeleton className="h-72" />
      </PageBody>
    );
  }
  const data = server.data;
  return (
    <PageBody>
      <Header server={data} />
      <Summary server={data} />
      <Tabs value={tab} onValueChange={(next) => update({ tab: next === "tools" ? null : next })}>
        <TabsList aria-label="Server sections">
          <TabsTrigger value="tools">Tools ({data.tool_count})</TabsTrigger>
          <TabsTrigger value="resources">Resources ({data.resource_count})</TabsTrigger>
          <TabsTrigger value="prompts">Prompts ({data.prompt_count})</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
          <TabsTrigger value="health">Health</TabsTrigger>
          {canWrite ? <TabsTrigger value="secrets">Secrets ({data.secret_count})</TabsTrigger> : null}
          {canWrite ? <TabsTrigger value="settings">Settings</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="tools">
          <ToolsPanel slug={slug} />
        </TabsContent>
        <TabsContent value="resources">
          <ResourcesPanel slug={slug} />
        </TabsContent>
        <TabsContent value="prompts">
          <PromptsPanel slug={slug} />
        </TabsContent>
        <TabsContent value="versions">
          <VersionsPanel slug={slug} />
        </TabsContent>
        <TabsContent value="health">
          <HealthPanel server={data} />
        </TabsContent>
        {canWrite ? (
          <TabsContent value="secrets">
            <SecretsPanel server={data} />
          </TabsContent>
        ) : null}
        {canWrite ? (
          <TabsContent value="settings">
            <ServerSettings key={data.updated_at} server={data} />
          </TabsContent>
        ) : null}
      </Tabs>
    </PageBody>
  );
}
