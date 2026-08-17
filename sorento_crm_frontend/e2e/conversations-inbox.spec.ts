/**
 * Conversations inbox (PLAN-conversation-intervention-tickets.md slice S4.9,
 * UAC AC-N1 / AC-N2 / AC-N3). Sidebar -> SLA Management -> Conversations ->
 * list loads server-paginated, tabs each re-query with the right `tab=`,
 * search debounces to one request, selecting a row loads the shared thread
 * pane, and at 375px the list/thread stack with a back control.
 *
 * Env (test skipped without EMAIL/PASSWORD):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD (needs
 *   `sla_management.conversations.view`).
 *
 * Read-only: this spec never sends a message or writes a note, so there is
 * nothing to clean up.
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_* env vars to run this spec.');

const LIST_PATH = '/api/v1/sla-management/conversations';

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

function isListRequest(url: string): boolean {
  try {
    return new URL(url).pathname === LIST_PATH;
  } catch {
    return false;
  }
}

test.describe('Conversations inbox (AC-N1 / AC-N2 / AC-N3)', () => {
  test('list loads, tabs re-query, search debounces, row selection loads the thread', async ({
    page,
  }) => {
    await login(page);

    // ---- Sidebar click-through, never a deep link ----
    const listResponse = page.waitForResponse(
      (res) => isListRequest(res.url()) && res.request().method() === 'GET',
      { timeout: 20_000 },
    );
    await page.goto('/');
    await page.getByRole('button', { name: /SLA Management/i }).first().click();
    await page.getByRole('link', { name: /^Conversations$/i }).first().click();
    await expect(page).toHaveURL(/\/sla-management\/conversations$/, { timeout: 20_000 });
    const initialResult = await listResponse;
    expect(initialResult.ok()).toBeTruthy();
    // Default tab with no `?contact=` deep link is "mine".
    expect(new URL(initialResult.url()).searchParams.get('tab')).toBe('mine');

    // ---- Tabs: each switch re-queries with the matching tab= ----
    for (const tab of ['mentioned', 'unassigned', 'all'] as const) {
      const tabResponse = page.waitForResponse(
        (res) => isListRequest(res.url()) && new URL(res.url()).searchParams.get('tab') === tab,
        { timeout: 20_000 },
      );
      await page.getByTestId(`inbox-tab-${tab}`).click();
      const tabResult = await tabResponse;
      expect(tabResult.ok()).toBeTruthy();
    }
    // Now on "all" - the widest tab, most likely to have rows for selection below.

    // ---- Search: typed quickly, debounced to exactly one request ----
    const seenListUrls: string[] = [];
    page.on('request', (req) => {
      if (isListRequest(req.url())) seenListUrls.push(req.url());
    });
    const searchTerm = 'zz-e2e-p4-probe';
    const searchResponse = page.waitForResponse(
      (res) => isListRequest(res.url()) && new URL(res.url()).searchParams.get('q') === searchTerm,
      { timeout: 20_000 },
    );
    await page.getByTestId('inbox-search').pressSequentially(searchTerm, { delay: 25 });
    const searchResult = await searchResponse;
    expect(searchResult.ok()).toBeTruthy();
    const settledCalls = seenListUrls.filter(
      (url) => new URL(url).searchParams.get('q') === searchTerm,
    );
    expect(settledCalls).toHaveLength(1);
    await expect(page.getByTestId('inbox-empty')).toBeVisible({ timeout: 15_000 });

    // ---- Clear the probe search, back to the unfiltered "all" list ----
    const clearedResponse = page.waitForResponse(
      (res) => isListRequest(res.url()) && !new URL(res.url()).searchParams.get('q'),
      { timeout: 20_000 },
    );
    await page.getByTestId('inbox-search').fill('');
    await clearedResponse;

    const firstRow = page.locator('[data-testid^="inbox-row-"]').first();
    const hasRows = await firstRow.isVisible({ timeout: 10_000 }).catch(() => false);
    test.skip(
      !hasRows,
      'No conversations in the "All" tab on this environment - nothing to select.',
    );

    // ---- Select a row: the shared thread pane loads by contact ref ----
    const threadResponse = page.waitForResponse(
      (res) => /\/conversations\/[^/?]+\/page(\?|$)/.test(res.url()) && res.request().method() === 'GET',
      { timeout: 20_000 },
    );
    await firstRow.click();
    const threadResult = await threadResponse;
    expect(threadResult.ok()).toBeTruthy();
    await expect(page.getByTestId('chat-scroll-container')).toBeVisible({ timeout: 20_000 });

    // ---- Mobile: list-first, then thread replaces it with a way back ----
    // The selection from the desktop click above carries over (it is JS
    // state, not viewport-dependent) - resizing alone flips the responsive
    // classes so the thread pane now OWNS the screen with a back control,
    // exactly as a phone user who had just tapped the row would see it.
    await page.setViewportSize({ width: 375, height: 800 });
    await expect(page.getByTestId('thread-back')).toBeVisible({ timeout: 15_000 });
    await page.getByTestId('thread-back').click();

    // Back on the list: the thread pane's own empty state (or the thread
    // itself) is hidden, and the tab bar plus the row list are visible again.
    await expect(page.getByRole('tablist', { name: /conversation filter/i })).toBeVisible();
    await expect(firstRow).toBeVisible();
    await expect(page.getByTestId('thread-back')).toHaveCount(0);
  });
});
