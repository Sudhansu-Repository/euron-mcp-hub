import { expect, test } from "@playwright/test";

import { signIn } from "../helpers";

test("the tool tester calls a tool as a client and shows the result", async ({ page }) => {
  await signIn(page, "operator");
  await page.goto("/playground?client=ops-agent&tool=toolbox.calculate");
  await expect(page.getByLabel("Tool")).toHaveValue("toolbox.calculate");
  await page.getByLabel("expression").fill("(12 + 8) * 3");
  await page.getByRole("button", { name: "Call the tool" }).click();
  const result = page.getByRole("region", { name: "Result text" }).or(page.getByLabel("Result text"));
  await expect(result).toContainText("60");
  await expect(page.getByText("OK", { exact: true }).first()).toBeVisible();
});

test("a tool the client may not use is refused the way the gateway refuses it", async ({ page }) => {
  await signIn(page, "operator");
  await page.goto("/playground?client=research-assistant&tool=tickets.list_tickets");
  const denied = page.locator("span").filter({ hasText: /^Denied$/ });
  await expect(denied.first()).toBeVisible();
  await page.getByRole("button", { name: "Call the tool" }).click();
  await expect(page.getByText("Unknown tool").first()).toBeVisible();
  await expect(denied.nth(1)).toBeVisible();
});

test("a viewer cannot make calls", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/playground?client=ops-agent&tool=toolbox.calculate");
  await expect(page.getByRole("button", { name: "Call the tool" })).toBeDisabled();
});
