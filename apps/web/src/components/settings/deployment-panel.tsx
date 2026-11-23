"use client";

import { CopyField } from "@/components/copy-field";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { useSystemInfo } from "@/lib/queries";

const BACKENDS: Record<string, string> = {
  kms: "AWS KMS (envelope encryption, ciphertext in the database)",
  secretsmanager: "AWS Secrets Manager (the database keeps only a reference)",
  local: "Local AES-GCM (development only)",
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[13rem_1fr] sm:gap-4">
      <dt className="text-muted-foreground text-[13px]">{label}</dt>
      <dd className="min-w-0 text-[13.5px]">{children}</dd>
    </div>
  );
}

export function DeploymentPanel() {
  const system = useSystemInfo();
  if (system.error) return <ErrorState message={system.error.message} onRetry={() => system.refetch()} />;
  if (!system.data) return <Skeleton className="h-64" />;
  const info = system.data;
  return (
    <Card className="max-w-4xl">
      <CardHeader>
        <div>
          <CardTitle>This deployment</CardTitle>
          <CardDescription>Read from the running API. Change these with its environment variables.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <dl className="divide-border divide-y">
          <Row label="Product">
            {info.product_name} <Badge tone="outline">v{info.version}</Badge>
          </Row>
          <Row label="Gateway endpoint">
            <CopyField value={info.gateway_url} label="Gateway endpoint" />
          </Row>
          <Row label="MCP SDK">{info.mcp_sdk_version}</Row>
          <Row label="Protocol versions">
            <span className="flex flex-wrap gap-1.5">
              {info.protocol_versions.map((version) => (
                <Badge key={version} tone="outline" className="font-mono">
                  {version}
                </Badge>
              ))}
            </span>
          </Row>
          <Row label="Upstream secrets">{BACKENDS[info.secrets_backend] ?? info.secrets_backend}</Row>
          <Row label="stdio commands">
            {info.stdio_commands.length ? (
              <span className="flex flex-wrap gap-1.5">
                {info.stdio_commands.map((command) => (
                  <Badge key={command} tone="outline" className="font-mono">
                    {command}
                  </Badge>
                ))}
              </span>
            ) : (
              <span className="text-muted-foreground">Disabled: only streamable HTTP servers can be registered.</span>
            )}
          </Row>
          <Row label="Health checks">Every {info.health_interval_s} seconds</Row>
          <Row label="Audit retention">{info.audit_retention_days} days</Row>
        </dl>
      </CardContent>
    </Card>
  );
}
