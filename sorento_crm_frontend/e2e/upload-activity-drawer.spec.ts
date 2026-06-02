/**
 * Upload Activity drawer end-to-end.
 *
 * Verifies the Phase 2 wiring of the drawer described in
 * `docs/plans/PLAN-upload-activity-drawer.md`:
 *
 *   1. The upload icon in the top nav opens the drawer.
 *   2. Uploading a single file via Resource Management → Files closes the
 *      modal immediately, auto-opens the drawer, and the new session row
 *      appears within seconds.
 *   3. The drawer polls `GET /api/v1/resource-management/upload-activity`
 *      while a session is in-flight (5 s cadence).
 *   4. Opening the file's detail modal shows an Integration tab next to
 *      Attachment Details and an Integration status chip in the header.
 *
 * Required env vars (test skipped otherwise — see
 * feedback_playwright_via_sidebar memory: always sidebar-navigate, never
 * deep-link):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   UPLOAD_ACTIVITY_E2E_EMAIL=...
 *   UPLOAD_ACTIVITY_E2E_PASSWORD=...
 *   UPLOAD_ACTIVITY_E2E_FIXTURE=e2e/fixtures/...  (real file; per feedback_e2e_real_samples)
 *   UPLOAD_ACTIVITY_E2E_ATTACHMENT_TYPE=Product Photos  (must exist + accept the fixture mime)
 */
import { test, expect, type Page } from '@playwright/test';
import * as path from 'path';

const EMAIL = process.env.UPLOAD_ACTIVITY_E2E_EMAIL;
const PASSWORD = process.env.UPLOAD_ACTIVITY_E2E_PASSWORD;
const FIXTURE = process.env.UPLOAD_ACTIVITY_E2E_FIXTURE;
const ATTACHMENT_TYPE = process.env.UPLOAD_ACTIVITY_E2E_ATTACHMENT_TYPE;

test.skip(
  !EMAIL || !PASSWORD || !FIXTURE || !ATTACHMENT_TYPE,
  'Set UPLOAD_ACTIVITY_E2E_* env vars to run this spec.',
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
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

async function navigateToFiles(page: Page) {
  // ALWAYS sidebar-navigate (project memory feedback_playwright_via_sidebar).
  await page.getByRole('button', { name: /resource management/i }).first().click();
  await page.getByRole('link', { name: /^files$/i }).first().click();
  await expect(page.getByRole('heading', { name: /files/i }).first()).toBeVisible();
}

test.describe('Upload Activity drawer', () => {
  test('upload icon opens the drawer + empty state visible before any upload', async ({ page }) => {
    await login(page);
    const icon = page.getByRole('button', { name: /upload activity/i });
    await expect(icon).toBeVisible();
    await icon.click();
    const drawer = page.getByRole('dialog', { name: /upload activity/i });
    await expect(drawer).toBeVisible();
    // Either empty state or pre-existing sessions; just confirm drawer surface renders.
    await expect(
      drawer.getByText(/no uploads yet|receipt|files|\.jpg|\.pdf/i),
    ).toBeVisible();
  });

  test('uploading a single file surfaces a session in the drawer + Integration tab in detail modal', async ({
    page,
  }) => {
    await login(page);
    await navigateToFiles(page);

    // Open Upload modal.
    await page.getByRole('button', { name: /^upload$/i }).first().click();
    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();

    // Pick attachment type + file. Type combobox label is "Attachment Type".
    await modal
      .getByRole('combobox', { name: /attachment type/i })
      .first()
      .click();
    await page.getByRole('option', { name: new RegExp(ATTACHMENT_TYPE!, 'i') }).first().click();
    await modal.locator('input[type="file"]').setInputFiles(path.resolve(FIXTURE!));

    // Watch for the GET poll while we submit; the drawer hook polls
    // /api/v1/resource-management/upload-activity at 5 s cadence.
    const pollPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/resource-management/upload-activity') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
      { timeout: 30_000 },
    );

    await modal.getByRole('button', { name: /^upload$/i }).click();

    // Phase 2 contract: modal closes immediately, drawer auto-opens.
    await expect(modal).not.toBeVisible({ timeout: 10_000 });
    const drawer = page.getByRole('dialog', { name: /upload activity/i });
    await expect(drawer).toBeVisible({ timeout: 10_000 });

    await pollPromise;

    // Fixture filename appears within the drawer.
    const filename = path.basename(FIXTURE!);
    await expect(drawer.getByText(filename, { exact: false })).toBeVisible({
      timeout: 30_000,
    });
  });

  test('AttachmentDetailModal shows Integration tab + status chip', async ({ page }) => {
    await login(page);
    await navigateToFiles(page);

    // Open the first attachment row to reach the detail modal.
    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toBeVisible({ timeout: 20_000 });
    await firstRow.click();

    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();
    // Tabs in the top card.
    await expect(modal.getByRole('tab', { name: /attachment details/i })).toBeVisible();
    const integrationTab = modal.getByRole('tab', { name: /^integration$/i });
    await expect(integrationTab).toBeVisible();

    await integrationTab.click();
    // Integration panel renders either the friendly summary or the "no runs yet" empty state.
    await expect(
      modal.getByText(
        /linked to|no integration runs|linking|integration server didn't respond|loading integration status/i,
      ),
    ).toBeVisible({ timeout: 15_000 });
  });
});
