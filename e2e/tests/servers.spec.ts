import { expect, test } from "@playwright/test";

import { API_URL, apiGet, apiSend, signIn, unique } from "../helpers";

test("the catalog lists the demo servers with their health and tool counts", async ({ page }) => {
  await signIn(page, "operator");
  await page.goto("/servers");
  const table = page.getByRole("region", { name: "Servers" });
  for (const name of ["Team notes", "Toolbox", "Help desk", "Weather", "Warehouse analytics"]) {
    await expect(table.getByRole("link", { name })).toBeVisible();
  }
  await expect(table.getByText("Healthy").first()).toBeVisible();
  await page.getByLabel("Filter by health").selectOption("down");
  await expect(table.getByRole("link", { name: "Warehouse analytics" })).toBeVisible();
  await expect(table.getByRole("link", { name: "Toolbox" })).toHaveCount(0);
});

test("a server page shows its tools, versions and health", async ({ page }) => {
  await signIn(page, "operator");
  await page.goto("/servers/tickets");
  await expect(page.getByRole("heading", { level: 1, name: /Help desk/ })).toBeVisible();
  const tools = page.getByRole("region", { name: "Tools" });
  await expect(tools.getByRole("button", { name: "tickets.create_ticket" })).toBeVisible();
  await tools.getByRole("button", { name: "tickets.create_ticket" }).click();
  await expect(page.getByRole("dialog").getByText("Input schema")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("tab", { name: "Versions" }).click();
  await expect(page.getByText("add_comment").first()).toBeVisible();
  await page.getByRole("tab", { name: "Health" }).click();
  await expect(page.getByText("Uptime, last 24 hours")).toBeVisible();
});

test("connecting a server discovers its tools, and removing it takes them away", async ({ page }) => {
  await signIn(page, "operator");
  const slug = unique("scratch").slice(0, 20);
  await page.goto("/servers");
  await page.getByRole("button", { name: "Connect a server" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Name\b/).fill("Scratch toolbox");
  await dialog.getByLabel(/^Namespace\b/).fill(slug);
  await dialog.getByLabel("Server URL").fill("http://demo-servers:9151/mcp");
  await dialog.getByRole("button", { name: "Continue" }).click();

  await dialog.getByRole("button", { name: "Skip, no credentials" }).click();
  await expect(dialog.getByText(/Found \d+ tools/)).toBeVisible();
  await dialog.getByRole("link", { name: "Open the server" }).click();
  await expect(page).toHaveURL(new RegExp(`/servers/${slug}`));
  await expect(
    page.getByRole("region", { name: "Tools" }).getByRole("button", { name: `${slug}.calculate` }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Remove this server" }).click();
  await page.getByLabel(/Type .* to confirm/).fill(slug);
  await page.getByRole("button", { name: "Remove server" }).click();
  await expect(page).toHaveURL(/\/servers$/);
  await expect(page.getByRole("link", { name: "Scratch toolbox" })).toHaveCount(0);
});

test("the egress policy refuses the cloud metadata address and private networks", async ({ page }) => {
  await signIn(page, "operator");
  await page.goto("/servers");
  await page.getByRole("button", { name: "Connect a server" }).click();
  const dialog = page.getByRole("dialog", { name: "Connect an MCP server" });
  await dialog.getByLabel(/^Name\b/).fill("Metadata probe");
  await dialog.getByLabel("Server URL").fill("http://169.254.169.254/latest/meta-data");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByRole("alert").filter({ hasText: "metadata" })).toBeVisible();

  await dialog.getByLabel("Server URL").fill("http://10.0.0.8:9000/mcp");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByRole("alert").filter({ hasText: "private or local network" })).toBeVisible();
});

test("secrets are write-only: the name is listed, the value never comes back", async ({ page }) => {
  await signIn(page, "operator");
  const slug = unique("vault").slice(0, 20);
  await apiSend(page, "POST", "/servers", {
    name: "Vault test",
    slug,
    url: "http://demo-servers:9151/mcp",
    discover: false,
  });
  const secret = `Bearer value-that-must-stay-hidden-${Date.now()}`;
  await page.goto(`/servers/${slug}?tab=secrets`);
  await page.getByLabel("Header name").fill("X-Team-Token");
  await page.getByLabel("Value").fill(secret);
  await page.getByRole("button", { name: "Encrypt and save" }).click();
  const list = page.getByRole("region", { name: "Secrets" });
  await expect(list.getByText("X-Team-Token")).toBeVisible();
  await expect(page.getByText(secret)).toHaveCount(0);

  const response = await page.request.get(`${API_URL}/api/v1/servers/${slug}/secrets`);
  expect(await response.text()).not.toContain("value-that-must-stay-hidden");
  expect((await apiGet<{ name: string }[]>(page, `/servers/${slug}/secrets`)).map((s) => s.name)).toEqual([
    "X-Team-Token",
  ]);
  await apiSend(page, "DELETE", `/servers/${slug}`);
});
