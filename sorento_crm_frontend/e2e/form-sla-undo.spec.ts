/**
 * Form SLA Undo end-to-end (PLAN-form-sla-undo.md, Phase 2).
 *
 * Covers the promise the feature actually makes, against the real stack:
 *   1. Approving a request whose stage configures a grace window DEFERS - the API
 *      answers 202, the countdown banner appears, and every business CTA (including
 *      Edit / Delete) disappears while the action is in flight.
 *   2. Undo inside the window leaves the form exactly as it was: the request is still
 *      pending approval and no approval-decision side effect ran.
 *
 * The post-grace reversal is covered by pytest (guardrail + inverse + tracker void /
 * reopen), because asserting it here would mean waiting out a real grace window and
 * then reaching into the database to prove the trackers moved.
 *
 * Requires a purchase request in `approval_status = 'pending'` AND a grace window on
 * the purchase_request / project_sales_manager stage:
 *   UPDATE form_sla_configs SET grace_seconds = 60
 *    WHERE source_entity_type = 'purchase_request'
 *      AND team_set_code = 'project_sales_manager';
 *
 * Env (test skipped otherwise):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL=...
 *   REQUEST_BATCH_E2E_PASSWORD=...
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_* env vars to run this spec.');

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

/** ALWAYS sidebar-navigate - a deep link hides nav-config and permission-gating bugs. */
async function navigateToPurchaseRequests(page: Page) {
  // The entry may already be exposed (pinned to Quick Access, or its group left open),
  // in which case the group button is not rendered at all. Expand only when needed, so
  // this still proves the sidebar route exists without depending on its collapsed state.
  const link = page.locator('a[href="/procurement-management/purchase-requests"]').first();
  if (!(await link.isVisible().catch(() => false))) {
    const group = page.getByRole('button', { name: /procurement/i }).first();
    await group.scrollIntoViewIfNeeded();
    await group.click();
  }
  await expect(link).toBeVisible({ timeout: 20_000 });
  await link.click();
  await expect(page).toHaveURL(/purchase-requests/, { timeout: 20_000 });
}

/** Open the first request the grid offers that is still awaiting a decision. */
async function openAPendingRequest(page: Page): Promise<boolean> {
  const rows = page.locator('tbody tr');
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });

  // Click the request-number cell by its text, not by column index: the grid's column
  // order is user-personalisable, so nth(1) is not dependably the number column.
  const numbers = page.locator('tbody tr').getByText(/^(PR|PSSF)\d{2}-\d{4}$/);
  // `rows.first()` turns visible on the skeleton, before the fetch resolves - wait for
  // real content or the count below reads 0.
  await expect(numbers.first()).toBeVisible({ timeout: 30_000 });
  const count = Math.min(await numbers.count(), 25);

  for (let i = 0; i < count; i += 1) {
    await numbers.nth(i).click();
    await expect(page).toHaveURL(/purchase-requests\/[0-9a-f-]{36}/, { timeout: 20_000 });
    const approve = page.getByRole('button', { name: /^approve$/i }).first();
    if (await approve.isVisible({ timeout: 5_000 }).catch(() => false)) return true;
    await page.goBack();
    await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  }
  return false;
}

test.describe('Form SLA undo', () => {
  test('approving defers, and undo inside the window leaves the form untouched', async ({
    page,
  }) => {
    await login(page);
    await navigateToPurchaseRequests(page);

    test.skip(
      !(await openAPendingRequest(page)),
      'No purchase request awaiting approval in this environment.',
    );

    // The decision must come back 202 (deferred), not 200 - a 200 here means the stage
    // has no grace window configured and the rest of the test is meaningless.
    const decision = page.waitForResponse(
      (resp) =>
        resp.url().includes('/approval-decision') && resp.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /^approve$/i }).first().click();
    const response = await decision;
    expect(response.status()).toBe(202);
    expect((await response.json()).deferred).toBe(true);

    // The countdown appears and says plainly that nothing has happened yet.
    const banner = page.getByTestId('form-action-banner');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText(/nothing has happened yet/i);

    // Every business CTA is suppressed while the action is in flight - including Edit
    // and Delete, so the action cannot commit against a row that changed underneath it.
    await expect(page.getByRole('button', { name: /^approve$/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^reject$/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^edit$/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^delete$/i })).toHaveCount(0);

    // Undo inside the window.
    const cancel = page.waitForResponse(
      (resp) => resp.url().includes('/form-actions/') && resp.url().includes('/cancel'),
    );
    await page.getByTestId('form-action-undo-pending').click();
    expect((await cancel).status()).toBe(200);

    // Back exactly where we started: banner gone, decision CTAs offered again.
    await expect(banner).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByRole('button', { name: /^approve$/i }).first()).toBeVisible({
      timeout: 15_000,
    });
  });
});
