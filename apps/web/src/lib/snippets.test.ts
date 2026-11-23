import { describe, expect, it } from "vitest";

import { KEY_PLACEHOLDER, snippetsFor } from "@/lib/snippets";

const URL = "http://localhost:8150/mcp";

describe("snippetsFor", () => {
  it("puts the gateway URL and the key in every snippet", () => {
    for (const snippet of snippetsFor(URL, "mch_abc_def")) {
      expect(snippet.code).toContain(URL);
      expect(snippet.code).toContain("mch_abc_def");
    }
  });

  it("uses a placeholder until a real key is shown", () => {
    expect(snippetsFor(URL).every((snippet) => snippet.code.includes(KEY_PLACEHOLDER))).toBe(true);
  });

  it("produces valid JSON for the IDE configuration", () => {
    const json = snippetsFor(URL, "mch_k").find((snippet) => snippet.id === "json");
    expect(JSON.parse(json?.code ?? "")).toEqual({
      mcpServers: { mcphub: { url: URL, headers: { Authorization: "Bearer mch_k" } } },
    });
  });

  it("sends the headers a streamable HTTP server needs in the curl example", () => {
    const curl = snippetsFor(URL).find((snippet) => snippet.id === "curl")?.code ?? "";
    expect(curl).toContain("accept: application/json, text/event-stream");
    expect(curl).toContain("tools/list");
  });
});
