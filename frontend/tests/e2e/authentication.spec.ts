import { expect, test, type Page } from "@playwright/test";
import { E2E_USERS } from "./keycloak";

async function login(page: Page, user: keyof typeof E2E_USERS, returnTo = "/") {
  const account = E2E_USERS[user];
  await page.goto(`/api/auth/login?return_to=${encodeURIComponent(returnTo)}`);
  await page.locator("#username").fill(account.username);
  await page.locator("#password").fill(account.password);
  await page.locator("#kc-login").click();
  await expect(page).toHaveURL(new RegExp(`${returnTo.replace("/", "\\/")}(?:$|\\?)`));
}

test.describe.serial("Keycloak authentication", () => {
  test("logs a patient in and applies a nonce CSP", async ({ page }) => {
    await login(page, "patient", "/patient");
    await expect(page.getByRole("heading", { name: "Patient intake" })).toBeVisible();
    const response = await page.goto("/patient");
    const csp = response?.headers()["content-security-policy"] ?? "";
    expect(csp).toContain("script-src");
    expect(csp).toContain("'nonce-");
    expect(csp).toContain("'strict-dynamic'");
    expect(csp).toContain("form-action 'self' http://localhost:8500");
    expect(csp).not.toContain("'unsafe-inline'");
  });

  test("enforces role boundaries", async ({ page }) => {
    await login(page, "patient", "/patient");
    await page.goto("/doctor");
    await expect(page).toHaveURL(/\/?access=denied$/);
    await expect(page.getByRole("heading", { name: "Doctor workspace" })).toHaveCount(0);
  });

  test("logs out locally and from Keycloak", async ({ page }) => {
    await login(page, "patient", "/patient");
    const logoutResponse = page.waitForResponse((response) => response.url().endsWith("/api/auth/logout"));
    await page.getByRole("button", { name: "Sign out" }).click();
    expect((await logoutResponse).status()).toBe(303);
    const confirm = page.locator("#kc-logout");
    if (await confirm.isVisible()) await confirm.click();
    await expect(page).toHaveURL("http://localhost:3000/");
    await expect(page.getByText("Signed in as")).toHaveCount(0);
  });

  test("revokes an active browser session", async ({ browser }) => {
    const patientContext = await browser.newContext();
    const adminContext = await browser.newContext();
    const patientPage = await patientContext.newPage();
    const adminPage = await adminContext.newPage();
    try {
      await login(patientPage, "patient", "/patient");
      const me = await patientPage.request.get("/api/careflow/auth/me");
      expect(me.ok()).toBeTruthy();
      const patient = await me.json() as { user_id: string };

      await login(adminPage, "admin", "/admin");
      const csrf = (await adminContext.cookies()).find((cookie) => cookie.name === "careflow_csrf")?.value;
      expect(csrf).toBeTruthy();
      const revoked = await adminPage.request.post(`/api/careflow/auth/users/${patient.user_id}/revoke-sessions`, {
        headers: { "x-csrf-token": csrf! },
      });
      expect(revoked.ok()).toBeTruthy();
      const result = await revoked.json() as { revoked: number };
      expect(result.revoked).toBeGreaterThanOrEqual(1);

      const expired = await patientPage.request.get("/api/careflow/auth/me");
      expect(expired.status()).toBe(401);
    } finally {
      await patientContext.close();
      await adminContext.close();
    }
  });
});
