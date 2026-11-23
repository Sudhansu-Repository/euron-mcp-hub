import { Badge } from "@/components/ui/badge";
import type { JsonSchema } from "@/lib/types";

function typeOf(schema: JsonSchema): string {
  if (schema.enum) return schema.enum.map(String).join(" | ");
  if (Array.isArray(schema.type)) return schema.type.join(" | ");
  if (schema.type === "array") return `${schema.items ? typeOf(schema.items) : "any"}[]`;
  if (schema.type) return schema.type;
  if (schema.anyOf) return schema.anyOf.map(typeOf).join(" | ");
  return "any";
}

/** A tool's input schema as a readable list of arguments instead of raw JSON Schema. */
export function SchemaView({ schema }: { schema: JsonSchema }) {
  const properties = Object.entries(schema.properties ?? {});
  const required = new Set(schema.required ?? []);
  if (properties.length === 0) {
    return <p className="text-muted-foreground text-[13px]">This tool takes no arguments.</p>;
  }
  return (
    <ul className="divide-border divide-y">
      {properties.map(([name, property]) => (
        <li key={name} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
          <code className="font-mono text-[12.5px] font-medium">{name}</code>
          <span className="text-muted-foreground font-mono text-[12px]">{typeOf(property)}</span>
          {required.has(name) ? <Badge tone="primary">required</Badge> : null}
          {property.description ? (
            <span className="text-muted-foreground w-full text-[12.5px]">{property.description}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
