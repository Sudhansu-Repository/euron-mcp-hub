import { expect, test } from "@playwright/test";

import { PEOPLE, requirePassword, signIn, signInWithForm } from "../helpers";

test("the admin signs in and lands on the overview", async ({ page }) => {
  await signIn(page, "admin");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link")).toHaveCount(8);
  await expect(page.getByText("Gateway endpoint").first()).toBeVisible();
});

test("a wrong password is refused with a clear message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(PEOPLE.admin.email);
  await page.getByLabel("Password").fill(`${requirePassword()}-wrong`);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Next.js keeps an empty role="alert" route announcer in every page: pick ours by its text.
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect." })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("signed-out visitors are sent to sign in, then back where they were going", async ({ page }) => {
  await page.goto("/servers/tickets");
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel("Email").fill(PEOPLE.viewer.email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/servers\/tickets/);
  await expect(page.getByRole("heading", { level: 1, name: /Help desk/ })).toBeVisible();
});

test("signing out ends the session", async ({ page }) => {
  // Its own sign-in: signing out revokes the session, and the shared one must stay valid.
  await signInWithForm(page, "viewer");
  await page.getByRole("button", { name: `Account menu for ${PEOPLE.viewer.name}` }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login\?next=/);
});

test("a viewer reads everything but cannot change anything", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/servers");
  await expect(page.getByRole("heading", { name: "Servers", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect a server" })).toHaveCount(0);
  await page.goto("/clients");
  await expect(page.getByRole("button", { name: "New client" })).toHaveCount(0);
  await page.goto("/settings");
  await expect(page.getByRole("tab", { name: "People" })).toHaveCount(0);
});
