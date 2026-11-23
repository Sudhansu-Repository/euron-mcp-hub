import type { CallStatus, Health, Role, Transport } from "@/lib/types";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "primary";

export const HEALTH: Record<Health, { label: string; tone: Tone }> = {
  healthy: { label: "Healthy", tone: "success" },
  degraded: { label: "Degraded", tone: "warning" },
  down: { label: "Down", tone: "danger" },
  unknown: { label: "Not checked", tone: "neutral" },
};

export const CALL_STATUS: Record<CallStatus, { label: string; tone: Tone; hint: string }> = {
  ok: { label: "OK", tone: "success", hint: "The tool ran and answered." },
  tool_error: { label: "Tool error", tone: "danger", hint: "The server ran the tool and it reported an error." },
  denied: { label: "Denied", tone: "warning", hint: "The client may not use this tool, or it does not exist." },
  blocked: { label: "Blocked", tone: "warning", hint: "An argument broke a constraint of the client's policy." },
  invalid_arguments: {
    label: "Invalid arguments",
    tone: "warning",
    hint: "The arguments did not match the input schema.",
  },
  rate_limited: { label: "Rate limited", tone: "info", hint: "The client or the rule exceeded its calls per minute." },
  upstream_error: { label: "Upstream error", tone: "danger", hint: "The gateway could not reach the server." },
  timeout: { label: "Timed out", tone: "danger", hint: "The server did not answer within its timeout." },
};

export const CALL_STATUSES = Object.keys(CALL_STATUS) as CallStatus[];

/** Refusals by policy, as opposed to failures of the server. */
export const REFUSED_STATUSES: ReadonlySet<CallStatus> = new Set([
  "denied",
  "blocked",
  "invalid_arguments",
  "rate_limited",
]);

export const TRANSPORT: Record<Transport, string> = {
  streamable_http: "Streamable HTTP",
  stdio: "stdio",
};

export const ROLE: Record<Role, { label: string; description: string }> = {
  admin: { label: "Admin", description: "Everything, including accounts." },
  operator: { label: "Operator", description: "Servers, secrets, clients and policy." },
  viewer: { label: "Viewer", description: "Read-only, including the call log." },
};

export const ACTIVITY_LABEL: Record<string, string> = {
  "server.registered": "registered the server",
  "server.updated": "changed the server",
  "server.deleted": "removed the server",
  "server.catalog_changed": "saw the catalog change on",
  "server.health_changed": "saw a health change on",
  "secret.set": "set a secret on",
  "secret.deleted": "deleted a secret on",
  "tool.enabled": "enabled a tool on",
  "tool.disabled": "disabled a tool on",
  "client.created": "created the client",
  "client.updated": "changed the client",
  "client.suspended": "suspended the client",
  "client.resumed": "resumed the client",
  "client.deleted": "deleted the client",
  "key.created": "created a key for",
  "key.revoked": "revoked a key of",
  "rule.created": "added a rule to",
  "rule.updated": "changed a rule of",
  "rule.deleted": "removed a rule from",
  "user.created": "created an account",
  "user.updated": "changed an account",
  "user.setup": "set up this deployment",
  "user.password_changed": "changed their password",
};
