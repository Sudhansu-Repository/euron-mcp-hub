import { describe, expect, it } from "vitest";

import { argumentsFrom, fieldsOf } from "@/lib/schema-form";

const SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string", description: "Short summary" },
    priority: { type: "string", enum: ["low", "normal", "high"] },
    limit: { type: "integer", default: 10 },
    ratio: { type: "number" },
    dry_run: { type: "boolean" },
    tags: { type: "array", items: { type: "string" } },
  },
  required: ["title"],
};

describe("fieldsOf", () => {
  it("maps schema types to field kinds", () => {
    const fields = fieldsOf(SCHEMA);
    expect(fields.map((f) => [f.name, f.kind])).toEqual([
      ["title", "text"],
      ["priority", "enum"],
      ["limit", "integer"],
      ["ratio", "number"],
      ["dry_run", "boolean"],
      ["tags", "json"],
    ]);
    expect(fields[0]?.required).toBe(true);
    expect(fields[1]?.options).toEqual(["low", "normal", "high"]);
    expect(fields[2]?.placeholder).toBe("10");
  });

  it("returns no fields for a tool without arguments", () => {
    expect(fieldsOf({ type: "object" })).toEqual([]);
  });
});

describe("argumentsFrom", () => {
  const fields = fieldsOf(SCHEMA);

  it("builds typed arguments and leaves empty optional fields out", () => {
    const { arguments: args, errors } = argumentsFrom(fields, {
      title: " Printer jam ",
      priority: "high",
      limit: "5",
      ratio: "",
      dry_run: true,
      tags: '["a","b"]',
    });
    expect(errors).toEqual([]);
    expect(args).toEqual({ title: "Printer jam", priority: "high", limit: 5, dry_run: true, tags: ["a", "b"] });
  });

  it("names every problem instead of sending a broken call", () => {
    const { errors } = argumentsFrom(fields, { title: "", limit: "2.5", ratio: "x", tags: "[oops" });
    expect(errors).toEqual([
      "title is required.",
      "limit must be a whole number.",
      "ratio must be a number.",
      "tags must be valid JSON.",
    ]);
  });
});
