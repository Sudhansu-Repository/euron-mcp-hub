import { describe, expect, it } from "vitest";

import { isNavActive, NAV_GROUPS } from "@/components/shell/nav";

describe("isNavActive", () => {
  it("keeps a section highlighted on its detail pages", () => {
    expect(isNavActive("/servers", "/servers")).toBe(true);
    expect(isNavActive("/servers/tickets", "/servers")).toBe(true);
  });

  it("does not match a different section with the same prefix", () => {
    expect(isNavActive("/serversfoo", "/servers")).toBe(false);
    expect(isNavActive("/keys", "/clients")).toBe(false);
  });
});

describe("NAV_GROUPS", () => {
  it("has one entry per page and no duplicate links", () => {
    const hrefs = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.href));
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs).toContain("/overview");
    expect(hrefs).toContain("/calls");
  });
});
