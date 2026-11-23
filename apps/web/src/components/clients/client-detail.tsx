"use client";

import { Pause, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useState } from "react";

import { AccessPanel } from "@/components/clients/access-panel";
import { ClientSettings } from "@/components/clients/client-settings";
import { ConnectPanel } from "@/components/clients/connect-panel";
import { KeysPanel } from "@/components/clients/keys-panel";
import { RulesPanel } from "@/components/clients/rules-panel";
import { SimulatePanel } from "@/components/clients/simulate-panel";
import { RelativeTime } from "@/components/domain/relative-time";
import { ClientStatusBadge } from "@/components/domain/status-badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { StatCard } from "@/components/ui/stat-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { useCan, useClient, useDeleteClient, useUpdateClient } from "@/lib/queries";
import { useUrlParams } from "@/lib/use-url-params";

const TABS = ["access", "rules", "keys", "connect", "dry-run", "settings"] as const;
type TabName = (typeof TABS)[number];

export function ClientDetail({ slug }: { slug: string }) {
  const router = useRouter();
  const client = useClient(slug);
  const canWrite = useCan("operator");
  const update = useUpdateClient(slug);
  const remove = useDeleteClient();
  const { params, update: setParams } = useUrlParams();
  const [deleting, setDeleting] = useState(false);
  const requested = params.get("tab") as TabName | null;
  const tab: TabName = requested && TABS.includes(requested) ? requested : "access";

  if (client.error instanceof ApiError && client.error.status === 404) {
    return (
      <PageBody>
        <EmptyState
          title="Client not found"
          description="It was deleted, or the address is wrong."
          action={
            <Button asChild variant="secondary">
              <Link href="/clients">Back to clients</Link>
            </Button>
          }
        />
      </PageBody>
    );
  }
  if (client.error && !client.data) {
    return (
      <PageBody>
        <ErrorState message={client.error.message} onRetry={() => client.refetch()} />
      </PageBody>
    );
  }
  if (!client.data) {
    return (
      <PageBody>
        <Skeleton className="mb-4 h-10 w-72" />
        <Skeleton className="h-72" />
      </PageBody>
    );
  }
  const data = client.data;
  const suspended = data.status === "suspended";

  return (
    <PageBody>
      <PageHeader
        breadcrumbs={[{ label: "Clients", href: "/clients" }, { label: data.name }]}
        documentTitle={data.name}
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            {data.name}
            <ClientStatusBadge status={data.status} />
          </span>
        }
        description={
          <>
            <code className="font-mono text-[12.5px]">{data.slug}</code>
            {data.description ? ` - ${data.description}` : ""}
          </>
        }
        actions={
          canWrite ? (
            <>
              <Button
                variant="secondary"
                loading={update.isPending}
                onClick={async () => {
                  await update.mutateAsync({ status: suspended ? "active" : "suspended" });
                  toast.success(suspended ? "Client resumed." : "Client suspended: its keys stop working now.");
                }}
              >
                {suspended ? <Play /> : <Pause />} {suspended ? "Resume" : "Suspend"}
              </Button>
              <Button
                variant="danger-ghost"
                size="icon"
                aria-label="Delete this client"
                onClick={() => setDeleting(true)}
              >
                <Trash2 />
              </Button>
            </>
          ) : null
        }
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Calls, 24 hours" value={formatNumber(data.calls_24h)} />
        <StatCard
          label="Rules"
          value={data.rules}
          caption={data.default_effect === "deny" ? "default: deny" : "default: allow"}
        />
        <StatCard label="Active keys" value={data.active_keys} />
        <StatCard
          label="Last seen"
          value={
            <span className="text-[20px]">
              {data.last_seen_at ? <RelativeTime iso={data.last_seen_at} /> : "never"}
            </span>
          }
        />
      </div>
      <Tabs value={tab} onValueChange={(next) => setParams({ tab: next === "access" ? null : next })}>
        <TabsList aria-label="Client sections">
          <TabsTrigger value="access">Tool access</TabsTrigger>
          <TabsTrigger value="rules">Rules ({data.rules})</TabsTrigger>
          <TabsTrigger value="keys">Keys ({data.active_keys})</TabsTrigger>
          <TabsTrigger value="connect">Connect</TabsTrigger>
          <TabsTrigger value="dry-run">Dry run</TabsTrigger>
          {canWrite ? <TabsTrigger value="settings">Settings</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="access">
          <AccessPanel client={data} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="rules">
          <RulesPanel slug={slug} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="keys">
          <KeysPanel slug={slug} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="connect">
          <ConnectPanel client={data} />
        </TabsContent>
        <TabsContent value="dry-run">
          <SimulatePanel client={data} />
        </TabsContent>
        {canWrite ? (
          <TabsContent value="settings">
            <ClientSettings key={data.updated_at} client={data} />
          </TabsContent>
        ) : null}
      </Tabs>
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${data.name}?`}
        description="Its keys stop working and its rules are removed. Its calls stay in the audit log."
        confirmLabel="Delete client"
        destructive
        requireText={data.slug}
        onConfirm={async () => {
          await remove.mutateAsync(slug);
          toast.success("Client deleted.");
          router.replace("/clients");
        }}
      />
    </PageBody>
  );
}
