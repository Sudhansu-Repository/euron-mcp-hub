import { describe, expect, it } from "vitest";

import { constraintOf, describeConstraint, draftOf, emptyDraft, parseValue } from "@/lib/constraints";

describe("describeConstraint", () => {
  it("reads like a sentence", () => {
    expect(describeConstraint({ argument: "priority", rule: "one_of", values: ["low", "normal"] })).toBe(
      "priority is one of low, normal",
    );
    expect(describeConstraint({ argument: "limit", rule: "range", min: 1, max: 50 })).toBe("limit is between 1 and 50");
    expect(describeConstraint({ argument: "limit", rule: "range", min: null, max: 50 })).toBe("limit is at most 50");
    expect(describeConstraint({ argument: "admin", rule: "forbidden" })).toBe("admin must be absent");
  });
});

describe("parseValue", () => {
  it("keeps numbers and booleans typed", () => {
    expect(parseValue("42")).toBe(42);
    expect(parseValue("true")).toBe(true);
    expect(parseValue(" low ")).toBe("low");
    expect(parseValue("")).toBe("");
  });
});

describe("constraintOf", () => {
  it("builds each kind of constraint from a draft", () => {
    const base = emptyDraft();
    expect(constraintOf({ ...base, argument: "priority", rule: "one_of", text: "low, 2, normal" })).toEqual({
      argument: "priority",
      rule: "one_of",
      values: ["low", 2, "normal"],
    });
    expect(constraintOf({ ...base, argument: "q", rule: "max_length", text: "200" })).toEqual({
      argument: "q",
      rule: "max_length",
      value: 200,
    });
    expect(constraintOf({ ...base, argument: "n", rule: "range", min: "1", max: "" })).toEqual({
      argument: "n",
      rule: "range",
      min: 1,
      max: null,
    });
  });

  it("explains what is missing instead of building a broken constraint", () => {
    const base = emptyDraft();
    expect(constraintOf(base)).toMatch(/Name the argument/);
    expect(constraintOf({ ...base, argument: "p", rule: "one_of", text: " , " })).toMatch(/List the allowed values/);
    expect(constraintOf({ ...base, argument: "n", rule: "range" })).toMatch(/minimum, a maximum or both/);
    expect(constraintOf({ ...base, argument: "q", rule: "max_length", text: "-1" })).toMatch(/Enter a length/);
  });

  it("round-trips through a draft", () => {
    const constraint = { argument: "status", rule: "one_of" as const, values: ["pending", "resolved"] };
    expect(constraintOf(draftOf(constraint))).toEqual(constraint);
  });
});
