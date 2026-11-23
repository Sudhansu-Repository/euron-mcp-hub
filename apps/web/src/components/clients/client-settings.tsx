"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { useUpdateClient } from "@/lib/queries";
import type { Client, Effect } from "@/lib/types";

export function ClientSettings({ client }: { client: Client }) {
  const update = useUpdateClient(client.slug, { silent: true });
  const [name, setName] = useState(client.name);
  const [description, setDescription] = useState(client.description);
  const [effect, setEffect] = useState<Effect>(client.default_effect);
  const [separator, setSeparator] = useState(client.tool_separator);
  const [rate, setRate] = useState(client.rate_limit_per_minute ? String(client.rate_limit_per_minute) : "");
  const [record, setRecord] = useState(client.record_arguments);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await update.mutateAsync({
        name: name.trim(),
        description: description.trim(),
        default_effect: effect,
        tool_separator: separator,
        rate_limit_per_minute: rate ? Number(rate) : null,
        record_arguments: record,
      });
    } catch {
      return;
    }
    toast.success("Client updated.");
  }

  return (
    <Card>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Name" htmlFor="client-edit-name" required>
            <Input id="client-edit-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Description" htmlFor="client-edit-description">
            <Textarea
              id="client-edit-description"
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
                { value: "deny", label: "Denied" },
                { value: "allow", label: "Allowed" },
              ]}
            />
            {effect === "allow" ? (
              <p className="text-warning text-xs">
                New tools from any server are available to this client as soon as they are discovered.
              </p>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tool names" htmlFor="client-edit-separator">
              <NativeSelect
                id="client-edit-separator"
                value={separator}
                onChange={(e) => setSeparator(e.target.value as "." | "__")}
              >
                <option value=".">server.tool</option>
                <option value="__">server__tool</option>
              </NativeSelect>
            </Field>
            <Field label="Calls per minute" htmlFor="client-edit-rate" hint="Empty means no limit.">
              <Input
                id="client-edit-rate"
                type="number"
                min={1}
                value={rate}
                onChange={(e) => setRate(e.target.value)}
              />
            </Field>
          </div>
          <label className="flex items-start gap-3 text-[13px]">
            <Switch
              checked={record}
              onCheckedChange={setRecord}
              aria-label="Record call arguments"
              className="mt-0.5"
            />
            <span>
              <span className="block font-medium">Record call arguments in the audit log</span>
              <span className="text-muted-foreground">
                Credentials are always masked. Turn this off for clients whose arguments are sensitive.
              </span>
            </span>
          </label>
          {update.error ? <ErrorNotice message={update.error.message} /> : null}
          <div className="flex justify-end">
            <Button type="submit" loading={update.isPending}>
              Save changes
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
