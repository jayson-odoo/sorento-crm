/**
 * AI assistant bubble record-context end-to-end (Phase 2).
 *
 * Verifies that opening a complaint detail page registers the record into the
 * AI entity store (lib/aiEntityContext via <RecordEntityRegistrar/>), so that a
 * record-class question ("Why was this complaint rejected?") makes the backend
 * deterministic pre-route hit
 *   GET /api/v1/assistant/record-context/complaint/{id}
 * and renders a grounded assistant reply.
 *
 * The same record-context pre-route applies to the other AI-grounded detail
 * pages, which now also mount <RecordEntityRegistrar/>. Full coverage needs
 * login creds; the additional routes the bubble fires for those pages are:
 *   GET /api/v1/assistant/record-context/stock_inquiry/{id}
 *   GET /api/v1/assistant/record-context/purchase_request/{id}
 *   GET /api/v1/assistant/record-context/sponsorship_form/{id}
 * (sponsorship_form and purchase_request share a detail component but register
 * distinct entity_type strings - assert on the URL, not the component.)
 *
 * ALWAYS sidebar-navigate (project memory feedback_playwright_via_sidebar),
 * never deep-link to the detail page directly.
 *
 * Required env (spec is skipped otherwise):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD  (login creds; same
 *     vars used by the other complaint specs - set in the BE .env per memory)
 *
 * Assumes the logged-in user has the `system.ai_assistant_chat.use` permission
 * (the bubble does not render without it) and at least one complaint exists.
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

async function navigateToComplaints(page: Page) {
  await page.getByRole('button', { name: /complaint management/i }).first().click();
  await page.getByRole('link', { name: /^complaints$/i }).first().click();
  await expect(
    page.getByRole('heading', { name: /complaints/i }).first(),
  ).toBeVisible({ timeout: 20_000 });
}

test.describe('AI bubble record context', () => {
  test('asking about the open complaint hits record-context and renders a reply', async ({
    page,
  }) => {
    await login(page);
    await navigateToComplaints(page);

    // Open the first complaint row -> detail page registers {complaint, id}.
    const rows = page.locator('table tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 20_000 });
    await rows.first().click();
    await expect(page).toHaveURL(
      /complaint-management\/complaints\/[^/]+/,
      { timeout: 20_000 },
    );

    // Open the AI assistant bubble (floating button bottom-right).
    await page.getByRole('button', { name: /open ai assistant/i }).click();

    const promptInput = page.getByPlaceholder(/ask the assistant/i);
    await expect(promptInput).toBeVisible({ timeout: 20_000 });

    // The deterministic record-context pre-route should fire for the open record.
    const recordContextReq = page.waitForRequest(
      (req) =>
        /\/api\/v1\/assistant\/record-context\/complaint\//.test(req.url()),
      { timeout: 30_000 },
    );

    await promptInput.fill('Why was this complaint rejected?');
    // The send button is icon-only; submitting the form via Enter is robust.
    await promptInput.press('Enter');

    await recordContextReq;

    // An assistant reply renders (markdown bubble on the left).
    await expect(page.locator('.ai-markdown').first()).toBeVisible({
      timeout: 30_000,
    });
  });
});
