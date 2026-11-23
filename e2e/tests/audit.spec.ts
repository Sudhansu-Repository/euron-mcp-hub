import { expect, test } from "@playwright/test";

import { signIn } from "../helpers";

test("the audit log filters by outcome and opens a call in full", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/calls");
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
  const table = page.getByRole("region", { name: "Tool calls" });
  await expect(table.getByRole("row")).not.toHaveCount(1);

  await page.getByRole("button", { name: /^Outcome/ }).click();
  await page.getByRole("menuitemcheckbox", { name: "Denied" }).click();
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/status=denied/);
  await expect(table.getByText("Denied").first()).toBeVisible();
  await expect(table.getByText("OK", { exact: true })).toHaveCount(0);

  await table.getByRole("button").first().click();
  const detail = page.getByRole("dialog");
  await expect(detail.getByText("Arguments as recorded")).toBeVisible();
  await expect(detail.getByText("Client", { exact: true })).toBeVisible();
});

test("calls can be filtered by client and searched, and exported", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/calls");
  await page.getByLabel("Filter by client").selectOption("support-copilot");
  await expect(page).toHaveURL(/client=support-copilot/);
  const table = page.getByRole("region", { name: "Tool calls" });
  await expect(table.getByText("tickets.", { exact: false }).first()).toBeVisible();
  await expect(table.getByRole("cell", { name: "Support copilot" }).first()).toBeVisible();
  await expect(table.getByRole("cell", { name: "Ops runbook agent" })).toHaveCount(0);
  await page.getByLabel("Search calls").fill("delete_ticket");
  await expect(table.getByText("tickets.delete_ticket").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Export CSV" })).toHaveAttribute(
    "href",
    /calls\/export.*client=support-copilot/,
  );
});

test("credentials never appear in recorded arguments", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/calls?q=requester_email");
  const table = page.getByRole("region", { name: "Tool calls" });
  await expect(table.getByText("tickets.create_ticket").first()).toBeVisible();
  await table.getByRole("button", { name: "tickets.create_ticket" }).first().click();
  const detail = page.getByRole("dialog");
  await expect(detail.getByLabel("Recorded arguments")).toContainText("[redacted]");
  await expect(detail.getByLabel("Recorded arguments")).not.toContainText("@acmefreight.example");
});
