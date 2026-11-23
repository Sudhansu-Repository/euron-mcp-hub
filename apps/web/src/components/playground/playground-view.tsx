"use client";

import { Play } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";

import { JsonView } from "@/components/domain/json-view";
import { CallStatusBadge } from "@/components/domain/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { Field, FieldHint, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { formatDuration } from "@/lib/format";
import { useCan, useClientAccess, useClients, usePlaygroundCall, useTools } from "@/lib/queries";
import { argumentsFrom, fieldsOf, type FormField, type FormValues } from "@/lib/schema-form";
import { useUrlParams } from "@/lib/use-url-params";
import type { PlaygroundResult } from "@/lib/types";

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value: string | boolean | undefined;
  onChange: (value: string | boolean) => void;
}) {
  const id = `arg-${field.name}`;
  const label = (
    <span className="font-mono text-[12.5px]">
      {field.name}
      <span className="text-muted-foreground ml-2 font-sans text-[11.5px]">
        {field.kind === "enum" ? "choice" : field.kind}
      </span>
    </span>
  );
  if (field.kind === "boolean") {
    return (
      <label className="flex items-center gap-3 py-1 text-[13px]">
        <Switch checked={value === true} onCheckedChange={onChange} aria-label={field.name} />
        {label}
        {field.description ? <span className="text-muted-foreground text-xs">{field.description}</span> : null}
      </label>
    );
  }
  return (
    <Field label={label} htmlFor={id} required={field.required} hint={field.description}>
      {field.kind === "enum" ? (
        <NativeSelect id={id} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)}>
          <option value="">{field.required ? "Choose" : "Not set"}</option>
          {field.options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </NativeSelect>
      ) : field.kind === "json" ? (
        <Textarea
          id={id}
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-16 font-mono text-[12.5px]"
          placeholder="JSON"
          spellCheck={false}
        />
      ) : (
        <Input
          id={id}
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
          inputMode={field.kind === "text" ? undefined : "decimal"}
          placeholder={field.placeholder}
        />
      )}
    </Field>
  );
}

