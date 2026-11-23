"use client";

import { Ban, KeyRound, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { KeyReveal } from "@/components/clients/key-reveal";
import { RelativeTime } from "@/components/domain/relative-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { EmptyState, ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useClientKeys, useCreateKey, useRevokeKey } from "@/lib/queries";
import type { ApiKey, ApiKeyCreated } from "@/lib/types";

export function keyState(key: ApiKey, now = new Date()): "active" | "revoked" | "expired" {
  if (key.revoked_at) return "revoked";
  if (key.expires_at && new Date(key.expires_at) <= now) return "expired";
  return "active";
}

export function KeyStateBadge({ keyData }: { keyData: ApiKey }) {
  const state = keyState(keyData);
  return (
    <Badge tone={state === "active" ? "success" : "neutral"}>
      {state === "active" ? "Active" : state === "revoked" ? "Revoked" : "Expired"}
    </Badge>
  );
}

function NewKeyDialog({
  slug,
  open,
  onOpenChange,
}: {
  slug: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const create = useCreateKey(slug, { silent: true });
  const [name, setName] = useState("");
  const [days, setDays] = useState("");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  function close(next: boolean) {
    if (!next) {
      setName("");
      setDays("");
      setCreated(null);
      create.reset();
    }
    onOpenChange(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setCreated(await create.mutateAsync({ name: name.trim(), expires_in_days: days ? Number(days) : null }));
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        className="w-[min(94vw,36rem)]"
        title={created ? "Key created" : "New API key"}
        description={created ? undefined : "Give each tool or deployment its own key, so one can be revoked alone."}
      >
        {created ? (
          <div className="space-y-4">
            <KeyReveal secret={created.key} />
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="Name" htmlFor="key-name" required hint="Where this key is used: Laptop, CI, Production.">
              <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </Field>
            <Field label="Expires" htmlFor="key-expiry">
              <NativeSelect id="key-expiry" value={days} onChange={(e) => setDays(e.target.value)}>
                <option value="">Never</option>
                <option value="7">In 7 days</option>
                <option value="30">In 30 days</option>
                <option value="90">In 90 days</option>
                <option value="365">In a year</option>
              </NativeSelect>
            </Field>
            {create.error ? <ErrorNotice message={create.error.message} /> : null}
            <DialogFooter>
              <Button variant="secondary" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending}>
                Create key
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function KeysPanel({ slug, canWrite }: { slug: string; canWrite: boolean }) {
  const keys = useClientKeys(slug);
  const revoke = useRevokeKey(slug);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);

  if (keys.error) return <ErrorState message={keys.error.message} onRetry={() => keys.refetch()} />;
  if (!keys.data) return <Skeleton className="h-40" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground max-w-2xl text-[13px]">
          A key identifies this client at the gateway. Only a keyed hash is stored, so a key can be shown once and never
          again.
        </p>
        {canWrite ? (
          <Button onClick={() => setCreating(true)}>
            <Plus /> New key
          </Button>
        ) : null}
      </div>
      {keys.data.length === 0 ? (
        <EmptyState
          icon={<KeyRound />}
          title="No keys"
          description="Create a key so this client can call the gateway."
        />
      ) : (
        <TableContainer label="API keys">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Last used</TableHead>
                <TableHead className="text-right">Expires</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.data.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-[12.5px]">mch_{key.prefix}_...</TableCell>
                  <TableCell>
                    <KeyStateBadge keyData={key} />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    <RelativeTime iso={key.last_used_at} />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    {key.expires_at ? <RelativeTime iso={key.expires_at} /> : "never"}
                  </TableCell>
                  <TableCell className="text-right">
                    {canWrite && keyState(key) === "active" ? (
                      <Button variant="danger-ghost" size="sm" onClick={() => setRevoking(key)}>
                        <Ban /> Revoke
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <NewKeyDialog slug={slug} open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke ${revoking?.name ?? "this key"}?`}
        description="Anything using it stops working at once. This cannot be undone; create a new key to replace it."
        confirmLabel="Revoke key"
        destructive
        onConfirm={async () => {
          if (revoking) await revoke.mutateAsync(revoking.id);
          toast.success("Key revoked.");
        }}
      />
    </div>
  );
}
