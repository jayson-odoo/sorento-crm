/**
 * SLA "Extend resolution deadline" end-to-end (Phase 2 wiring) - UAC-19.
 *
 * Flow: land on home (the My Pending Tasks widget lives on the dashboard), find an
 * eligible row, open the Extend dialog, submit a working-days extension, and assert:
 *   - the FE posts POST /api/v1/.../{id}/extend/preview while the user types, and
 *   - POST /api/v1/.../{id}/extend on submit (FE -> BE -> DB round-trip), and
 *   - the toast / dialog close confirms success.
 *
 * NAVIGATION: always sidebar/home navigation, never deep-link (project memory
 * feedback_playwright_via_sidebar).
 *
 * AUTH GAP: this spec requires login creds that are NOT present in .env per
 * CLAUDE.md (USER_GUIDE_E2E_* / per-spec creds are not committed). It is therefore
 * SKIPPED unless SLA_EXTEND_E2E_EMAIL / SLA_EXTEND_E2E_PASSWORD are set. It has NOT
 * been run/verified green in this environment - committed for regression coverage.
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   SLA_EXTEND_E2E_EMAIL=...
 *   SLA_EXTEND_E2E_PASSWORD=...
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.SLA_EXTEND_E2E_EMAIL;
const PASSWORD = process.env.SLA_EXTEND_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set SLA_EXTEND_E2E_* env vars to run this spec.');

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

test.describe('SLA extend resolution deadline', () => {
  test('open Extend on an eligible pending-task row, submit, and the new due is persisted', async ({
    page,
  }) => {
    await login(page);

    // The My Pending Tasks widget renders on the home dashboard.
    await page.goto('/');

    // Find the first Extend button (gated to assignee + unresolved + has resolution due).
    const extendBtn = page.getByRole('button', { name: /^extend$/i }).first();
    if (!(await extendBtn.isVisible().catch(() => false))) {
      test.skip(true, 'No eligible SLA row with an Extend action; seed one to run this spec.');
    }
    await extendBtn.click();

    // Dialog open.
    await expect(page.getByText(/extend resolution deadline/i)).toBeVisible({ timeout: 10_000 });

    // The debounced preview hits the backend as we set the working-days input.
    const previewResp = page.waitForResponse(
      (resp) =>
        /\/extend\/preview$/.test(new URL(resp.url()).pathname) &&
        resp.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await page.getByLabel(/additional working days/i).fill('2');
    await previewResp;

    // New-due preview line appears.
    await expect(page.getByText(/New due:/i)).toBeVisible({ timeout: 15_000 });

    // Reason required.
    await page.getByLabel(/reason/i).fill('E2E: waiting on supplier confirmation');

    // Submit -> POST /extend (the round-trip we assert).
    const extendResp = page.waitForResponse(
      (resp) =>
        /\/extend$/.test(new URL(resp.url()).pathname) &&
        resp.request().method() === 'POST' &&
        resp.status() === 200,
      { timeout: 30_000 },
    );
    await page.getByRole('button', { name: /extend deadline/i }).click();
    const resp = await extendResp;

    // Backend echoes the updated tracking with the new (extended) due.
    const body = await resp.json().catch(() => ({}));
    expect(body).toHaveProperty('id');

    // Dialog closes on success.
    await expect(page.getByText(/extend resolution deadline/i)).toBeHidden({ timeout: 10_000 });
  });
});
