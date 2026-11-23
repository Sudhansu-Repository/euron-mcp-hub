/**
 * Connection snippets for a client key. Every snippet runs as written once the placeholder
 * key is replaced (or, right after a key is created, with the real key filled in).
 */
export type Snippet = { id: string; label: string; language: string; code: string };

export const KEY_PLACEHOLDER = "mch_YOUR_KEY";

export function snippetsFor(gatewayUrl: string, key: string = KEY_PLACEHOLDER): Snippet[] {
  return [
    {
      id: "cli",
      label: "Command line (claude mcp)",
      language: "bash",
      code: `claude mcp add --transport http mcphub ${gatewayUrl} \\\n  --header "Authorization: Bearer ${key}"`,
    },
    {
      id: "json",
      label: "Cursor and other IDEs",
      language: "json",
      code: JSON.stringify(
        { mcpServers: { mcphub: { url: gatewayUrl, headers: { Authorization: `Bearer ${key}` } } } },
        null,
        2,
      ),
    },
    {
      id: "curl",
      label: "curl",
      language: "bash",
      code: [
        `curl -s ${gatewayUrl} \\`,
        `  -H "authorization: Bearer ${key}" \\`,
        `  -H "content-type: application/json" \\`,
        `  -H "accept: application/json, text/event-stream" \\`,
        `  -H "mcp-protocol-version: 2025-11-25" \\`,
        `  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`,
      ].join("\n"),
    },
    {
      id: "python",
      label: "Python",
      language: "python",
      code: [
        "import httpx",
        "",
        `URL = "${gatewayUrl}"`,
        "HEADERS = {",
        `    "authorization": "Bearer ${key}",`,
        `    "accept": "application/json, text/event-stream",`,
        `    "mcp-protocol-version": "2025-11-25",`,
        "}",
        "",
        "",
        "def rpc(method, params=None, id=1):",
        '    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}',
        "    return httpx.post(URL, headers=HEADERS, json=body, timeout=60).json()",
        "",
        "",
        'print([tool["name"] for tool in rpc("tools/list")["result"]["tools"]])',
      ].join("\n"),
    },
    {
      id: "inspector",
      label: "MCP Inspector",
      language: "bash",
      code: `npx @modelcontextprotocol/inspector --transport http --server-url ${gatewayUrl} \\\n  --header "Authorization: Bearer ${key}"`,
    },
  ];
}
