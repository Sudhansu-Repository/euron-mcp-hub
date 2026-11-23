/**
 * README screenshots (1440x900 at 2x) and tour frames, from the seeded demo data.
 * Every image shows the real stack: nothing here is mocked. Run this right after
 * `make demo`, before the e2e suite adds its scratch servers and clients.
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { settle, signIn } from "../helpers";

const SHOTS = path.resolve(__dirname, "../../docs/assets/screenshots");
const FRAMES = path.resolve(__dirname, "../.capture/frames");
mkdirSync(SHOTS, { recursive: true });
mkdirSync(FRAMES, { recursive: true });

let frame = 0;

async function shot(page: Page, name: string): Promise<void> {
  await settle(page);
  // The clicked control keeps a keyboard focus ring: the picture is of the page.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

async function tourFrame(page: Page, holdMs = 1800): Promise<void> {
  frame += 1;
  const file = path.join(FRAMES, `${String(frame).padStart(3, "0")}-${holdMs}.png`);
  await page.screenshot({ path: file, scale: "css" });
}

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

test("sign-in page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("One front door for every MCP server.")).toBeVisible();
  await shot(page, "00-sign-in");
  await tourFrame(page, 1600);
});

test("the web app, page by page", async ({ page }) => {
  await signIn(page, "admin");

  await page.goto("/overview");
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await expect(page.getByText("Busiest tools")).toBeVisible();
  await shot(page, "01-overview");
  await tourFrame(page, 2600);

  await page.goto("/servers");
  const table = page.getByRole("region", { name: "Servers" });
  await expect(table.getByRole("link", { name: "Help desk" })).toBeVisible();
  await expect(table.getByText("Healthy").first()).toBeVisible();
  await shot(page, "02-servers");
  await tourFrame(page, 2200);

  await page.goto("/servers/tickets");
  await expect(page.getByRole("button", { name: "tickets.create_ticket" })).toBeVisible();
  await shot(page, "03-server-tools");
  await tourFrame(page, 2400);

  await page.getByRole("button", { name: "tickets.create_ticket" }).click();
  await expect(page.getByRole("dialog").getByText("Input schema")).toBeVisible();
  await shot(page, "04-tool-detail");
  await page.keyboard.press("Escape");

  await page.goto("/servers/tickets?tab=versions");
  await expect(page.getByText("add_comment").first()).toBeVisible();
  await shot(page, "05-server-versions");

  await page.goto("/servers/tickets?tab=secrets");
  await expect(page.getByRole("region", { name: "Secrets" }).getByText("Authorization")).toBeVisible();
  await shot(page, "06-secrets");
  await tourFrame(page, 2200);

  await page.goto("/clients");
  await expect(
    page.getByRole("region", { name: "Clients" }).getByRole("link", { name: "Support copilot" }),
  ).toBeVisible();
  await shot(page, "07-clients");
  await tourFrame(page, 2000);

  await page.goto("/clients/support-copilot");
  await expect(page.getByText(/tools allowed/).first()).toBeVisible();
  await shot(page, "08-permission-matrix");
  await tourFrame(page, 3000);

  await page.goto("/clients/support-copilot?tab=rules");
  await expect(page.getByText("priority is one of low, normal, high")).toBeVisible();
  await shot(page, "09-rules");
  await tourFrame(page, 2400);

  await page.goto("/clients/support-copilot?tab=connect");
  await expect(page.getByLabel("Gateway endpoint").first()).toBeVisible();
  await shot(page, "10-connect");

  await page.goto("/keys");
  await expect(page.getByRole("region", { name: "API keys" }).getByText("Production key").first()).toBeVisible();
  await shot(page, "11-api-keys");

  await page.goto("/playground?client=support-copilot&tool=tickets.list_tickets");
  await page.getByRole("button", { name: "Call the tool" }).click();
  await expect(page.getByLabel("Result text").first()).toContainText("TCK-");
  await shot(page, "12-tool-tester");
  await tourFrame(page, 2800);

  await page.goto("/calls");
  await expect(page.getByRole("region", { name: "Tool calls" }).getByRole("row")).not.toHaveCount(1);
  await shot(page, "13-audit-log");
  await tourFrame(page, 2400);

  await page.goto("/calls?status=denied&status=blocked");
  await expect(page.getByRole("region", { name: "Tool calls" }).getByText("Denied").first()).toBeVisible();
  await page.getByRole("region", { name: "Tool calls" }).getByRole("button").first().click();
  await expect(page.getByRole("dialog").getByText("Arguments as recorded")).toBeVisible();
  await shot(page, "14-audit-detail");
  await tourFrame(page, 2600);
  await page.keyboard.press("Escape");

  await page.goto("/servers/weather?tab=health");
  await expect(page.getByText("Uptime, last 24 hours")).toBeVisible();
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await shot(page, "15-server-health");

  await page.goto("/settings?tab=team");
  await expect(page.getByRole("cell", { name: /priya.sharma@lumenlabs.example/ })).toBeVisible();
  await shot(page, "16-people");

  await page.evaluate(() => localStorage.setItem("mcphub-theme", "dark"));
  await page.goto("/clients/support-copilot");
  await expect(page.getByText(/tools allowed/).first()).toBeVisible();
  await shot(page, "17-permission-matrix-dark");
  await page.evaluate(() => localStorage.removeItem("mcphub-theme"));
});