function Outcome({ result }: { result: PlaygroundResult }) {
  const text = result.content.filter((block) => block.type === "text").map((block) => block.text ?? "");
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Result <CallStatusBadge status={result.call.status} />
          </CardTitle>
          <CardDescription>
            {formatDuration(result.call.latency_ms)} through the gateway
            {result.call.upstream_ms !== null ? `, ${formatDuration(result.call.upstream_ms)} at the server` : ""}.{" "}
            <Link
              href={`/calls?q=${encodeURIComponent(result.call.tool_name)}&source=playground`}
              className="text-primary underline underline-offset-2"
            >
              Open it in the audit log
            </Link>
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {result.error ? <ErrorNotice message={result.error} /> : null}
        {result.call.error_message && !result.error ? <ErrorNotice message={result.call.error_message} /> : null}
        {text.map((block, index) => (
          <JsonView key={index} value={tryFormat(block)} label="Result text" />
        ))}
        {result.structured_content != null ? (
          <div>
            <p className="text-muted-foreground mb-1 text-xs font-medium">Structured content</p>
            <JsonView value={result.structured_content} label="Structured result" />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function tryFormat(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

/**
 * The tool tester: a real call through the gateway, as one of the clients. The same policy,
 * schema checks, limits and audit trail apply as for any agent, so what works here works
 * for the client, and a refusal here is the refusal the client would get.
 */
export function PlaygroundView() {
  const { params, update } = useUrlParams();
  const clients = useClients({ limit: 200, status: "active" });
  const canCall = useCan("operator");
  const clientSlug = params.get("client") ?? clients.data?.items[0]?.slug ?? "";
  const toolName = params.get("tool") ?? "";
  const access = useClientAccess(clientSlug);
  const catalog = useTools({ limit: 200 });
  const call = usePlaygroundCall();
  const [mode, setMode] = useState<"form" | "json">("form");
  const [values, setValues] = useState<FormValues>({});
  const [json, setJson] = useState("{}");
  const [problems, setProblems] = useState<string[]>([]);
  const [result, setResult] = useState<PlaygroundResult | null>(null);

  const row = access.data?.find((candidate) => candidate.qualified_name === toolName);
  const tool = catalog.data?.items.find((candidate) => candidate.qualified_name === toolName);
  const fields = useMemo(() => (tool ? fieldsOf(tool.input_schema) : []), [tool]);

  function choose(next: string) {
    update({ tool: next || null });
    setValues({});
    setJson("{}");
    setProblems([]);
    setResult(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    let args: Record<string, unknown>;
    if (mode === "form") {
      const built = argumentsFrom(fields, values);
      setProblems(built.errors);
      if (built.errors.length) return;
      args = built.arguments;
    } else {
      try {
        const parsed: unknown = JSON.parse(json || "{}");
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error("not an object");
        args = parsed as Record<string, unknown>;
        setProblems([]);
      } catch {
        setProblems(["The arguments must be a JSON object."]);
        return;
      }
    }
    setResult(await call.mutateAsync({ client: clientSlug, tool: toolName, arguments: args }));
  }

  const accessRows = access.data;
  const grouped = useMemo(() => {
    const map = new Map<string, NonNullable<typeof accessRows>>();
    for (const item of accessRows ?? []) map.set(item.server_name, [...(map.get(item.server_name) ?? []), item]);
    return [...map.entries()];
  }, [accessRows]);

  return (
    <PageBody>
      <PageHeader
        title="Tool tester"
        description="Call any tool through the gateway as one of your clients. The call follows the client's policy and is recorded in the audit log."
      />
      {clients.data && clients.data.items.length === 0 ? (
        <EmptyState
          title="No clients yet"
          description="Create a client first: the tester calls tools as a client, under its permissions."
          action={
            <Button asChild>
              <Link href="/clients">Go to clients</Link>
            </Button>
          }
        />
      ) : !clients.data ? (
        <Skeleton className="h-72" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
          <Card>
            <CardContent>
              <form onSubmit={submit} className="space-y-4">
                <Field label="Call as" htmlFor="tester-client">
                  <NativeSelect
                    id="tester-client"
                    value={clientSlug}
                    onChange={(event) => {
                      update({ client: event.target.value });
                      setResult(null);
                    }}
                  >
                    {clients.data.items.map((client) => (
                      <option key={client.slug} value={client.slug}>
                        {client.name}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Tool" htmlFor="tester-tool">
                  <NativeSelect
                    id="tester-tool"
                    value={toolName}
                    onChange={(event) => choose(event.target.value)}
                    required
                  >
                    <option value="">Choose a tool</option>
                    {grouped.map(([server, rows]) => (
                      <optgroup key={server} label={server}>
                        {rows.map((item) => (
                          <option key={item.qualified_name} value={item.qualified_name}>
                            {item.qualified_name}
                            {item.allowed ? "" : " (denied)"}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </NativeSelect>
                </Field>
                {row ? (
                  <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
                    <Badge tone={row.allowed ? "success" : "warning"}>{row.allowed ? "Allowed" : "Denied"}</Badge>
                    <span className="text-muted-foreground">{row.reason}</span>
                  </div>
                ) : null}
                {tool ? (
                  <>
                    <p className="text-muted-foreground text-[13px]">{tool.description}</p>
                    <SegmentedControl
                      label="Argument editor"
                      size="sm"
                      value={mode}
                      onValueChange={setMode}
                      options={[
                        { value: "form", label: "Form" },
                        { value: "json", label: "JSON" },
                      ]}
                    />
                    {mode === "form" ? (
                      fields.length === 0 ? (
                        <FieldHint>This tool takes no arguments.</FieldHint>
                      ) : (
                        <div className="space-y-3">
                          {fields.map((field) => (
                            <FieldInput
                              key={field.name}
                              field={field}
                              value={values[field.name]}
                              onChange={(next) => setValues((state) => ({ ...state, [field.name]: next }))}
                            />
                          ))}
                        </div>
                      )
                    ) : (
                      <Field label="Arguments" htmlFor="tester-json">
                        <Textarea
                          id="tester-json"
                          value={json}
                          onChange={(event) => setJson(event.target.value)}
                          className="min-h-32 font-mono text-[12.5px]"
                          spellCheck={false}
                        />
                      </Field>
                    )}
                  </>
                ) : null}
                {problems.length ? <ErrorNotice message={problems.join(" ")} /> : null}
                {call.error ? <ErrorNotice message={call.error.message} /> : null}
                <Button type="submit" disabled={!toolName || !canCall} loading={call.isPending}>
                  <Play /> Call the tool
                </Button>
                {!canCall ? <FieldHint>Viewers can read the audit log but cannot make calls.</FieldHint> : null}
              </form>
            </CardContent>
          </Card>
          <div>
            {result ? (
              <Outcome result={result} />
            ) : (
              <EmptyState
                title="Pick a tool and call it"
                description="The result, its status and how long it took appear here."
                className="border-border rounded-xl border border-dashed py-20"
              />
            )}
          </div>
        </div>
      )}
    </PageBody>
  );
}
