import { expect, test } from "@playwright/test";

import { apiSend, gateway, signIn, unique } from "../helpers";

test("a new client starts with no tools, gets permissions in the matrix, and the gateway follows", async ({
  page,
  request,
}) => {
  await signIn(page, "operator");
  const name = unique("E2E agent");
  await page.goto("/clients");
  await page.getByRole("button", { name: "New client" }).click();
  const dialog = page.getByRole("dialog", { name: "New client" });
  await dialog.getByLabel(/^Name\b/).fill(name);
  await dialog.getByRole("button", { name: "Create client and key" }).click();

  // The key is shown once, with snippets that use exactly this key.
  await expect(page.getByRole("dialog", { name: new RegExp(`${name} is ready`) })).toBeVisible();
  const key = (await page.getByLabel("API key").textContent())?.trim() ?? "";
  expect(key).toMatch(/^mch_[a-z2-7]{10}_/);
  await expect(page.getByLabel("Command line (claude mcp) snippet")).toContainText(key);
  await page.getByRole("link", { name: "Set permissions" }).click();

  // Deny by default: the gateway lists nothing for a client with no rules.
  const empty = await gateway(request, key, "tools/list");
  expect(empty.status).toBe(200);
  expect(empty.body.result?.tools).toEqual([]);

  // Allow one tool from the matrix.
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(name) })).toBeVisible();
  const row = page.getByRole("listitem").filter({ hasText: "toolbox.calculate" }).first();
  await row.getByRole("radio", { name: "Allow" }).click();
  await expect(row.getByText("Allowed", { exact: true })).toBeVisible();

  const listed = await gateway(request, key, "tools/list");
  expect((listed.body.result?.tools as { name: string }[]).map((t) => t.name)).toEqual(["toolbox.calculate"]);
  const called = await gateway(request, key, "tools/call", {
    name: "toolbox.calculate",
    arguments: { expression: "6 * 7" },
  });
  expect(JSON.stringify(called.body.result)).toContain("42");

  // The dry run explains a refusal without calling anything.
  await page.getByRole("tab", { name: "Dry run" }).click();
  await expect(page.getByRole("button", { name: "Check the call" })).toBeVisible();
  await page.locator("#sim-tool").selectOption("tickets.delete_ticket");
  await page.getByRole("button", { name: "Check the call" }).click();
  await expect(page.getByRole("status").filter({ hasText: "would be refused" })).toBeVisible();

  // Suspending a client stops its key at once.
  await page.getByRole("button", { name: "Suspend" }).click();
  await expect(page.getByText("Suspended").first()).toBeVisible();
  expect((await gateway(request, key, "tools/list")).status).toBe(403);

  await page.getByRole("button", { name: "Delete this client" }).click();
  await page.getByLabel(/Type .* to confirm/).fill((await page.url()).split("/").pop()!.split("?")[0]!);
  await page.getByRole("button", { name: "Delete client" }).click();
  await expect(page).toHaveURL(/\/clients$/);
});

test("a revoked key stops working", async ({ page, request }) => {
  await signIn(page, "operator");
  const slug = unique("revoke").slice(0, 24);
  const created = await apiSend<{ key: { key: string } }>(page, "POST", "/clients", { name: "Revoke test", slug });
  await apiSend(page, "POST", `/clients/${slug}/rules`, { pattern: "toolbox.*", effect: "allow" });
  expect((await gateway(request, created.key.key, "tools/list")).status).toBe(200);

  await page.goto(`/clients/${slug}?tab=keys`);
  await page.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("button", { name: "Revoke key" }).click();
  await expect(page.getByText("Revoked").first()).toBeVisible();
  expect((await gateway(request, created.key.key, "tools/list")).status).toBe(401);
  await apiSend(page, "DELETE", `/clients/${slug}`);
});

test("rules can carry argument constraints that the gateway enforces", async ({ page, request }) => {
  await signIn(page, "operator");
  const slug = unique("limits").slice(0, 24);
  const created = await apiSend<{ key: { key: string } }>(page, "POST", "/clients", { name: "Limits test", slug });
  await page.goto(`/clients/${slug}?tab=rules`);
  await page.getByRole("button", { name: "Add a rule" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a rule" });
  await dialog.getByLabel("Tools").fill("tickets.create_ticket");
  await dialog.getByRole("button", { name: "Add a constraint" }).click();
  await dialog.getByLabel("Argument").fill("priority");
  await dialog.getByLabel("Value").fill("low, normal");
  await dialog.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByText("priority is one of low, normal")).toBeVisible();

  const refused = await gateway(request, created.key.key, "tools/call", {
    name: "tickets.create_ticket",
    arguments: { title: "Fire in the server room", priority: "high" },
  });
  expect(JSON.stringify(refused.body.result)).toContain("does not allow these arguments");
  await apiSend(page, "DELETE", `/clients/${slug}`);
});
