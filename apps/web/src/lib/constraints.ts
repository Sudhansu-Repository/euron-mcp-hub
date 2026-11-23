import type { Constraint } from "@/lib/types";

export type ConstraintRule = Constraint["rule"];

export const CONSTRAINT_RULES: { value: ConstraintRule; label: string; help: string }[] = [
  { value: "one_of", label: "is one of", help: "Comma separated values, for example low, normal, high." },
  { value: "equals", label: "equals", help: "The value the argument must have." },
  { value: "pattern", label: "matches", help: "A regular expression the whole value must match." },
  { value: "max_length", label: "is at most this long", help: "The longest text or list allowed." },
  { value: "range", label: "is between", help: "Minimum and maximum, either may be empty." },
  { value: "forbidden", label: "must be absent", help: "The client may not pass this argument at all." },
];

/** A constraint as one readable phrase: `priority is one of low, normal`. */
export function describeConstraint(constraint: Constraint): string {
  const name = constraint.argument;
  switch (constraint.rule) {
    case "equals":
      return `${name} equals ${JSON.stringify(constraint.value)}`;
    case "one_of":
      return `${name} is one of ${constraint.values.map((value) => String(value)).join(", ")}`;
    case "pattern":
      return `${name} matches /${constraint.value}/`;
    case "max_length":
      return `${name} is at most ${constraint.value} long`;
    case "range": {
      const { min, max } = constraint;
      if (min != null && max != null) return `${name} is between ${min} and ${max}`;
      return min != null ? `${name} is at least ${min}` : `${name} is at most ${max}`;
    }
    case "forbidden":
      return `${name} must be absent`;
  }
}

/** Parse a typed value the way a person means it: numbers and booleans stay typed. */
export function parseValue(text: string): unknown {
  const trimmed = text.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed !== "" && !Number.isNaN(Number(trimmed))) return Number(trimmed);
  return trimmed;
}

export type ConstraintDraft = { argument: string; rule: ConstraintRule; text: string; min: string; max: string };

export const emptyDraft = (): ConstraintDraft => ({ argument: "", rule: "one_of", text: "", min: "", max: "" });

export function draftOf(constraint: Constraint): ConstraintDraft {
  const draft = { ...emptyDraft(), argument: constraint.argument, rule: constraint.rule };
  switch (constraint.rule) {
    case "equals":
      return { ...draft, text: String(constraint.value) };
    case "one_of":
      return { ...draft, text: constraint.values.map(String).join(", ") };
    case "pattern":
    case "max_length":
      return { ...draft, text: String(constraint.value) };
    case "range":
      return {
        ...draft,
        min: constraint.min == null ? "" : String(constraint.min),
        max: constraint.max == null ? "" : String(constraint.max),
      };
    case "forbidden":
      return draft;
  }
}

/** The constraint a draft describes, or a reason it cannot be saved yet. */
export function constraintOf(draft: ConstraintDraft): Constraint | string {
  const argument = draft.argument.trim();
  if (!argument) return "Name the argument each constraint applies to.";
  switch (draft.rule) {
    case "equals":
      return { argument, rule: "equals", value: parseValue(draft.text) };
    case "one_of": {
      const values = draft.text
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map(parseValue);
      return values.length ? { argument, rule: "one_of", values } : `List the allowed values for ${argument}.`;
    }
    case "pattern":
      return draft.text.trim()
        ? { argument, rule: "pattern", value: draft.text.trim() }
        : `Enter a pattern for ${argument}.`;
    case "max_length": {
      const value = Number(draft.text);
      return Number.isInteger(value) && value >= 0
        ? { argument, rule: "max_length", value }
        : `Enter a length for ${argument}.`;
    }
    case "range": {
      const min = draft.min.trim() === "" ? null : Number(draft.min);
      const max = draft.max.trim() === "" ? null : Number(draft.max);
      if (min === null && max === null) return `Set a minimum, a maximum or both for ${argument}.`;
      if ((min !== null && Number.isNaN(min)) || (max !== null && Number.isNaN(max)))
        return `Use numbers for ${argument}.`;
      return { argument, rule: "range", min, max };
    }
    case "forbidden":
      return { argument, rule: "forbidden" };
  }
}
