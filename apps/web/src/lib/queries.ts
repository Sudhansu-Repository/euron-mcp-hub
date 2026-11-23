"use client";

/**
 * Data access for the whole dashboard: one TanStack Query hook per API endpoint.
 *
 * CONVENTIONS
 *
 * Layout. Pages live in `app/(app)/<route>/page.tsx` and stay thin; feature UI goes in
 * `components/<area>/`. Shared building blocks are `components/ui/*` (primitives) and
 * `components/domain/*` (status badges, JSON and schema views). Design tokens are CSS
 * variables in `app/globals.css`; use the Tailwind names (`bg-card`, `text-muted-foreground`),
 * never raw colours.
 *
 * Roles. `useCan("operator")` hides the controls a viewer may not use. The API enforces the
 * same rules; the UI only avoids offering what would be refused.
 *
 * Keys. `qk` builds every query key; the resource name is always the first element, so
 * `invalidateQueries({ queryKey: ["servers"] })` refreshes every server list and detail.
 *
 * Writes. A mutation hook returns the `useMutation` result: call `mutateAsync` in a handler.
 * Success toasts belong to the call site. Failures are toasted for you by the QueryClient's
 * mutation cache (see `lib/providers.tsx`); pass `{ silent: true }` when the form renders
 * `mutation.error` inline.
 */

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, toQuery, V1 } from "@/lib/api";
import type {
  Access,
  Activity,
  ApiKey,
  ApiKeyCreated,
  ApiKeyListed,
  Call,
  CallDetail,
  Client,
  ClientCreated,
  ClientInput,
  ClientUpdate,
  Constraint,
  CursorPage,
  Discovery,
  HealthCheck,
  HealthHistory,
  Overview,
  Page,
  PlaygroundResult,
  Prompt,
  Resource,
  Role,
  Rule,
  RuleInput,
  Secret,
  SecretKind,
  Server,
  ServerInput,
  ServerUpdate,
  SessionOut,
  Simulation,
  StatsRange,
  SystemInfo,
  Tool,
  User,
  UserCreated,
  Version,
} from "@/lib/types";

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: { silent?: boolean };
  }
}

/** Pass `{ silent: true }` when the form shows the error itself. */
export type HookOptions = { silent?: boolean };

const meta = (options?: HookOptions) => ({ silent: options?.silent ?? false });

export type PageParams = { limit?: number; offset?: number };
export type ServerParams = PageParams & { q?: string; health?: string; tag?: string; transport?: string };
export type ToolParams = PageParams & { q?: string; server?: string };
export type ClientParams = PageParams & { q?: string; status?: string };
export type KeyParams = PageParams & { q?: string; state?: string };
export type CallParams = {
  client?: string;
  server?: string;
  tool?: string;
  status?: readonly string[];
  source?: string;
  q?: string;
  since?: string;
  until?: string;
  cursor?: string;
  limit?: number;
};

export const qk = {
  system: ["system"] as const,
  me: ["me"] as const,
  users: ["users"] as const,
  overview: (range: StatsRange) => ["overview", range] as const,
  servers: (params: ServerParams = {}) => ["servers", "list", params] as const,
  server: (slug: string) => ["servers", "one", slug] as const,
  serverTools: (slug: string) => ["servers", "tools", slug] as const,
  serverResources: (slug: string) => ["servers", "resources", slug] as const,
  serverPrompts: (slug: string) => ["servers", "prompts", slug] as const,
  serverVersions: (slug: string) => ["servers", "versions", slug] as const,
  serverHealth: (slug: string, hours: number) => ["servers", "health", slug, hours] as const,
  secrets: (slug: string) => ["servers", "secrets", slug] as const,
  tools: (params: ToolParams = {}) => ["tools", params] as const,
  clients: (params: ClientParams = {}) => ["clients", "list", params] as const,
  client: (slug: string) => ["clients", "one", slug] as const,
  clientKeys: (slug: string) => ["clients", "keys", slug] as const,
  clientRules: (slug: string) => ["clients", "rules", slug] as const,
  clientAccess: (slug: string) => ["clients", "access", slug] as const,
  keys: (params: KeyParams = {}) => ["keys", params] as const,
  calls: (params: CallParams = {}) => ["calls", "list", params] as const,
  call: (id: string) => ["calls", "one", id] as const,
  activity: (params: PageParams & { target_type?: string } = {}) => ["activity", params] as const,
};

