/**
 * Promotion expiry-batch deep link + Compile-PDF end-to-end (Phase 2 wiring).
 *
 * Verifies the FE → BE → DB round-trip for the compile-PDF flow:
 *   1. Sidebar-navigate to Marketing Management → Promotions → All Promotions
 *      (per feedback_playwright_via_sidebar: never deep-link into a page cold).
 *   2. Select promotions in the grid and fire the "Compile PDF" bulk action;
 *      assert the POST to /api/v1/marketing/promotions/export/pdf and that a
 *      "Promotions PDF" row appears in the My Downloads drawer.
 *   3. The `?expiry_notify_batch_id=` deep link (from a reminder email) renders
 *      the dismissable batch banner and re-queries the list scoped to the batch.
 *
 * Required env vars (test skipped otherwise):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   PROMO_E2E_EMAIL=...
 *   PROMO_E2E_PASSWORD=...
 *
 * The compile flow merges each promotion's ALREADY-LINKED attachment flyers
 * server-side (real bytes via the storage router) - no upload fixture is needed
 * here; it exercises whatever promotions the environment already has.
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.PROMO_E2E_EMAIL;
const PASSWORD = process.env.PROMO_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set PROMO_E2E_* env vars to run this spec.');

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
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

async function navigateToPromotions(page: Page) {
  // ALWAYS sidebar-navigate (project memory feedback_playwright_via_sidebar).
  await page.getByRole('button', { name: /marketing management/i }).first().click();
  // "Promotions" group → "All Promotions" leaf.
  await page.getByRole('button', { name: /^promotions$/i }).first().click();
  await page.getByRole('link', { name: /all promotions/i }).first().click();
  await expect(page).toHaveURL(/marketing-management\/promotions/, { timeout: 20_000 });
}

test.describe('Promotion compile-PDF + expiry batch deep link', () => {
  test('selecting promotions and Compile PDF enqueues a Promotions PDF download', async ({
    page,
  }) => {
    await login(page);
    await navigateToPromotions(page);

    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toBeVisible({ timeout: 20_000 });

    // Select all rows via the header select-all checkbox (first checkbox).
    await page.locator('table thead input[type="checkbox"], table thead [role="checkbox"]').first().click();

    // Fire the Compile PDF bulk action and assert the compile POST.
    const compileReq = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/marketing/promotions/export/pdf') &&
        resp.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await page.getByRole('button', { name: /compile pdf/i }).click();
    const resp = await compileReq;
    // 202 Accepted with a download_id; the request body carries the selected ids.
    expect(resp.status()).toBe(202);
    const body = resp.request().postDataJSON() as { promotion_ids: string[] };
    expect(Array.isArray(body.promotion_ids)).toBe(true);
    expect(body.promotion_ids.length).toBeGreaterThan(0);

    // Open the My Downloads drawer and assert a "Promotions PDF" row surfaces.
    await page.getByRole('button', { name: /my downloads/i }).first().click();
    await expect(page.getByText('Promotions PDF').first()).toBeVisible({ timeout: 30_000 });
  });

  test('expiry_notify_batch_id deep link shows the batch banner and filters', async ({
    page,
  }) => {
    await login(page);
    await navigateToPromotions(page);

    // Deep link from a reminder email - the list re-queries scoped to the batch.
    const listReq = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/marketing/promotions') &&
        resp.url().includes('expiry_notify_batch_id=') &&
        resp.request().method() === 'GET',
      { timeout: 30_000 },
    );
    await page.goto('/marketing-management/promotions?expiry_notify_batch_id=00000000-0000-0000-0000-000000000000');
    await listReq;

    await expect(
      page.getByText(/Showing promotions from a recent expiry-reminder batch/i),
    ).toBeVisible({ timeout: 20_000 });

    // Clear dismisses the banner and drops the param.
    await page.getByRole('button', { name: /^clear$/i }).click();
    await expect(
      page.getByText(/Showing promotions from a recent expiry-reminder batch/i),
    ).not.toBeVisible();
    await expect(page).not.toHaveURL(/expiry_notify_batch_id=/);
  });
});
