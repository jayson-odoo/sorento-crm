/**
 * Ticket internal comment with @mention (PLAN-conversation-intervention-
 * tickets.md slice S4.3, UAC AC-L1). My Pending -> first open intervention
 * ticket -> switch composer to Comment mode -> type "@" -> pick a user from
 * the typeahead -> add the note -> assert `POST .../comments` fired and
 * `.../ticket/send` never did (a note must never reach the contact) -> the
 * amber note bubble renders with the text.
 *
 * Same seeding constraint as intervention-ticket-round-trip.spec.ts: tickets
 * are created only by the n8n sub-human-intervention flow, so this spec finds
 * an already-open ticket assigned to the test account and skips gracefully
 * with a clear message when none exists.
 *
 * Env (test skipped without EMAIL/PASSWORD):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD
 *
 * Cleanup: the CRM has no delete endpoint for `conversation_ticket_comments`
 * (comments are an append-only audit trail per AC-L1/L2 - deleting one would
 * also have to un-mirror it from Respond's own comment thread, which has no
 * API for that either). The note is marker-prefixed (`E2E-P4-`) and reads as
 * an internal-only annotation, never delivered to the contact - documented
 * here as accepted residue rather than silently skipped.
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_* env vars to run this spec.');

const MARKER = 'E2E-P4-';
const NOTE_TEXT = `${MARKER}internal note ${Date.now().toString(36)}`;

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

test.describe('Ticket internal note with @mention (AC-L1)', () => {
  test('comment mode posts a note, never a message to the contact', async ({ page }) => {
    await login(page);

    const found = await openAnOpenTicket(page);
    test.skip(
      !found,
      'No open intervention ticket assigned to this account - seed one via the ' +
        'sub-human-intervention n8n flow (or POST .../integration) before running.',
    );

    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();

    // Track every request while the note goes out - the negative assertion
    // (never .../ticket/send) has to be a positive capture, not an absence of
    // a single waitForResponse call.
    const requestUrls: string[] = [];
    page.on('request', (req) => requestUrls.push(req.url()));

    // ---- Switch to Comment mode ----
    await drawer.getByTestId('composer-mode-comment').click();
    const composer = drawer.getByTestId('internal-comment-composer');
    await expect(composer).toBeVisible({ timeout: 10_000 });

    // ---- "@" opens the mention typeahead; pick the first suggestion ----
    const input = drawer.getByTestId('internal-comment-input');
    await input.fill('@');
    const typeahead = drawer.getByTestId('mention-typeahead');
    await expect(typeahead).toBeVisible({ timeout: 10_000 });
    const firstOption = typeahead.getByRole('option').first();
    await expect(firstOption).toBeVisible({ timeout: 10_000 });
    const mentionedName = (await firstOption.textContent())?.trim() ?? '';
    await firstOption.click();

    // The mention inserted "@Name " - append the marker text after it.
    await input.pressSequentially(NOTE_TEXT, { delay: 5 });
    await expect(input).toHaveValue(new RegExp(`@.*${NOTE_TEXT}`));

    // ---- Submit ----
    const commentResponse = page.waitForResponse(
      (res) => /\/comments$/.test(new URL(res.url()).pathname) && res.request().method() === 'POST',
      { timeout: 20_000 },
    );
    await drawer.getByRole('button', { name: /^add note$/i }).click();
    const commentResult = await commentResponse;
    expect(commentResult.ok()).toBeTruthy();
    const commentBody = await commentResult.json();
    expect(commentBody.body as string).toContain(NOTE_TEXT);

    // ---- Never a send to the contact ----
    expect(requestUrls.some((url) => url.includes('/ticket/send'))).toBe(false);

    // ---- Amber note bubble renders with the text ----
    const noteBubble = drawer.getByTestId('chat-internal-note').filter({ hasText: NOTE_TEXT });
    await expect(noteBubble.first()).toBeVisible({ timeout: 15_000 });

    if (mentionedName) {
      expect((commentBody.mentioned_names as string[] | undefined)?.length ?? 0).toBeGreaterThan(0);
    }
  });
});
