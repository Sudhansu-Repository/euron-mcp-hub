"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { KeyReveal } from "@/components/clients/key-reveal";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useCreateClient } from "@/lib/queries";
import type { ClientCreated, Effect } from "@/lib/types";

export function CreateClientDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreateClient({ silent: true });
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [effect, setEffect] = useState<Effect>("deny");
  const [separator, setSeparator] = useState<"." | "__">(".");
  const [rate, setRate] = useState("");
  const [created, setCreated] = useState<ClientCreated | null>(null);

  function close(next: boolean) {
    if (!next) {
      setName("");
      setSlug("");
      setDescription("");
      setEffect("deny");
      setSeparator(".");
      setRate("");
      setCreated(null);
      create.reset();
    }
    onOpenChange(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setCreated(
        await create.mutateAsync({
          name: name.trim(),
          slug: slug.trim() || undefined,
          description: description.trim(),
          default_effect: effect,
          tool_separator: separator,
          rate_limit_per_minute: rate ? Number(rate) : null,
        }),
      );
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        className="w-[min(94vw,36rem)]"
        title={created ? `${created.client.name} is ready` : "New client"}
        description={
          created
            ? "It starts with no permissions. Choose the tools it may call on its page."
            : "A client is one caller of the gateway, with its own key and permissions."
        }
      >
        {created ? (
          <div className="space-y-4">
            <KeyReveal secret={created.key.key} />
            <DialogFooter>
              <Button variant="secondary" onClick={() => close(false)}>
                Close
              </Button>
              <Button asChild>
                <Link href={`/clients/${created.client.slug}`} onClick={() => close(false)}>
                  Set permissions
                </Link>
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="client-name" required>
                <Input id="client-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
              </Field>
              <Field label="Slug" htmlFor="client-slug" hint="Used in URLs. Optional.">
                <Input
                  id="client-slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase())}
                  placeholder="support-copilot"
                  pattern="[a-z0-9]([a-z0-9\-]*[a-z0-9])?"
                />
              </Field>
            </div>
            <Field label="Description" htmlFor="client-description">
              <Textarea
                id="client-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="min-h-16"
              />
            </Field>
            <div className="space-y-1.5">
              <p className="text-[13px] font-medium">A tool no rule mentions is</p>
              <SegmentedControl
                label="Default for tools without a rule"
                value={effect}
                onValueChange={setEffect}
                options={[
                  { value: "deny", label: "Denied (recommended)" },
                  { value: "allow", label: "Allowed" },
                ]}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Tool names"
                htmlFor="client-separator"
                hint="Some model APIs reject dots in function names."
              >
                <NativeSelect
                  id="client-separator"
                  value={separator}
                  onChange={(e) => setSeparator(e.target.value as "." | "__")}
                >
                  <option value=".">server.tool</option>
                  <option value="__">server__tool</option>
                </NativeSelect>
              </Field>
              <Field label="Calls per minute" htmlFor="client-rate" hint="Empty means no limit.">
                <Input
                  id="client-rate"
                  type="number"
                  min={1}
                  max={100000}
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                />
              </Field>
            </div>
            {create.error ? <ErrorNotice message={create.error.message} /> : null}
            <DialogFooter>
              <Button variant="secondary" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending}>
                Create client and key
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
