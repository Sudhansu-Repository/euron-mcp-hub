"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { EmptyState, ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  CONSTRAINT_RULES,
  constraintOf,
  describeConstraint,
  draftOf,
  emptyDraft,
  type ConstraintDraft,
} from "@/lib/constraints";
import { useClientRules, useCreateRule, useDeleteRule, useUpdateRule } from "@/lib/queries";
import type { Constraint, Effect, Rule } from "@/lib/types";

function RuleDialog({
  slug,
  rule,
  open,
  onOpenChange,
}: {
  slug: string;
  rule: Rule | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const create = useCreateRule(slug, { silent: true });
  const update = useUpdateRule(slug, { silent: true });
  const [pattern, setPattern] = useState(rule?.pattern ?? "");
  const [effect, setEffect] = useState<Effect>(rule?.effect ?? "allow");
  const [rate, setRate] = useState(rule?.rate_limit_per_minute ? String(rule.rate_limit_per_minute) : "");
  const [redact, setRedact] = useState(rule?.redact.join(", ") ?? "");
  const [description, setDescription] = useState(rule?.description ?? "");
  const [drafts, setDrafts] = useState<ConstraintDraft[]>(rule?.constraints.map(draftOf) ?? []);
  const [problem, setProblem] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;
  const failure = create.error ?? update.error;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const constraints: Constraint[] = [];
    for (const draft of drafts) {
      const built = constraintOf(draft);
      if (typeof built === "string") {
        setProblem(built);
        return;
      }
      constraints.push(built);
    }
    setProblem(null);
    const body = {
      pattern: pattern.trim(),
      effect,
      constraints,
      rate_limit_per_minute: rate ? Number(rate) : null,
      redact: redact
        .split(",")
        .map((path) => path.trim())
        .filter(Boolean),
      description: description.trim(),
    };
    try {
      if (rule) await update.mutateAsync({ id: rule.id, ...body });
      else await create.mutateAsync(body);
    } catch {
      return;
    }
    toast.success(rule ? "Rule updated." : "Rule added.");
    onOpenChange(false);
  }

  const setDraft = (index: number, patch: Partial<ConstraintDraft>) =>
    setDrafts((list) => list.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="w-[min(94vw,38rem)]"
        title={rule ? "Edit rule" : "Add a rule"}
        description="The most specific matching rule decides: an exact tool name beats tickets.get_*, which beats tickets.*, which beats *."
      >
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <Field
              label="Tools"
              htmlFor="rule-pattern"
              required
              hint="server.tool with * and ? wildcards: tickets.*, notes.get_note, *."
            >
              <Input
                id="rule-pattern"
                value={pattern}
                onChange={(e) => setPattern(e.target.value)}
                placeholder="tickets.*"
                required
                autoFocus
              />
            </Field>
            <SegmentedControl
              label="Effect"
              value={effect}
              onValueChange={setEffect}
              options={[
                { value: "allow", label: "Allow" },
                { value: "deny", label: "Deny" },
              ]}
            />
          </div>

          {effect === "allow" ? (
            <fieldset className="space-y-2">
              <legend className="text-[13px] font-medium">Argument constraints</legend>
              <p className="text-muted-foreground text-xs">
                Calls whose arguments break a constraint are refused before they reach the server.
              </p>
              {drafts.map((draft, index) => (
                <div key={index} className="border-border bg-muted/40 space-y-2 rounded-lg border p-2.5">
                  <div className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
                    <Input
                      aria-label="Argument"
                      placeholder="priority"
                      value={draft.argument}
                      onChange={(e) => setDraft(index, { argument: e.target.value })}
                    />
                    <NativeSelect
                      aria-label="Constraint"
                      value={draft.rule}
                      onChange={(e) => setDraft(index, { rule: e.target.value as ConstraintDraft["rule"] })}
                    >
                      {CONSTRAINT_RULES.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </NativeSelect>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Remove constraint"
                      onClick={() => setDrafts((list) => list.filter((_, i) => i !== index))}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                  {draft.rule === "range" ? (
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        aria-label="Minimum"
                        placeholder="minimum"
                        value={draft.min}
                        onChange={(e) => setDraft(index, { min: e.target.value })}
                      />
                      <Input
                        aria-label="Maximum"
                        placeholder="maximum"
                        value={draft.max}
                        onChange={(e) => setDraft(index, { max: e.target.value })}
                      />
                    </div>
                  ) : draft.rule !== "forbidden" ? (
                    <Input
                      aria-label="Value"
                      placeholder={CONSTRAINT_RULES.find((r) => r.value === draft.rule)?.help}
                      value={draft.text}
                      onChange={(e) => setDraft(index, { text: e.target.value })}
                    />
                  ) : null}
                </div>
              ))}
              <Button variant="secondary" size="sm" onClick={() => setDrafts((list) => [...list, emptyDraft()])}>
                <Plus /> Add a constraint
              </Button>
            </fieldset>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            {effect === "allow" ? (
              <Field label="Calls per minute" htmlFor="rule-rate" hint="For this rule's tools together.">
                <Input id="rule-rate" type="number" min={1} value={rate} onChange={(e) => setRate(e.target.value)} />
              </Field>
            ) : null}
            <Field
              label="Keep out of the audit log"
              htmlFor="rule-redact"
              hint="Argument paths, comma separated: customer.email"
              className={effect === "deny" ? "sm:col-span-2" : undefined}
            >
              <Input id="rule-redact" value={redact} onChange={(e) => setRedact(e.target.value)} />
            </Field>
          </div>
          <Field
            label="Why"
            htmlFor="rule-description"
            hint="Shown next to the rule so the next person knows its purpose."
          >
            <Input id="rule-description" value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          {problem ? <ErrorNotice message={problem} /> : failure ? <ErrorNotice message={failure.message} /> : null}
          <DialogFooter>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={pending}>
              {rule ? "Save rule" : "Add rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RulesPanel({ slug, canWrite }: { slug: string; canWrite: boolean }) {
  const rules = useClientRules(slug);
  const remove = useDeleteRule(slug);
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const [deleting, setDeleting] = useState<Rule | null>(null);

  if (rules.error) return <ErrorState message={rules.error.message} onRetry={() => rules.refetch()} />;
  if (!rules.data) return <Skeleton className="h-48" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground max-w-2xl text-[13px]">
          Rules decide which tools this client sees and what it may pass them. The most specific pattern wins; two rules
          of equal specificity deny.
        </p>
        {canWrite ? (
          <Button onClick={() => setEditing("new")}>
            <Plus /> Add a rule
          </Button>
        ) : null}
      </div>
      {rules.data.length === 0 ? (
        <EmptyState title="No rules" description="Without rules this client gets only what its default allows." />
      ) : (
        <TableContainer label="Rules">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pattern</TableHead>
                <TableHead>Effect</TableHead>
                <TableHead>Constraints and limits</TableHead>
                <TableHead>Why</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.data.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="font-mono text-[12.5px] font-medium">{rule.pattern}</TableCell>
                  <TableCell>
                    <Badge tone={rule.effect === "allow" ? "success" : "danger"}>
                      {rule.effect === "allow" ? "Allow" : "Deny"}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-md">
                    <ul className="text-muted-foreground space-y-0.5 text-[12.5px]">
                      {rule.constraints.map((constraint, index) => (
                        <li key={index}>{describeConstraint(constraint)}</li>
                      ))}
                      {rule.rate_limit_per_minute ? <li>{rule.rate_limit_per_minute} calls per minute</li> : null}
                      {rule.redact.length ? <li>Not logged: {rule.redact.join(", ")}</li> : null}
                      {!rule.constraints.length && !rule.rate_limit_per_minute && !rule.redact.length ? (
                        <li>None</li>
                      ) : null}
                    </ul>
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-xs">{rule.description}</TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {canWrite ? (
                      <>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Edit ${rule.pattern}`}
                          onClick={() => setEditing(rule)}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="danger-ghost"
                          size="icon-sm"
                          aria-label={`Delete ${rule.pattern}`}
                          onClick={() => setDeleting(rule)}
                        >
                          <Trash2 />
                        </Button>
                      </>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {editing ? (
        <RuleDialog
          key={editing === "new" ? "new" : editing.id}
          slug={slug}
          rule={editing === "new" ? null : editing}
          open
          onOpenChange={(open) => !open && setEditing(null)}
        />
      ) : null}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete the rule for ${deleting?.pattern ?? ""}?`}
        description="Tools it covered fall back to broader rules and the client's default."
        confirmLabel="Delete rule"
        destructive
        onConfirm={async () => {
          if (deleting) await remove.mutateAsync(deleting.id);
          toast.success("Rule deleted.");
        }}
      />
    </div>
  );
}
