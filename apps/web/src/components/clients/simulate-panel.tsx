"use client";

import { CheckCircle2, CircleSlash, FlaskConical } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, NativeSelect, Textarea } from "@/components/ui/input";
import { useClientAccess, useSimulate } from "@/lib/queries";
import type { Client, Simulation } from "@/lib/types";

/** What would the gateway do with this call? Nothing is sent to any server. */
export function SimulatePanel({ client }: { client: Client }) {
  const access = useClientAccess(client.slug);
  const simulate = useSimulate(client.slug);
  const [tool, setTool] = useState("");
  const [args, setArgs] = useState("{}");
  const [parseError, setParseError] = useState<string | null>(null);
  const [result, setResult] = useState<Simulation | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(args || "{}");
    } catch {
      setParseError("The arguments are not valid JSON.");
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setParseError("The arguments must be a JSON object.");
      return;
    }
    setParseError(null);
    setResult(await simulate.mutateAsync({ tool, arguments: parsed as Record<string, unknown> }));
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Dry run</CardTitle>
          <CardDescription>
            Check a call against this client&apos;s rules, the tool&apos;s input schema and the argument constraints
            without calling anything.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Tool" htmlFor="sim-tool" required>
            <NativeSelect id="sim-tool" value={tool} onChange={(e) => setTool(e.target.value)} required>
              <option value="">Choose a tool</option>
              {access.data?.map((row) => (
                <option key={row.qualified_name} value={row.qualified_name}>
                  {row.qualified_name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Arguments (JSON)" htmlFor="sim-args">
            <Textarea
              id="sim-args"
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              className="font-mono text-[12.5px]"
              spellCheck={false}
            />
          </Field>
          {parseError ? <ErrorNotice message={parseError} /> : null}
          {simulate.error ? <ErrorNotice message={simulate.error.message} /> : null}
          <Button type="submit" loading={simulate.isPending}>
            <FlaskConical /> Check the call
          </Button>
        </form>
        {result ? (
          <div
            className={`mt-5 rounded-lg p-3.5 text-[13px] ${result.would_call ? "bg-success-soft text-success" : "bg-warning-soft text-warning"}`}
            role="status"
          >
            <p className="flex items-center gap-2 font-medium">
              {result.would_call ? (
                <CheckCircle2 className="size-4" aria-hidden />
              ) : (
                <CircleSlash className="size-4" aria-hidden />
              )}
              {result.would_call ? "This call would reach the server." : "This call would be refused."}
            </p>
            <p className="mt-1">{result.reason}</p>
            {result.rule_pattern ? <p className="mt-1">Decided by the rule for {result.rule_pattern}.</p> : null}
            {result.schema_errors.length > 0 ? (
              <ul className="mt-2 list-disc pl-5">
                {result.schema_errors.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            ) : null}
            {result.violations.length > 0 ? (
              <ul className="mt-2 list-disc pl-5">
                {result.violations.map((violation) => (
                  <li key={`${violation.argument}-${violation.rule}`}>{violation.message}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
