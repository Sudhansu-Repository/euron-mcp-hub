import { expect, test } from "@playwright/test";

import { apiGet, signIn, unique } from "../helpers";

test("an admin adds a person and sees the one-time password once", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/settings?tab=team");
  await page.getByRole("button", { name: "Add a person" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a person" });
  const email = `${unique("e2e")}@lumenlabs.example`;
  await dialog.getByLabel(/^Name\b/).fill("E2E Person");
  await dialog.getByLabel("Email").fill(email);
  await dialog.getByLabel("Role").selectOption("viewer");
  await dialog.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("dialog", { name: "Account created" }).getByLabel("One-time password")).not.toBeEmpty();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("cell", { name: new RegExp(email) })).toBeVisible();

  // Deactivate the account so repeated runs leave nothing usable behind.
  const row = page.getByRole("row").filter({ hasText: email });
  await row.getByRole("button", { name: "Deactivate" }).click();
  await expect(row.getByText("Deactivated")).toBeVisible();
});

test("the deployment page reports what the API reports", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/settings?tab=deployment");
  const info = await apiGet<{ version: string; gateway_url: string }>(page, "/system/info");
  await expect(page.getByText(`v${info.version}`)).toBeVisible();
  await expect(page.getByLabel("Gateway endpoint")).toContainText(info.gateway_url);
  await expect(page.getByText(/KMS/).first()).toBeVisible();
});

test("the activity feed names who changed what", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/settings?tab=activity");
  const table = page.getByRole("region", { name: "Administrative activity" });
  await expect(table.getByRole("row")).not.toHaveCount(1);
  await expect(table.getByText("Daniel Okafor").first()).toBeVisible();
});