// Session and account

export const useSystemInfo = () =>
  useQuery({
    queryKey: qk.system,
    queryFn: () => api<SystemInfo>(`${V1}/system/info`),
    staleTime: 60_000,
    retry: false,
  });

export const useMe = (enabled = true) =>
  useQuery({ queryKey: qk.me, queryFn: () => api<User>(`${V1}/auth/me`), enabled, retry: false, staleTime: 60_000 });

/** Whether the signed-in person has at least this role (admin > operator > viewer). */
export function useCan(minimum: Role): boolean {
  const me = useMe();
  const rank: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 };
  return me.data ? rank[me.data.role] >= rank[minimum] : false;
}

export function useLogin(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { email: string; password: string }) =>
      api<SessionOut>(`${V1}/auth/login`, { method: "POST", json: body }),
    onSuccess: async () => {
      client.clear();
    },
  });
}

export function useSetup(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { name: string; email: string; password: string }) =>
      api<SessionOut>(`${V1}/auth/setup`, { method: "POST", json: body }),
    onSuccess: async () => {
      client.clear();
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: () => api<void>(`${V1}/auth/logout`, { method: "POST" }),
    onSettled: () => client.clear(),
  });
}

export function useChangePassword(options?: HookOptions) {
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<SessionOut>(`${V1}/auth/password`, { method: "POST", json: body }),
  });
}

export function useUpdateProfile(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (name: string) => api<User>(`${V1}/auth/me`, { method: "PATCH", json: { name } }),
    onSuccess: (user) => client.setQueryData(qk.me, user),
  });
}

export const useUsers = (enabled = true) =>
  useQuery({ queryKey: qk.users, queryFn: () => api<Page<User>>(`${V1}/users?limit=200`), enabled });

export function useCreateUser(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { email: string; name: string; role: Role }) =>
      api<UserCreated>(`${V1}/users`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.users }),
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; role?: Role; is_active?: boolean }) =>
      api<User>(`${V1}/users/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.users }),
  });
}

// Overview

export const useOverview = (range: StatsRange) =>
  useQuery({
    queryKey: qk.overview(range),
    queryFn: () => api<Overview>(`${V1}/stats/overview${toQuery({ range })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

// Servers

export const useServers = (params: ServerParams = {}) =>
  useQuery({
    queryKey: qk.servers(params),
    queryFn: () => api<Page<Server>>(`${V1}/servers${toQuery({ limit: 100, ...params })}`),
    placeholderData: keepPreviousData,
  });

export const useServer = (slug: string) =>
  useQuery({ queryKey: qk.server(slug), queryFn: () => api<Server>(`${V1}/servers/${encodeURIComponent(slug)}`) });

const serverUrl = (slug: string) => `${V1}/servers/${encodeURIComponent(slug)}`;

export const useServerTools = (slug: string) =>
  useQuery({ queryKey: qk.serverTools(slug), queryFn: () => api<Tool[]>(`${serverUrl(slug)}/tools`) });

export const useServerResources = (slug: string) =>
  useQuery({ queryKey: qk.serverResources(slug), queryFn: () => api<Resource[]>(`${serverUrl(slug)}/resources`) });

export const useServerPrompts = (slug: string) =>
  useQuery({ queryKey: qk.serverPrompts(slug), queryFn: () => api<Prompt[]>(`${serverUrl(slug)}/prompts`) });

export const useServerVersions = (slug: string) =>
  useQuery({
    queryKey: qk.serverVersions(slug),
    queryFn: () => api<Page<Version>>(`${serverUrl(slug)}/versions?limit=20`),
  });

export const useServerHealth = (slug: string, hours = 24) =>
  useQuery({
    queryKey: qk.serverHealth(slug, hours),
    queryFn: () => api<HealthHistory>(`${serverUrl(slug)}/health?hours=${hours}`),
    refetchInterval: 30_000,
  });

function refreshServer(client: QueryClient, slug: string) {
  return Promise.all([
    client.invalidateQueries({ queryKey: ["servers"] }),
    client.invalidateQueries({ queryKey: ["tools"] }),
    client.invalidateQueries({ queryKey: ["clients", "access"] }),
    client.invalidateQueries({ queryKey: qk.serverTools(slug) }),
  ]);
}

export function useCreateServer(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: ServerInput) => api<Server>(`${V1}/servers`, { method: "POST", json: body }),
    onSuccess: (server) => refreshServer(client, server.slug),
  });
}

