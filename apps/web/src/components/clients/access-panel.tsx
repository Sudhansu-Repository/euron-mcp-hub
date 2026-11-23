"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { ToolHints } from "@/components/domain/status-badge";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/cn";
import { useClientAccess, useClientRules, useCreateRule, useDeleteRule, useUpdateRule } from "@/lib/queries";
import type { Access, Client, Effect, Rule } from "@/lib/types";

type Choice = "default" | "allow" | "deny";

/** The exact rule for one tool or one whole server, if the client has it. */
function ruleFor(rules: Rule[], pattern: string): Rule | undefined {
  return rules.find((rule) => rule.pattern === pattern);
}

function ChoiceControl({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: Choice;
  disabled: boolean;
  onChange: (choice: Choice) => void;
}) {
  return (
    <fieldset disabled={disabled} className={cn(disabled && "opacity-60")}>
      <SegmentedControl
        size="sm"
        label={label}
        value={value}
        onValueChange={onChange}
        options={[
          { value: "default", label: "Inherit" },
          { value: "allow", label: "Allow" },
          { value: "deny", label: "Deny" },
        ]}
      />
    </fieldset>
  );
}

/**
 * The permission matrix: every tool in the catalog against this client. The control on a row
 * sets an exact rule for that tool ("Inherit" removes it, so broader rules and the client
 * default decide again); the control on a server header does the same for `server.*`. The
 * badge says what the client actually gets and which rule decided it.
 */
export function AccessPanel({ client, canWrite }: { client: Client; canWrite: boolean }) {
  const access = useClientAccess(client.slug);
  const rules = useClientRules(client.slug);
  const create = useCreateRule(client.slug);
  const update = useUpdateRule(client.slug);
  const remove = useDeleteRule(client.slug);
  const [text, setText] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const busy = create.isPending || update.isPending || remove.isPending;

  const grouped = useMemo(() => {
    const needle = text.trim().toLowerCase();
    const map = new Map<string, { name: string; tools: Access[] }>();
    for (const row of access.data ?? []) {
      if (needle && !`${row.qualified_name} ${row.description}`.toLowerCase().includes(needle)) continue;
      const group = map.get(row.server_slug) ?? { name: row.server_name, tools: [] };
      group.tools.push(row);
      map.set(row.server_slug, group);
    }
    return [...map.entries()];
  }, [access.data, text]);

  if (access.error) return <ErrorState message={access.error.message} onRetry={() => access.refetch()} />;
  if (!access.data || !rules.data) return <Skeleton className="h-72" />;
  if (access.data.length === 0) {
    return <EmptyState title="No tools in the catalog" description="Connect a server and its tools appear here." />;
  }

  async function choose(pattern: string, choice: Choice) {
    const existing = ruleFor(rules.data ?? [], pattern);
    if (choice === "default") {
      if (existing) await remove.mutateAsync(existing.id);
    } else if (existing) {
      if (existing.effect !== choice) await update.mutateAsync({ id: existing.id, effect: choice });
    } else {
      await create.mutateAsync({ pattern, effect: choice as Effect });
    }
  }

  const choiceOf = (pattern: string): Choice => ruleFor(rules.data ?? [], pattern)?.effect ?? "default";
  const allowed = access.data.filter((row) => row.allowed).length;

  return (
    <div className="space-y-4">
      <FilterBar>
        <SearchField value={text} onChange={setText} label="Filter tools" placeholder="Filter tools" />
        <p className="text-muted-foreground tabular text-[13px]" aria-live="polite">
          {allowed} of {access.data.length} tools allowed
        </p>
      </FilterBar>
      {grouped.length === 0 ? (
        <EmptyState title="No tools match" description="Try a different filter." />
      ) : (
        grouped.map(([slug, group]) => {
          const expanded = open[slug] ?? true;
          const count = group.tools.filter((row) => row.allowed).length;
          return (
            <section key={slug} className="border-border bg-card overflow-hidden rounded-xl border shadow-sm">
              <header className="bg-muted/60 flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpen((state) => ({ ...state, [slug]: !expanded }))}
                  className="flex items-center gap-2 text-left text-[13.5px] font-semibold"
                >
                  {expanded ? (
                    <ChevronDown className="size-4" aria-hidden />
                  ) : (
                    <ChevronRight className="size-4" aria-hidden />
                  )}
                  {group.name}
                  <code className="text-muted-foreground font-mono text-[12px] font-normal">{slug}</code>
                  <Badge tone={count === group.tools.length ? "success" : count === 0 ? "neutral" : "info"}>
                    {count}/{group.tools.length} allowed
                  </Badge>
                </button>
                {canWrite ? (
                  <ChoiceControl
                    label={`Whole ${group.name} server`}
                    value={choiceOf(`${slug}.*`)}
                    disabled={busy}
                    onChange={(choice) => void choose(`${slug}.*`, choice)}
                  />
                ) : null}
              </header>
              {expanded ? (
                <ul className="divide-border divide-y">
                  {group.tools.map((row) => (
                    <li
                      key={row.qualified_name}
                      className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5"
                    >
                      <div className="min-w-0 flex-1 basis-64">
                        <div className="flex flex-wrap items-center gap-2">
                          <code className="font-mono text-[12.5px] font-medium">{row.exposed_name}</code>
                          <ToolHints readOnly={row.read_only} destructive={row.destructive} />
                        </div>
                        <p className="text-muted-foreground mt-0.5 line-clamp-1 text-[12.5px]">{row.description}</p>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-3">
                        <span className="flex items-center gap-1.5 text-[12.5px]">
                          <Badge tone={row.allowed ? "success" : "neutral"}>{row.allowed ? "Allowed" : "Denied"}</Badge>
                          <span className="text-muted-foreground max-w-48 truncate" title={row.reason}>
                            {row.rule_pattern ? `by ${row.rule_pattern}` : "client default"}
                          </span>
                        </span>
                        {canWrite ? (
                          <ChoiceControl
                            label={`Permission for ${row.qualified_name}`}
                            value={choiceOf(row.qualified_name)}
                            disabled={busy}
                            onChange={(choice) => void choose(row.qualified_name, choice)}
                          />
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          );
        })
      )}
    </div>
  );
}
