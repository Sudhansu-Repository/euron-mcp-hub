"use client";

import { KeyRound, Lock, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { RelativeTime } from "@/components/domain/relative-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, FieldHint, Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDeleteSecret, useSecrets, useSetSecret, useSystemInfo } from "@/lib/queries";
import type { Secret, SecretKind, Server } from "@/lib/types";

const BACKEND: Record<string, string> = {
  kms: "KMS envelope",
  secretsmanager: "Secrets Manager",
  local: "Local AES-GCM",
};

function SecretForm({ server }: { server: Server }) {
  const set = useSetSecret(server.slug, { silent: true });
  const stdio = server.transport === "stdio";
  const kind: SecretKind = stdio ? "env" : "header";
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await set.mutateAsync({ kind, name: name.trim(), value });
    } catch {
      return; // Rendered from the mutation state below.
    }
    toast.success(`${name.trim()} saved. The value is encrypted and cannot be read back.`);
    setName("");
    setValue("");
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Set a secret</CardTitle>
          <CardDescription>
            Saving an existing name replaces its value. Values are write-only: no screen and no API call returns them.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={kind === "header" ? "Header name" : "Variable name"} htmlFor="secret-name" required>
              <Input
                id="secret-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={kind === "header" ? "Authorization" : "API_KEY"}
                required
              />
            </Field>
            <Field label="Value" htmlFor="secret-value" required>
              <Input
                id="secret-value"
                type="password"
                autoComplete="off"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder={kind === "header" ? "Bearer ..." : ""}
                required
              />
            </Field>
          </div>
          {set.error ? <ErrorNotice message={set.error.message} /> : null}
          <div className="flex justify-end">
            <Button type="submit" loading={set.isPending}>
              <KeyRound /> Encrypt and save
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function SecretsPanel({ server }: { server: Server }) {
  const secrets = useSecrets(server.slug);
  const remove = useDeleteSecret(server.slug);
  const system = useSystemInfo();
  const [deleting, setDeleting] = useState<Secret | null>(null);

  return (
    <div className="space-y-4">
      <div className="bg-muted/60 text-muted-foreground flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-[13px]">
        <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          Secrets are encrypted with{" "}
          <strong className="text-foreground font-medium">
            {BACKEND[system.data?.secrets_backend ?? "kms"] ?? system.data?.secrets_backend}
          </strong>{" "}
          and bound to this server, so a stored value cannot be moved to another one. The gateway decrypts them only
          when it connects, and they are masked in call results, logs and the audit log.
        </p>
      </div>
      {secrets.error ? (
        <ErrorState message={secrets.error.message} onRetry={() => secrets.refetch()} />
      ) : !secrets.data ? (
        <Skeleton className="h-32" />
      ) : secrets.data.length === 0 ? (
        <EmptyState
          icon={<KeyRound />}
          title="No secrets"
          description="This server does not need credentials, or none have been added yet."
        />
      ) : (
        <TableContainer label="Secrets">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Stored in</TableHead>
                <TableHead className="text-right">Version</TableHead>
                <TableHead className="text-right">Updated</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {secrets.data.map((secret) => (
                <TableRow key={secret.id}>
                  <TableCell className="font-mono text-[12.5px] font-medium">{secret.name}</TableCell>
                  <TableCell>
                    <Badge tone="outline">{secret.kind === "header" ? "header" : "environment"}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{BACKEND[secret.backend] ?? secret.backend}</TableCell>
                  <TableCell className="tabular text-right">{secret.version}</TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    <RelativeTime iso={secret.updated_at} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="danger-ghost"
                      size="icon-sm"
                      aria-label={`Delete ${secret.name}`}
                      onClick={() => setDeleting(secret)}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <SecretForm server={server} />
      <FieldHint>Changing or deleting a secret reconnects the server with the new credentials.</FieldHint>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "this secret"}?`}
        description="The gateway stops sending it to this server. If the server needs it, calls start failing until it is set again."
        confirmLabel="Delete secret"
        destructive
        onConfirm={async () => {
          if (deleting) await remove.mutateAsync(deleting.id);
          toast.success("Secret deleted.");
        }}
      />
    </div>
  );
}
