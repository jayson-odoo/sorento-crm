/**
 * SCM M1 (CP2b) e2e — FE → BE → DB round-trip against the real `scm` API.
 *
 * Run against a running stack (FE :3000 + BE :8000 with the `scm` module enabled
 * for the tenant + the M0/M1 seed applied — `scripts/seed_scm_demo.py`):
 *
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   SCM_E2E_EMAIL=admin@example.com \
 *   SCM_E2E_PASSWORD='...' \
 *   npx playwright test e2e/scm-dashboard.spec.ts
 *
 * Skipped automatically when the credentials aren't set so it doesn't block
 * local dev. Navigation always goes through the sidebar (never a deep URL) so a
 * broken menu gate (moduleKey / permission) fails the test.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.SCM_E2E_EMAIL;
const PASSWORD = process.env.SCM_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set SCM_E2E_EMAIL and SCM_E2E_PASSWORD to run the SCM flow');

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

/** Expand the "Supply Chain" sidebar group and click a leaf. */
async function openScmLeaf(page: Page, leaf: RegExp) {
  const group = page.getByRole('button', { name: /supply chain/i }).first();
  await expect(group).toBeVisible({ timeout: 15_000 });
  await group.click();
  await page.getByRole('link', { name: leaf }).first().click();
}

test('sidebar → dashboard loads real net-position data + drill-down + filter', async ({ page }) => {
  const scmCalls: string[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (u.includes('/api/v1/scm/')) scmCalls.push(`${r.method()} ${new URL(u).pathname}`);
  });

  await login(page);
  await openScmLeaf(page, /^Dashboard$/);
  await page.waitForURL(/\/scm$/);

  // Roll-up + warehouse read models fire on mount.
  await expect
    .poll(() => scmCalls.some((c) => c.includes('/scm/dashboard/rollups')))
    .toBeTruthy();
  await expect
    .poll(() => scmCalls.some((c) => c.includes('/scm/dashboard/warehouses')))
    .toBeTruthy();

  // Switch to the Product perspective → net-position list loads. The perspective
  // toggle renders as a Radix ToggleGroup (radio items).
  await page.getByRole('radio', { name: 'Product' }).click();
  await expect
    .poll(() => scmCalls.some((c) => c.includes('/scm/dashboard/net-position')), { timeout: 15_000 })
    .toBeTruthy();

  // A seeded SKU renders from real data.
  await expect(page.getByText(/WESERP10B|CWCY605|C-FH24/).first()).toBeVisible({ timeout: 15_000 });

  // Supplier perspective hits the suppliers read model.
  await page.getByRole('radio', { name: 'Supplier' }).click();
  await expect
    .poll(() => scmCalls.some((c) => c.includes('/scm/dashboard/suppliers')), { timeout: 15_000 })
    .toBeTruthy();
});

test('sidebar → sales orders list loads real SO data', async ({ page }) => {
  const scmCalls: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/scm/sales-orders')) scmCalls.push(r.method());
  });

  await login(page);
  await openScmLeaf(page, /^Sales Orders$/);
  await page.waitForURL(/\/scm\/sales-orders$/);

  await expect.poll(() => scmCalls.length > 0, { timeout: 15_000 }).toBeTruthy();
  // A seeded SO number renders.
  await expect(page.getByText(/^SO-/).first()).toBeVisible({ timeout: 15_000 });
});

test('sidebar → purchase orders read-only list loads real PO data', async ({ page }) => {
  const scmCalls: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/scm/purchase-orders')) scmCalls.push(r.method());
  });

  await login(page);
  await openScmLeaf(page, /^Purchase Orders$/);
  await page.waitForURL(/\/scm\/purchase-orders$/);

  await expect.poll(() => scmCalls.length > 0, { timeout: 15_000 }).toBeTruthy();
  await expect(page.getByRole('heading', { name: /purchase orders/i }).first()).toBeVisible();
});
