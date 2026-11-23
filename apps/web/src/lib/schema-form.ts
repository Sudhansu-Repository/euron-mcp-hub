import type { JsonSchema } from "@/lib/types";

export type FieldKind = "text" | "number" | "integer" | "boolean" | "enum" | "json";

export type FormField = {
  name: string;
  kind: FieldKind;
  required: boolean;
  description?: string;
  options?: string[];
  placeholder?: string;
};

function kindOf(schema: JsonSchema): FieldKind {
  if (schema.enum && schema.enum.every((option) => typeof option === "string")) return "enum";
  const type = Array.isArray(schema.type) ? schema.type.find((t) => t !== "null") : schema.type;
  if (type === "string") return "text";
  if (type === "integer") return "integer";
  if (type === "number") return "number";
  if (type === "boolean") return "boolean";
  return "json";
}

/** The fields a form needs for a tool's top-level arguments (nested values are edited as JSON). */
export function fieldsOf(schema: JsonSchema): FormField[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, property]) => ({
    name,
    kind: kindOf(property),
    required: required.has(name),
    description: property.description,
    options: property.enum?.map(String),
    placeholder: property.default === undefined ? undefined : String(property.default),
  }));
}

export type FormValues = Record<string, string | boolean>;

/**
 * Turn form values into call arguments. Empty optional fields are left out; a required
 * field that is empty, or a number or JSON value that does not parse, is reported by name.
 */
export function argumentsFrom(
  fields: FormField[],
  values: FormValues,
): { arguments: Record<string, unknown>; errors: string[] } {
  const result: Record<string, unknown> = {};
  const errors: string[] = [];
  for (const field of fields) {
    const raw = values[field.name];
    if (field.kind === "boolean") {
      if (raw === true || raw === false) result[field.name] = raw;
      else if (field.required) result[field.name] = false;
      continue;
    }
    const text = typeof raw === "string" ? raw.trim() : "";
    if (text === "") {
      if (field.required) errors.push(`${field.name} is required.`);
      continue;
    }
    if (field.kind === "number" || field.kind === "integer") {
      const value = Number(text);
      if (Number.isNaN(value) || (field.kind === "integer" && !Number.isInteger(value))) {
        errors.push(`${field.name} must be ${field.kind === "integer" ? "a whole number" : "a number"}.`);
      } else {
        result[field.name] = value;
      }
    } else if (field.kind === "json") {
      try {
        result[field.name] = JSON.parse(text);
      } catch {
        errors.push(`${field.name} must be valid JSON.`);
      }
    } else {
      result[field.name] = text;
    }
  }
  return { arguments: result, errors };
}
