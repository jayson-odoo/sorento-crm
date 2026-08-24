/**
 * Complaints record-navigation end-to-end (Phase 2).
 *
 * Acceptance criteria exercised (docs/plans/PLAN-record-navigation-standardization.md §9):
 * - UAC-1  Apply a search filter -> open a row -> the detail pager total equals
 *            the FILTERED count, not the unfiltered total.
 * - UAC-3  Clicking Next lands on the correct neighbour and the counter
 *            increments.
 * - UAC-10 The filter is carried into the detail URL (so the neighbours call
 *            includes the filter) and preserved when stepping between records.
 * - Asserts the FE fired GET .../complaints/neighbours?...&query=<filter>
 *     (FE -> BE -> DB round-trip via browser_network_requests equivalent).
 *
 * ALWAYS sidebar-navigate (project memory feedback_playwright_via_sidebar), never
 * deep-link to the detail page directly.
 *
 * Required env (skipped otherwise):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000  (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_* env vars to run this spec.');

// A search term expected to match a known, small subset of complaints.
const FILTER = process.env.COMPLAINT_NAV_FILTER ?? '04';

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
  await page.getByRole('button', { name: /complaint management/i }).first().click();
  await page.getByRole('link', { name: /^complaints$/i }).first().click();
  await expect(
    page.getByRole('heading', { name: /complaints/i }).first(),
  ).toBeVisible();
}

/** Read the pager total from the counter span aria-label "X of Y records". */
async function readPagerTotal(page: Page): Promise<number> {
  const counter = page.locator('[aria-label$="records"]').first();
  await expect(counter).toBeVisible({ timeout: 20_000 });
  const label = (await counter.getAttribute('aria-label')) ?? '';
  const m = label.match(/(\d+)\s+of\s+(\d+)\s+records/i);
  expect(m, `pager aria-label should read "X of Y records", got "${label}"`).not.toBeNull();
  return Number(m![2]);
}

async function readPagerIndex(page: Page): Promise<number> {
  const counter = page.locator('[aria-label$="records"]').first();
  const label = (await counter.getAttribute('aria-label')) ?? '';
  const m = label.match(/(\d+)\s+of\s+(\d+)\s+records/i);
  return Number(m![1]);
}

test.describe('Complaints filtered prev/next navigation', () => {
  test('filtered pager total == filtered list count; Next steps correctly', async ({
    page,
  }) => {
    await login(page);
    await navigateToComplaints(page);

    // Apply the search filter.
    const search = page.getByPlaceholder(/search complaints/i);
    await expect(search).toBeVisible({ timeout: 20_000 });
    await search.fill(FILTER);

    // Wait for the filtered list to settle and count the filtered rows.
    await page.waitForTimeout(1200); // debounce + refetch
    const rows = page.locator('table tbody tr');
    const filteredCount = await rows.count();
    expect(filteredCount).toBeGreaterThan(0);

    // Open a middle row so prev AND next exist (UAC-3 both directions).
    const targetRowIdx = Math.min(1, filteredCount - 1);

    // The neighbours call MUST carry the filter (UAC-1/UAC-10).
    const neighboursReq = page.waitForResponse(
      (resp) =>
        resp.url().includes('/complaints/neighbours') &&
        resp.url().includes(`query=${encodeURIComponent(FILTER)}`) &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
      { timeout: 30_000 },
    );

    await rows.nth(targetRowIdx).click();
    await expect(page).toHaveURL(
      /complaint-management\/complaints\/.+query=/,
      { timeout: 20_000 },
    );
    await neighboursReq;

    // UAC-1: pager total equals the filtered list count, NOT the unfiltered total.
    const total = await readPagerTotal(page);
    expect(total).toBe(filteredCount);

    const indexBefore = await readPagerIndex(page);

    // UAC-3: Next steps to the neighbour and the counter increments (or wraps).
    const nextNeighboursReq = page.waitForResponse(
      (resp) =>
        resp.url().includes('/complaints/neighbours') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
      { timeout: 30_000 },
    );
    await page.getByRole('button', { name: /next complaint/i }).click();
    await nextNeighboursReq;
    await page.waitForTimeout(500);

    const indexAfter = await readPagerIndex(page);
    const totalAfter = await readPagerTotal(page);
    expect(totalAfter).toBe(filteredCount); // total stable across navigation
    // index increments by 1, or wraps from last back to 1 (circular, D3/UAC-6).
    const expectedNext = indexBefore === total ? 1 : indexBefore + 1;
    expect(indexAfter).toBe(expectedNext);

    // No console errors during the flow.
    // (Playwright surfaces page errors via the 'pageerror' event if wired; this
    // spec relies on the assertions above for correctness.)
  });
});
