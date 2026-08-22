/**
 * Ticket thread in-conversation search + scroll-back (PLAN-conversation-
 * intervention-tickets.md slice S4.8, UAC AC-L7 / AC-L8).
 *
 * My Pending -> first open intervention ticket -> open the search icon in the
 * chat header -> type a term -> assert `GET .../conversation/search?q=` fired
 * and the match counter renders -> Enter/Shift+Enter step through matches ->
 * Escape closes the bar. Then scroll the thread to the top and assert either
 * `GET .../conversation/page?before=` fires (more history to load) or
 * "Beginning of this conversation" already shows (short thread).
 *
 * Intervention tickets are created only by the n8n sub-human-intervention flow
 * (or POST .../integration) - there is no UI path to seed one, so this spec
 * finds any ticket already open and assigned to the test account and skips
 * gracefully with a clear message when none exists, same as
 * intervention-ticket-round-trip.spec.ts.
 *
 * Env (test skipped without EMAIL/PASSWORD):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD
 *
 * This spec is READ-ONLY on the ticket (search + scroll-back never mutate a
 * tracker), so no cleanup is required.
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
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

async function waitForMyPendingWidget(page: Page) {
  await expect(page.getByRole('heading', { name: /my pending tasks/i })).toBeVisible({
    timeout: 20_000,
  });
}

/**
 * Same detection strategy as intervention-ticket-round-trip.spec.ts: a ticket
 * row is the only "My Pending" row that opens an in-place drawer with a
 * "Resolve ticket" affordance.
 */
async function openAnOpenTicket(page: Page): Promise<boolean> {
  await waitForMyPendingWidget(page);
  const rows = page.locator('ul.divide-y > li');
  const rowCount = await rows.count();
  for (let i = 0; i < rowCount; i += 1) {
    await rows.nth(i).getByRole('button').first().click();
    const drawer = page.getByRole('dialog');
    const resolveButton = drawer.getByRole('button', { name: /resolve ticket/i });
    if (await resolveButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
      return true;
    }
    if (page.url() !== (await page.evaluate(() => window.location.origin)) + '/') {
      await page.goto('/');
      await waitForMyPendingWidget(page);
    }
  }
  return false;
}

test.describe('Ticket thread search + scroll-back (AC-L7 / AC-L8)', () => {
  test('search bar fires the search endpoint and renders a match counter; scroll-back loads history', async ({
    page,
  }) => {
    await login(page);

    const found = await openAnOpenTicket(page);
    test.skip(
      !found,
      'No open intervention ticket assigned to this account - seed one via the ' +
        'sub-human-intervention n8n flow (or POST .../integration) before running.',
    );

    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();

    // Wait for the thread itself to render before touching search/scroll -
    // the search icon and the scroll container only exist once it has loaded.
    const scrollContainer = drawer.getByTestId('chat-scroll-container');
    await expect(scrollContainer).toBeVisible({ timeout: 20_000 });

    // ---- Open search ----
    const searchIcon = drawer.getByRole('button', { name: /^search messages$/i });
    await expect(searchIcon).toBeVisible({ timeout: 10_000 });
    await searchIcon.click();

    const searchInput = drawer.getByRole('searchbox', { name: /search messages/i });
    await expect(searchInput).toBeVisible();

    // A short, common term - the goal is exercising the endpoint + counter,
    // not asserting a specific match count against unpredictable live data.
    const term = 'a';
    const searchResponse = page.waitForResponse(
      (res) =>
        /\/conversation\/search\?/.test(res.url()) &&
        new URL(res.url()).searchParams.get('q') === term &&
        res.request().method() === 'GET',
      { timeout: 20_000 },
    );
    await searchInput.fill(term);
    const searchResult = await searchResponse;
    expect(searchResult.ok()).toBeTruthy();

    const counter = drawer.getByTestId('conversation-search-counter');
    await expect(counter).toBeVisible({ timeout: 15_000 });
    const counterText = (await counter.textContent())?.trim() ?? '';

    if (counterText !== 'No results') {
      // "x / y" - navigation only makes sense with at least one match.
      await searchInput.press('Enter');
      await expect(counter).toBeVisible();
      await searchInput.press('Shift+Enter');
      await expect(counter).toBeVisible();
    } else {
      const prevButton = drawer.getByRole('button', { name: /previous match/i });
      const nextButton = drawer.getByRole('button', { name: /next match/i });
      await expect(prevButton).toBeDisabled();
      await expect(nextButton).toBeDisabled();
    }

    // ---- Escape closes the bar ----
    await searchInput.press('Escape');
    await expect(drawer.getByTestId('conversation-search-controls')).not.toBeVisible({
      timeout: 10_000,
    });
    await expect(searchIcon).toBeVisible();

    // ---- Scroll-back: either a page load fires, or the thread is already
    // short enough that we are already at the true start. ----
    const pageLoadResponse = page
      .waitForResponse(
        (res) => /\/conversation\/page\?.*before=/.test(res.url()) && res.request().method() === 'GET',
        { timeout: 8_000 },
      )
      .catch(() => null);

    await scrollContainer.evaluate((node) => {
      node.scrollTop = 0;
      node.dispatchEvent(new Event('scroll'));
    });

    const pageLoadResult = await pageLoadResponse;
    if (pageLoadResult) {
      expect(pageLoadResult.ok()).toBeTruthy();
    } else {
      await expect(drawer.getByTestId('chat-conversation-start')).toBeVisible({ timeout: 10_000 });
    }
  });
});