export function useUpdateServer(slug: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: ServerUpdate) => api<Server>(serverUrl(slug), { method: "PATCH", json: body }),
    onSuccess: () => refreshServer(client, slug),
  });
}

export function useDeleteServer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api<void>(serverUrl(slug), { method: "DELETE" }),
    onSuccess: (_data, slug) => refreshServer(client, slug),
  });
}

export function useRefreshServer(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<Discovery>(`${serverUrl(slug)}/refresh`, { method: "POST" }),
    onSuccess: () => refreshServer(client, slug),
  });
}

export function useCheckServer(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<HealthCheck>(`${serverUrl(slug)}/check`, { method: "POST" }),
    onSuccess: () =>
      Promise.all([refreshServer(client, slug), client.invalidateQueries({ queryKey: ["servers", "health"] })]),
  });
}

export function useSetToolEnabled(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api<Tool>(`${serverUrl(slug)}/tools/${name.split("/").map(encodeURIComponent).join("/")}`, {
        method: "PATCH",
        json: { enabled },
      }),
    onSuccess: () => refreshServer(client, slug),
  });
}

export const useSecrets = (slug: string, enabled = true) =>
  useQuery({ queryKey: qk.secrets(slug), queryFn: () => api<Secret[]>(`${serverUrl(slug)}/secrets`), enabled });

export function useSetSecret(slug: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { kind: SecretKind; name: string; value: string }) =>
      api<Secret>(`${serverUrl(slug)}/secrets`, { method: "PUT", json: body }),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: qk.secrets(slug) }),
        client.invalidateQueries({ queryKey: ["servers"] }),
      ]),
  });
}

export function useDeleteSecret(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`${serverUrl(slug)}/secrets/${id}`, { method: "DELETE" }),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: qk.secrets(slug) }),
        client.invalidateQueries({ queryKey: ["servers"] }),
      ]),
  });
}

// Tools

export const useTools = (params: ToolParams = {}) =>
  useQuery({
    queryKey: qk.tools(params),
    queryFn: () => api<Page<Tool>>(`${V1}/tools${toQuery({ limit: 100, ...params })}`),
    placeholderData: keepPreviousData,
  });

// Clients

export const useClients = (params: ClientParams = {}) =>
  useQuery({
    queryKey: qk.clients(params),
    queryFn: () => api<Page<Client>>(`${V1}/clients${toQuery({ limit: 100, ...params })}`),
    placeholderData: keepPreviousData,
  });

const clientUrl = (slug: string) => `${V1}/clients/${encodeURIComponent(slug)}`;

export const useClient = (slug: string) =>
  useQuery({ queryKey: qk.client(slug), queryFn: () => api<Client>(clientUrl(slug)) });

export const useClientKeys = (slug: string) =>
  useQuery({ queryKey: qk.clientKeys(slug), queryFn: () => api<ApiKey[]>(`${clientUrl(slug)}/keys`) });

export const useClientRules = (slug: string) =>
  useQuery({ queryKey: qk.clientRules(slug), queryFn: () => api<Rule[]>(`${clientUrl(slug)}/rules`) });

export const useClientAccess = (slug: string) =>
  useQuery({ queryKey: qk.clientAccess(slug), queryFn: () => api<Access[]>(`${clientUrl(slug)}/tools`) });

