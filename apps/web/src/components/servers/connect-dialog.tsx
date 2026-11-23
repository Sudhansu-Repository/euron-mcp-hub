"use client";

import { CheckCircle2, KeyRound, Plug, Plus, Trash2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, FieldHint, Input, Textarea } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { api, V1 } from "@/lib/api";
import { useCreateServer, useSetSecret, useSystemInfo } from "@/lib/queries";
import type { Discovery, SecretKind, Server, Transport } from "@/lib/types";
import { useQueryClient } from "@tanstack/react-query";

type Step = "details" | "credentials" | "result";
type SecretRow = { name: string; value: string };

const EMPTY_SECRET: SecretRow = { name: "Authorization", value: "" };

/**
 * Connect a server in three steps: where it is (and how to reach it), what credentials it
 * needs (written once, encrypted, never shown again), and what discovery found. The server is
 * created without discovery first so its credentials are in place before the gateway tries
 * to connect: a server that wants a token would otherwise fail its very first discovery.
 */
export function ConnectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const system = useSystemInfo();
  const client = useQueryClient();
  const [step, setStep] = useState<Step>("details");
  const [transport, setTransport] = useState<Transport>("streamable_http");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [created, setCreated] = useState<Server | null>(null);
  const [secrets, setSecrets] = useState<SecretRow[]>([{ ...EMPTY_SECRET }]);
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const create = useCreateServer({ silent: true });
  const setSecret = useSetSecret(created?.slug ?? "", { silent: true });
  const kind: SecretKind = transport === "stdio" ? "env" : "header";

  function reset() {
    setStep("details");
    setTransport("streamable_http");
    setName("");
    setSlug("");
    setUrl("");
    setCommand("");
    setArgs("");
    setDescription("");
    setTags("");
    setCreated(null);
    setSecrets([{ ...EMPTY_SECRET }]);
    setDiscovery(null);
    setError(null);
  }

  function close(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  async function submitDetails(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const server = await create.mutateAsync({
        name: name.trim(),
        slug: slug.trim() || undefined,
        description: description.trim(),
        transport,
        url: transport === "streamable_http" ? url.trim() : undefined,
        command: transport === "stdio" ? command.trim() : undefined,
        args: transport === "stdio" ? args.split(/\s+/).filter(Boolean) : undefined,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        discover: false,
      });
      setCreated(server);
      setSecrets([{ name: kind === "header" ? "Authorization" : "", value: "" }]);
      setStep("credentials");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not register the server.");
    }
  }

  async function discover(withSecrets: boolean) {
    if (!created) return;
    setError(null);
    setWorking(true);
    try {
      if (withSecrets) {
        for (const row of secrets.filter((r) => r.name.trim() && r.value)) {
          await setSecret.mutateAsync({ kind, name: row.name.trim(), value: row.value });
        }
      }
      const result = await api<Discovery>(`${V1}/servers/${encodeURIComponent(created.slug)}/refresh`, {
        method: "POST",
      });
      setDiscovery(result);
      await client.invalidateQueries({ queryKey: ["servers"] });
      await client.invalidateQueries({ queryKey: ["tools"] });
      setStep("result");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Discovery failed.");
    } finally {
      setWorking(false);
    }
  }

  const stdioBlocked = transport === "stdio" && system.data && system.data.stdio_commands.length === 0;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        className="w-[min(94vw,36rem)]"
        title={step === "details" ? "Connect an MCP server" : step === "credentials" ? "Credentials" : "Connected"}
        description={
          step === "details"
            ? "Tell the gateway where the server is. It connects, discovers the tools and starts checking its health."
            : step === "credentials"
              ? "If the server needs a token or a key, add it now. It is encrypted at once and never shown again."
              : created?.name
        }
      >
        {step === "details" ? (
          <form onSubmit={submitDetails} className="space-y-4">
            <SegmentedControl
              label="Transport"
              value={transport}
              onValueChange={setTransport}
              options={[
                { value: "streamable_http", label: "Streamable HTTP" },
                { value: "stdio", label: "stdio command" },
              ]}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="connect-name" required>
                <Input id="connect-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
              </Field>
              <Field label="Namespace" htmlFor="connect-slug" hint="Tools are named namespace.tool. Optional.">
                <Input
                  id="connect-slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase())}
                  placeholder="tickets"
                  pattern="[a-z0-9]([a-z0-9\-]*[a-z0-9])?"
                />
              </Field>
            </div>
            {transport === "streamable_http" ? (
              <Field
                label="Server URL"
                htmlFor="connect-url"
                required
                hint="The MCP endpoint, for example https://tickets.example.com/mcp"
              >
                <Input
                  id="connect-url"
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://"
                  required
                />
              </Field>
            ) : (
              <>
                <Field
                  label="Command"
                  htmlFor="connect-command"
                  required
                  hint={
                    system.data?.stdio_commands.length
                      ? `Allowed on this gateway: ${system.data.stdio_commands.join(", ")}`
                      : undefined
                  }
                >
                  <Input id="connect-command" value={command} onChange={(e) => setCommand(e.target.value)} required />
                </Field>
                <Field label="Arguments" htmlFor="connect-args" hint="Separated by spaces.">
                  <Input id="connect-args" value={args} onChange={(e) => setArgs(e.target.value)} />
                </Field>
                {stdioBlocked ? (
                  <ErrorNotice message="stdio servers are disabled on this gateway: an administrator lists the commands it may launch in STDIO_ALLOWED_COMMANDS." />
                ) : null}
              </>
            )}
            <Field label="Description" htmlFor="connect-description">
              <Textarea
                id="connect-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="min-h-16"
              />
            </Field>
            <Field label="Tags" htmlFor="connect-tags" hint="Comma separated.">
              <Input
                id="connect-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="support, internal"
              />
            </Field>
            {error ? <ErrorNotice message={error} /> : null}
            <DialogFooter>
              <Button variant="secondary" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending} disabled={Boolean(stdioBlocked)}>
                <Plug /> Continue
              </Button>
            </DialogFooter>
          </form>
        ) : null}

        {step === "credentials" ? (
          <div className="space-y-4">
            <div className="space-y-3">
              {secrets.map((row, index) => (
                <div key={index} className="grid grid-cols-[1fr_1.4fr_auto] items-end gap-2">
                  <Field label={kind === "header" ? "Header" : "Variable"} htmlFor={`secret-name-${index}`}>
                    <Input
                      id={`secret-name-${index}`}
                      value={row.name}
                      onChange={(e) =>
                        setSecrets((rows) => rows.map((r, i) => (i === index ? { ...r, name: e.target.value } : r)))
                      }
                    />
                  </Field>
                  <Field label="Value" htmlFor={`secret-value-${index}`}>
                    <Input
                      id={`secret-value-${index}`}
                      type="password"
                      autoComplete="off"
                      value={row.value}
                      placeholder={kind === "header" ? "Bearer ..." : ""}
                      onChange={(e) =>
                        setSecrets((rows) => rows.map((r, i) => (i === index ? { ...r, value: e.target.value } : r)))
                      }
                    />
                  </Field>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Remove this credential"
                    onClick={() => setSecrets((rows) => rows.filter((_, i) => i !== index))}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSecrets((rows) => [...rows, { name: "", value: "" }])}
              >
                <Plus /> Add another
              </Button>
            </div>
            <FieldHint className="flex items-start gap-1.5">
              <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              Encrypted with {system.data?.secrets_backend === "secretsmanager" ? "AWS Secrets Manager" : "KMS"} and
              injected only when the gateway connects.
            </FieldHint>
            {error ? <ErrorNotice message={error} /> : null}
            <DialogFooter>
              <Button variant="secondary" onClick={() => discover(false)} disabled={working}>
                Skip, no credentials
              </Button>
              <Button
                onClick={() => discover(true)}
                loading={working}
                disabled={!secrets.some((r) => r.name.trim() && r.value)}
              >
                Save and discover tools
              </Button>
            </DialogFooter>
          </div>
        ) : null}

        {step === "result" && discovery ? (
          <div className="space-y-4">
            {discovery.ok ? (
              <div className="bg-success-soft text-success flex items-start gap-2.5 rounded-lg p-3 text-[13px]">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
                <div>
                  <p className="font-medium">
                    Found {discovery.server.tool_count} tools, {discovery.server.resource_count} resources and{" "}
                    {discovery.server.prompt_count} prompts
                    {discovery.latency_ms !== null ? ` in ${discovery.latency_ms} ms.` : "."}
                  </p>
                  <p className="mt-0.5">
                    They are in the catalog now. Grant them to a client to make them callable through the gateway.
                  </p>
                </div>
              </div>
            ) : (
              <div className="bg-danger-soft text-danger flex items-start gap-2.5 rounded-lg p-3 text-[13px]">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                <div>
                  <p className="font-medium">The server is registered, but discovery failed.</p>
                  <p className="mt-0.5">{discovery.error}</p>
                  <p className="mt-0.5">Fix the address or credentials on the server page and refresh.</p>
                </div>
              </div>
            )}
            {discovery.ok && discovery.added.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {discovery.added.slice(0, 12).map((tool) => (
                  <Badge key={tool} tone="outline" className="font-mono">
                    {tool}
                  </Badge>
                ))}
              </div>
            ) : null}
            <DialogFooter>
              <Button variant="secondary" onClick={() => close(false)}>
                Close
              </Button>
              <Button asChild>
                <Link href={`/servers/${created?.slug ?? ""}`} onClick={() => close(false)}>
                  Open the server
                </Link>
              </Button>
            </DialogFooter>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
