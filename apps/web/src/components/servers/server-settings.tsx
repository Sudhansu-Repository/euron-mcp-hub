"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/input";
import { useUpdateServer } from "@/lib/queries";
import type { Server } from "@/lib/types";

/** Edit how the gateway reaches and schedules a server. The namespace cannot change. */
export function ServerSettings({ server }: { server: Server }) {
  const update = useUpdateServer(server.slug, { silent: true });
  const [name, setName] = useState(server.name);
  const [description, setDescription] = useState(server.description);
  const [url, setUrl] = useState(server.url ?? "");
  const [timeout, setTimeoutS] = useState(String(server.timeout_s));
  const [refresh, setRefresh] = useState(String(server.refresh_interval_s));
  const [tags, setTags] = useState(server.tags.join(", "));
  const [owner, setOwner] = useState(server.owner);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await update.mutateAsync({
        name: name.trim(),
        description: description.trim(),
        url: server.transport === "streamable_http" ? url.trim() : undefined,
        timeout_s: Number(timeout),
        refresh_interval_s: Number(refresh),
        owner: owner.trim(),
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
    } catch {
      return;
    }
    toast.success("Server updated.");
  }

  return (
    <Card>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="server-name" required>
              <Input id="server-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
            <Field label="Namespace" htmlFor="server-slug" hint="Part of every tool name, so it cannot change.">
              <Input id="server-slug" value={server.slug} disabled readOnly />
            </Field>
          </div>
          {server.transport === "streamable_http" ? (
            <Field label="Server URL" htmlFor="server-url" required>
              <Input id="server-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} required />
            </Field>
          ) : (
            <Field
              label="Command"
              htmlFor="server-command"
              hint="The command and its arguments are fixed after registering."
            >
              <Input id="server-command" value={[server.command, ...server.args].join(" ")} disabled readOnly />
            </Field>
          )}
          <Field label="Description" htmlFor="server-description">
            <Textarea
              id="server-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-h-16"
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Call timeout (seconds)" htmlFor="server-timeout" hint="Calls that take longer are cut off.">
              <Input
                id="server-timeout"
                type="number"
                min={1}
                max={600}
                value={timeout}
                onChange={(e) => setTimeoutS(e.target.value)}
              />
            </Field>
            <Field
              label="Rediscover every (seconds)"
              htmlFor="server-refresh"
              hint="How often the worker re-reads the catalog."
            >
              <Input
                id="server-refresh"
                type="number"
                min={30}
                max={86400}
                value={refresh}
                onChange={(e) => setRefresh(e.target.value)}
              />
            </Field>
            <Field label="Owner" htmlFor="server-owner">
              <Input id="server-owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
            </Field>
            <Field label="Tags" htmlFor="server-tags" hint="Comma separated.">
              <Input id="server-tags" value={tags} onChange={(e) => setTags(e.target.value)} />
            </Field>
          </div>
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
