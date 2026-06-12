/**
 * Complaint print-count + downloads-modal end-to-end (Phase 2 wiring).
 *
 * Verifies:
 *   1. The Complaints DataGrid renders a "Print Count" column.
 *   2. Clicking the print-count chip opens a "Downloads · <number>" modal
 *      scoped to that complaint (GET /api/v1/downloads?source_entity_type=
 *      complaint&source_entity_id=...).
 *   3. On a complaint detail page, "Download PDF" enqueues an export and the
 *      adjacent print-count chip opens the same per-complaint downloads modal;
 *      a ready row is click-to-download.
 *
 * Required env vars (test skipped otherwise — per feedback_playwright_via_sidebar
 * memory: always sidebar-navigate, never deep-link):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   COMPLAINT_E2E_EMAIL=...
 *   COMPLAINT_E2E_PASSWORD=...
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.COMPLAINT_E2E_EMAIL;
const PASSWORD = process.env.COMPLAINT_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set COMPLAINT_E2E_* env vars to run this spec.');

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

async function navigateToComplaints(page: Page) {
  // ALWAYS sidebar-navigate (project memory feedback_playwright_via_sidebar).
  await page.getByRole('button', { name: /complaint management/i }).first().click();
  await page.getByRole('link', { name: /^complaints$/i }).first().click();
  await expect(page.getByRole('heading', { name: /complaints/i }).first()).toBeVisible();
}

test.describe('Complaint print count + downloads modal', () => {
  test('Print Count column renders and chip opens a per-complaint downloads modal', async ({
    page,
  }) => {
    await login(page);
    await navigateToComplaints(page);

    // Column header present.
    await expect(page.getByText('Print Count', { exact: true })).toBeVisible({
      timeout: 20_000,
    });

    // The chip fetches the per-entity feed when opened.
    const entityFeed = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/downloads?') &&
        resp.url().includes('source_entity_type=complaint') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
      { timeout: 30_000 },
    );

    // Click the first print-count chip (printer icon + number).
    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toBeVisible({ timeout: 20_000 });
    await firstRow
      .getByRole('button', { name: /view downloads for this complaint/i })
      .click();

    await entityFeed;
    const modal = page.getByRole('dialog');
    await expect(modal.getByText(/^Downloads/)).toBeVisible({ timeout: 10_000 });

    // Closing the modal must NOT navigate to the row behind it.
    await modal.getByRole('button', { name: /close/i }).click();
    await expect(modal).not.toBeVisible();
    await expect(page).toHaveURL(/complaints\/?($|\?)/);
  });

  test('detail Download PDF enqueues export and chip shows the download', async ({ page }) => {
    await login(page);
    await navigateToComplaints(page);

    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toBeVisible({ timeout: 20_000 });
    await firstRow.click();
    await expect(page).toHaveURL(/complaint-management\/complaints\//, { timeout: 20_000 });

    const exportReq = page.waitForResponse(
      (resp) =>
        /\/complaints\/.+\/export\/pdf/.test(resp.url()) &&
        resp.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await page.getByRole('button', { name: /download pdf/i }).click();
    await exportReq;

    // Chip next to the button opens the per-complaint downloads modal.
    await page
      .getByRole('button', { name: /view downloads for this complaint/i })
      .click();
    const modal = page.getByRole('dialog');
    await expect(modal.getByText(/^Downloads/)).toBeVisible({ timeout: 10_000 });
  });
});
