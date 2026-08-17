/**
 * Resolve stays open in a Resolved state (PLAN-conversation-intervention-
 * tickets.md slice S4.5, UAC AC-M1 / AC-M2). Drawer -> Resolve (AlertDialog
 * confirm) -> the drawer stays open with the Resolved badge, a disabled
 * composer, and a "View history" link scoped to this contact; the resolve
 * hits `POST .../resolve`.
 *
 * Resolve is a REAL, irreversible action on a REAL contact's ticket (it stops
 * the SLA clock and, once "no other open sibling" is true, closes the
 * Respond.io conversation). There is no UI or ordinary-session API path to
 * create a throwaway intervention ticket (create_tracking's `/integration`
 * route needs a real `(agent_code, team_set_code)` pair that resolves to a
 * live SLA policy - not something this spec can safely invent). So this spec
 * ONLY runs against a ticket explicitly nominated for it:
 *
 *   E2E_INTERVENTION_TICKET_ID       - the tracking id to resolve (required)
 *
 * The nominated ticket must currently be open and visible in the signed-in
 * account's "My Pending" widget. The spec verifies the id via the drawer's
 * own `GET .../{id}/ticket` call before touching anything - it will NOT
 * resolve a ticket it cannot positively identify, and skips with a clear
 * message when the id is absent or not found in the widget.
 *
 * Env (test skipped without EMAIL/PASSWORD or the ticket id):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD
 *   E2E_INTERVENTION_TICKET_ID
 *
 * No cleanup: a resolve cannot be undone by design (AC-C3), which is exactly
 * why this spec is gated the way it is.
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;
const TICKET_ID = process.env.E2E_INTERVENTION_TICKET_ID;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_* env vars to run this spec.');
test.skip(
  !TICKET_ID,
  'Set E2E_INTERVENTION_TICKET_ID to a ticket you specifically created for this ' +
    'destructive resolve test - this spec never guesses a ticket to resolve.',
);

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
 * Opens each "My Pending" row until the drawer's own `GET .../{id}/ticket`
 * confirms it is the NOMINATED ticket. Never opens on a positive match by
 * accident: a row that turns out to be someone else's ticket, or not a
 * ticket row at all, is backed out of before the next attempt.
 */
async function openNominatedTicket(page: Page, ticketId: string): Promise<boolean> {
  await waitForMyPendingWidget(page);
  const rows = page.locator('ul.divide-y > li');
  const rowCount = await rows.count();
  for (let i = 0; i < rowCount; i += 1) {
    const ticketDetailResponse = page
      .waitForResponse(
        (res) =>
          new RegExp(`/conversation-sla-tracking/[0-9a-f-]{36}/ticket$`).test(
            new URL(res.url()).pathname,
          ) && res.request().method() === 'GET',
        { timeout: 5_000 },
      )
      .catch(() => null);
    await rows.nth(i).getByRole('button').first().click();
    const result = await ticketDetailResponse;
    if (result) {
      const openedId = new URL(result.url()).pathname.split('/').slice(-2, -1)[0];
      if (openedId === ticketId) return true;
    }
    // Not the nominated ticket (or not a ticket row at all) - back out.
    if (page.url() !== (await page.evaluate(() => window.location.origin)) + '/') {
      await page.goto('/');
      await waitForMyPendingWidget(page);
    }
  }
  return false;
}

test.describe('Ticket resolve stays open (AC-M1 / AC-M2)', () => {
  test('resolve keeps the drawer open in a Resolved state with a scoped history link', async ({
    page,
  }) => {
    await login(page);

    const found = await openNominatedTicket(page, TICKET_ID!);
    test.skip(
      !found,
      `E2E_INTERVENTION_TICKET_ID=${TICKET_ID} was not found open in this account's ` +
        'My Pending widget - nothing was touched.',
    );

    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByTestId('ticket-resolved-badge')).toHaveCount(0);

    // ---- Resolve: AlertDialog confirm, standard "cannot be undone" copy ----
    await drawer.getByRole('button', { name: /resolve ticket/i }).click();
    const confirmDialog = page.getByRole('alertdialog');
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog.getByText(/mark as resolved/i)).toBeVisible();
    await expect(confirmDialog.getByText(/cannot be undone/i)).toBeVisible();

    const resolveResponse = page.waitForResponse(
      (res) => /\/resolve$/.test(new URL(res.url()).pathname) && res.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await confirmDialog.getByRole('button', { name: /^confirm$/i }).click();
    const resolveResult = await resolveResponse;
    expect(resolveResult.ok()).toBeTruthy();

    // ---- Drawer stays open (AC-M1): NOT the old close-on-resolve behavior ----
    await expect(confirmDialog).not.toBeVisible({ timeout: 10_000 });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByTestId('ticket-resolved-badge')).toBeVisible({ timeout: 15_000 });
    await expect(drawer.getByTestId('ticket-resolved-at')).toBeVisible();

    // Composer disabled with the resolved reason, in both modes.
    await expect(drawer.getByText('This ticket is resolved.')).toBeVisible();
    await drawer.getByTestId('composer-mode-comment').click();
    await expect(drawer.getByText('This ticket is resolved.').first()).toBeVisible();

    // ---- AC-M2: "View history", scoped to this contact ----
    const historyLink = drawer.getByTestId('ticket-history-link');
    await expect(historyLink).toBeVisible();
    const href = await historyLink.getAttribute('href');
    expect(href).toContain('/sla-management/conversation-sla-tracking');
    expect(href).toMatch(/[?&]contact=/);
  });
});
