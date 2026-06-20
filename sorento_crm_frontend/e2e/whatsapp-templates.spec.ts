/**
 * WhatsApp template sync + default-template configuration (PLAN-whatsapp-template-fallback).
 *
 * Drives the real stack (FE :3000 + BE :8000 + a configured Respond.io
 * workspace) through the settings page:
 *   sidebar → WhatsApp Templates → Sync templates → set a per-use-case default
 *   with a param mapping → assert the row reflects it and the GET round-trips.
 *
 * Requires:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000
 *   WA_TEMPLATES_E2E_EMAIL=admin@example.com
 *   WA_TEMPLATES_E2E_PASSWORD='...'
 *
 * Run: npx playwright test e2e/whatsapp-templates.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.WA_TEMPLATES_E2E_EMAIL;
const PASSWORD = process.env.WA_TEMPLATES_E2E_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  'Set WA_TEMPLATES_E2E_EMAIL / WA_TEMPLATES_E2E_PASSWORD to run this spec.',
);

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page
    .locator('input[type="password"], input[name="password"]')
    .first()
    .fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

async function navigateViaSidebar(page: Page) {
  const link = page.getByRole('link', { name: /^WhatsApp Templates$/i }).first();
  const group = page.getByRole('button', { name: /system management/i }).first();
  // Wait for the sidebar to hydrate + settle before interacting — clicking the
  // group while it animates/mounts is a no-op and leaves the leaf hidden.
  await expect(group).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1_500);
  // Expand if the leaf isn't already visible; retry once since the first click
  // can land mid-animation. Clicking an already-expanded group collapses it,
  // so re-check visibility between attempts.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (await link.isVisible().catch(() => false)) break;
    await group.click({ timeout: 5_000, force: true }).catch(() => undefined);
    await page.waitForTimeout(800);
  }
  await expect(link).toBeVisible({ timeout: 10_000 });
  await link.click();
  await page.waitForURL(/\/integration-management\/whatsapp-templates/);
}

test('sync templates then set a complaint default with a param mapping', async ({ page }) => {
  await login(page);
  await navigateViaSidebar(page);

  // Sync from the live workspace; toast confirms how many templates landed.
  const syncReq = page.waitForResponse(
    (r) =>
      r.url().includes('/integrations/respond/templates/sync') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: /sync templates/i }).click();
  expect((await syncReq).ok()).toBeTruthy();

  // At least one approved template should now be in the grid.
  await expect(page.getByRole('cell', { name: /approved/i }).first()).toBeVisible({
    timeout: 15_000,
  });

  // Configure the complaint default.
  const complaintRow = page.getByTestId('default-row-complaint');
  await complaintRow.getByRole('button', { name: /set template|change/i }).click();

  const dialog = page.getByRole('dialog', { name: /default template/i });
  await expect(dialog).toBeVisible();

  // Pick the first approved template.
  await dialog.getByRole('combobox').first().click();
  await page.getByRole('option').first().click();

  // Map every surfaced placeholder to a variable.
  const paramSelects = dialog.getByRole('combobox');
  const count = await paramSelects.count();
  for (let i = 1; i < count; i += 1) {
    await paramSelects.nth(i).click();
    await page.getByRole('option').first().click();
  }

  const putReq = page.waitForResponse(
    (r) =>
      r.url().includes('/integrations/respond/template-defaults/complaint') &&
      r.request().method() === 'PUT',
  );
  await dialog.getByRole('button', { name: /save default/i }).click();
  expect((await putReq).ok()).toBeTruthy();

  // Row reflects the saved mapping (→ rendered in the summary line).
  await expect(complaintRow.getByText(/→/)).toBeVisible({ timeout: 10_000 });
});