function refreshClient(client: QueryClient, slug: string) {
  return Promise.all([
    client.invalidateQueries({ queryKey: ["clients"] }),
    client.invalidateQueries({ queryKey: ["keys"] }),
    client.invalidateQueries({ queryKey: qk.clientAccess(slug) }),
  ]);
}

export function useCreateClient(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: ClientInput) => api<ClientCreated>(`${V1}/clients`, { method: "POST", json: body }),
    onSuccess: (created) => refreshClient(client, created.client.slug),
  });
}

export function useUpdateClient(slug: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: ClientUpdate) => api<Client>(clientUrl(slug), { method: "PATCH", json: body }),
    onSuccess: () => refreshClient(client, slug),
  });
}

export function useDeleteClient() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api<void>(clientUrl(slug), { method: "DELETE" }),
    onSuccess: (_data, slug) => refreshClient(client, slug),
  });
}

export function useCreateKey(slug: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { name: string; expires_in_days?: number | null }) =>
      api<ApiKeyCreated>(`${clientUrl(slug)}/keys`, { method: "POST", json: body }),
    onSuccess: () => refreshClient(client, slug),
  });
}

export function useRevokeKey(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`${clientUrl(slug)}/keys/${id}`, { method: "DELETE" }),
    onSuccess: () => refreshClient(client, slug),
  });
}

export function useCreateRule(slug: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: RuleInput) => api<Rule>(`${clientUrl(slug)}/rules`, { method: "POST", json: body }),
    onSuccess: () =>
      Promise.all([refreshClient(client, slug), client.invalidateQueries({ queryKey: qk.clientRules(slug) })]),
  });
}

export function useUpdateRule(slug: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: ({ id, ...body }: Partial<RuleInput> & { id: string }) =>
      api<Rule>(`${clientUrl(slug)}/rules/${id}`, { method: "PATCH", json: body }),
    onSuccess: () =>
      Promise.all([refreshClient(client, slug), client.invalidateQueries({ queryKey: qk.clientRules(slug) })]),
  });
}

export function useDeleteRule(slug: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`${clientUrl(slug)}/rules/${id}`, { method: "DELETE" }),
    onSuccess: () =>
      Promise.all([refreshClient(client, slug), client.invalidateQueries({ queryKey: qk.clientRules(slug) })]),
  });
}

export function useSimulate(slug: string) {
  return useMutation({
    meta: { silent: true },
    mutationFn: (body: { tool: string; arguments: Record<string, unknown> }) =>
      api<Simulation>(`${clientUrl(slug)}/simulate`, { method: "POST", json: body }),
  });
}

export type { Constraint };

// Keys across clients

export const useAllKeys = (params: KeyParams = {}) =>
  useQuery({
    queryKey: qk.keys(params),
    queryFn: () => api<Page<ApiKeyListed>>(`${V1}/keys${toQuery({ limit: 100, ...params })}`),
    placeholderData: keepPreviousData,
  });

// Call log

export const useCalls = (params: CallParams = {}) =>
  useQuery({
    queryKey: qk.calls(params),
    queryFn: () => api<CursorPage<Call>>(`${V1}/calls${toQuery({ limit: 50, count: true, ...params })}`),
    placeholderData: keepPreviousData,
  });

export const useCall = (id: string | null) =>
  useQuery({
    queryKey: qk.call(id ?? ""),
    queryFn: () => api<CallDetail>(`${V1}/calls/${id}`),
    enabled: Boolean(id),
  });

export function callsExportUrl(params: CallParams): string {
  return `${V1}/calls/export${toQuery({ ...params, cursor: undefined, limit: undefined })}`;
}

export function usePlaygroundCall() {
  const client = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: (body: { client: string; tool: string; arguments: Record<string, unknown> }) =>
      api<PlaygroundResult>(`${V1}/playground/call`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["calls"] }),
  });
}

export const useActivity = (params: PageParams & { target_type?: string } = {}) =>
  useQuery({
    queryKey: qk.activity(params),
    queryFn: () => api<Page<Activity>>(`${V1}/activity${toQuery({ limit: 25, ...params })}`),
    placeholderData: keepPreviousData,
  });
