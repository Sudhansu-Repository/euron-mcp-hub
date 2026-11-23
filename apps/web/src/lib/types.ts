/** API response shapes, mirroring the server's schemas (apps/api/src/mcphub/schemas). */

export type Role = "admin" | "operator" | "viewer";
export type Health = "unknown" | "healthy" | "degraded" | "down";
export type Transport = "streamable_http" | "stdio";
export type Effect = "allow" | "deny";
export type ClientStatus = "active" | "suspended";
export type SecretKind = "header" | "env";
export type CallStatus =
  "ok" | "tool_error" | "denied" | "blocked" | "invalid_arguments" | "rate_limited" | "upstream_error" | "timeout";
export type StatsRange = "24h" | "7d" | "30d";

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type CursorPage<T> = { items: T[]; next_cursor: string | null; total?: number | null };

export type User = {
  id: string;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type SessionOut = { user: User; token: string; expires_at: string };
export type UserCreated = { user: User; temporary_password: string };

export type SystemInfo = {
  product_name: string;
  version: string;
  mcp_sdk_version: string;
  gateway_url: string;
  protocol_versions: string[];
  secrets_backend: string;
  stdio_commands: string[];
  audit_retention_days: number;
  health_interval_s: number;
  needs_setup: boolean;
};

export type Server = {
  id: string;
  slug: string;
  name: string;
  description: string;
  transport: Transport;
  url: string | null;
  command: string | null;
  args: string[];
  env: Record<string, unknown>;
  headers: Record<string, unknown>;
  tags: string[];
  owner: string;
  homepage_url: string | null;
  enabled: boolean;
  timeout_s: number;
  refresh_interval_s: number;
  config_version: number;
  health: Health;
  consecutive_failures: number;
  last_check_at: string | null;
  last_healthy_at: string | null;
  last_latency_ms: number | null;
  last_error: string | null;
  server_name: string | null;
  server_version: string | null;
  protocol_version: string | null;
  instructions: string | null;
  capabilities: Record<string, unknown>;
  last_discovered_at: string | null;
  discovery_error: string | null;
  tool_count: number;
  resource_count: number;
  prompt_count: number;
  created_at: string;
  updated_at: string;
  secret_count: number;
  uptime_24h: number | null;
  calls_24h: number;
  failed_24h: number;
};

export type ServerInput = {
  name: string;
  slug?: string;
  description?: string;
  transport: Transport;
  url?: string;
  command?: string;
  args?: string[];
  tags?: string[];
  owner?: string;
  timeout_s?: number;
  refresh_interval_s?: number;
  discover?: boolean;
};

export type ServerUpdate = Partial<Omit<ServerInput, "discover" | "slug">> & { enabled?: boolean };

export type Discovery = {
  ok: boolean;
  error: string | null;
  latency_ms: number | null;
  new_version: boolean;
  added: string[];
  removed: string[];
  changed: string[];
  server: Server;
};

export type HealthCheck = {
  ok: boolean;
  health: Health;
  latency_ms: number | null;
  error: string | null;
  server: Server;
};

export type Tool = {
  id: string;
  server_slug: string;
  name: string;
  qualified_name: string;
  title: string | null;
  description: string;
  input_schema: JsonSchema;
  output_schema: JsonSchema | null;
  annotations: Record<string, unknown>;
  enabled: boolean;
  fingerprint: string;
  first_seen_at: string;
  last_seen_at: string;
  changed_at: string | null;
  removed_at: string | null;
};

export type JsonSchema = {
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  description?: string;
  title?: string;
  enum?: unknown[];
  default?: unknown;
  items?: JsonSchema;
  minimum?: number;
  maximum?: number;
  anyOf?: JsonSchema[];
  [key: string]: unknown;
};

export type Resource = {
  id: string;
  uri: string;
  name: string;
  title: string | null;
  description: string;
  mime_type: string | null;
  is_template: boolean;
  first_seen_at: string;
};

export type Prompt = {
  id: string;
  name: string;
  title: string | null;
  description: string;
  arguments: { name: string; description?: string | null; required: boolean }[];
  first_seen_at: string;
};

export type Version = {
  id: string;
  server_version: string | null;
  protocol_version: string | null;
  catalog_hash: string;
  tool_count: number;
  resource_count: number;
  prompt_count: number;
  tools_added: string[];
  tools_removed: string[];
  tools_changed: string[];
  created_at: string;
};

export type HealthHistory = {
  hours: number;
  bucket_minutes: number;
  uptime: number | null;
  buckets: { start: string; checks: number; ok: number; avg_latency_ms: number | null }[];
};

export type Secret = {
  id: string;
  kind: SecretKind;
  name: string;
  backend: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type Client = {
  id: string;
  slug: string;
  name: string;
  description: string;
  status: ClientStatus;
  default_effect: Effect;
  tool_separator: "." | "__";
  rate_limit_per_minute: number | null;
  record_arguments: boolean;
  policy_version: number;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
  active_keys: number;
  rules: number;
  calls_24h: number;
};

export type ClientInput = {
  name: string;
  slug?: string;
  description?: string;
  default_effect?: Effect;
  tool_separator?: "." | "__";
  rate_limit_per_minute?: number | null;
  record_arguments?: boolean;
  key_name?: string;
  key_expires_in_days?: number | null;
};

export type ClientUpdate = Partial<
  Pick<
    Client,
    | "name"
    | "description"
    | "status"
    | "default_effect"
    | "tool_separator"
    | "rate_limit_per_minute"
    | "record_arguments"
  >
>;

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type ApiKeyListed = ApiKey & { client_slug: string; client_name: string; client_status: ClientStatus };
export type ApiKeyCreated = ApiKey & { key: string };
export type ClientCreated = { client: Client; key: ApiKeyCreated; gateway_url: string };

export type Constraint =
  | { argument: string; rule: "equals"; value: unknown }
  | { argument: string; rule: "one_of"; values: unknown[] }
  | { argument: string; rule: "pattern"; value: string }
  | { argument: string; rule: "max_length"; value: number }
  | { argument: string; rule: "range"; min?: number | null; max?: number | null }
  | { argument: string; rule: "forbidden" };

export type Rule = {
  id: string;
  pattern: string;
  effect: Effect;
  constraints: Constraint[];
  rate_limit_per_minute: number | null;
  redact: string[];
  description: string;
  created_at: string;
  updated_at: string;
};

export type RuleInput = {
  pattern: string;
  effect: Effect;
  constraints?: Constraint[];
  rate_limit_per_minute?: number | null;
  redact?: string[];
  description?: string;
};

export type Access = {
  server_slug: string;
  server_name: string;
  tool: string;
  qualified_name: string;
  exposed_name: string;
  title: string | null;
  description: string;
  allowed: boolean;
  reason: string;
  rule_id: string | null;
  rule_pattern: string | null;
  read_only: boolean | null;
  destructive: boolean | null;
};

export type Simulation = {
  tool: string;
  exposed_name: string;
  found: boolean;
  allowed: boolean;
  reason: string;
  rule_id: string | null;
  rule_pattern: string | null;
  schema_errors: string[];
  violations: { argument: string; rule: string; message: string }[];
  would_call: boolean;
};

export type Call = {
  id: string;
  created_at: string;
  client_id: string | null;
  client_name: string;
  server_id: string | null;
  server_slug: string;
  tool_name: string;
  qualified_name: string;
  source: "gateway" | "playground";
  status: CallStatus;
  error_message: string | null;
  latency_ms: number;
  upstream_ms: number | null;
};

export type CallDetail = Call & {
  client_key_id: string | null;
  rule_id: string | null;
  arguments: Record<string, unknown> | null;
  result_bytes: number | null;
  request_id: string | null;
  protocol_version: string | null;
  user_agent: string | null;
  actor_name: string | null;
};

export type PlaygroundResult = {
  call: Call;
  is_error: boolean;
  error: string | null;
  content: { type: string; text?: string; [key: string]: unknown }[];
  structured_content: unknown;
};

export type OverviewTotals = {
  calls: number;
  ok: number;
  failed: number;
  refused: number;
  success_rate: number | null;
  p50_ms: number;
  p95_ms: number;
  clients_seen: number;
  tools_used: number;
  active_clients: number;
  exposed_tools: number;
};

export type TopItem = { key: string; label: string; calls: number; failed: number; refused: number; p95_ms: number };

export type Overview = {
  range: StatsRange;
  generated_at: string;
  bucket_seconds: number;
  totals: OverviewTotals;
  servers: { total: number; enabled: number; unknown: number; healthy: number; degraded: number; down: number };
  series: ({ start: string } & Record<CallStatus, number>)[];
  latency: { start: string; p50_ms: number | null; p95_ms: number | null }[];
  statuses: Record<string, number>;
  top_tools: TopItem[];
  top_clients: TopItem[];
};

export type Activity = {
  id: string;
  actor_name: string;
  action: string;
  target_type: string;
  target_id: string | null;
  target_name: string | null;
  details: Record<string, unknown>;
  created_at: string;
};
