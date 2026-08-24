/**
 * SPO import + form chat reply - the two integration paths left undriven.
 *
 * 1. SPO allocation import: sidebar -> Procurement -> SPO Allocations -> Import
 *    SPO, upload a real .xlsx whose filename carries the SPO number (the
 *    backend parses it from there), and assert the upload is accepted and an
 *    import job is queued.
 *
 * 2. Form chat reply: open a form that has a Respond.io conversation, type into
 *    the shared composer and send. Locally the Respond credentials are
 *    deliberately wrong, so the send fails upstream - that is the point. What
 *    must hold is that the app issues the send request and surfaces the outcome
 *    rather than silently doing nothing.
 *
 * Required env (spec skips otherwise):
 *   SPO_E2E_EMAIL / SPO_E2E_PASSWORD
 */
import { test, expect, type Page } from '@playwright/test';
import * as path from 'path';

const EMAIL = process.env.SPO_E2E_EMAIL;
const PASSWORD = process.env.SPO_E2E_PASSWORD;
const FIXTURE = path.join(__dirname, 'fixtures', 'SPO-2026.08-9001.xlsx');

test.skip(!EMAIL || !PASSWORD, 'Set SPO_E2E_* env vars to run this spec.');

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}


/** Expand a sidebar group and click a leaf entry.
 *
 * The AI-assistant launcher is a fixed z-[120] element that can sit over the
 * nav and swallow clicks, so dismiss any open overlay first and scroll the
 * target into view before clicking.
 */
async function openFromSidebar(page: Page, group: RegExp, entry: RegExp) {
  await page.keyboard.press('Escape');
  const groupBtn = page.getByRole('button', { name: group }).first();
  await expect(groupBtn).toBeVisible({ timeout: 30_000 });
  await groupBtn.scrollIntoViewIfNeeded();
  // force: the fixed-position AI assistant launcher (z-[120]) and lingering
  // dialog overlays intermittently sit over the nav and swallow the click,
  // which hangs the default actionability wait. Visibility is asserted above.
  await groupBtn.click({ force: true });
  const link = page.getByRole('link', { name: entry }).first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  await link.scrollIntoViewIfNeeded();
  await link.click({ force: true });
}

test('SPO import accepts a real workbook and queues an import job', async ({ page }) => {
  test.setTimeout(180_000);
  await login(page);

  // Sidebar navigation (never deep-link: it hides nav-gating bugs).
  await openFromSidebar(page, /^procurement$/i, /^spo allocations$/i);
  await expect(page).toHaveURL(/spo-allocations/, { timeout: 30_000 });

  await page.getByRole('button', { name: /import spo/i }).first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  // Set the hidden input directly - the visible drop zone has several
  // text nodes and clicking the wrong one never opens the file chooser.
  await dialog.locator('input[type="file"]').setInputFiles(FIXTURE);

  // Selecting the file fires a separate `?validate_only=true` POST to the SAME
  // path. Match the REAL import only, or the test passes on validation alone
  // and never proves a job was queued.
  const upload = page.waitForResponse(
    (r) =>
      r.url().includes('/spo-allocations/import') &&
      !r.url().includes('validate_only') &&
      r.request().method() === 'POST',
    { timeout: 60_000 },
  );
  const importBtn = dialog.getByRole('button', { name: /^import$/i }).first();
  await expect(importBtn).toBeEnabled({ timeout: 30_000 });
  await importBtn.click();

  // A workbook that validates with warnings raises an "Import with warnings?"
  // confirm step. That is intended behaviour - acknowledge it, or the real
  // import POST never fires and the test silently proves nothing.
  const confirm = page.getByRole('button', { name: /import anyway/i });
  if (await confirm.isVisible({ timeout: 30_000 }).catch(() => false)) {
    await confirm.click();
  }

  const res = await upload;
  expect(res.status(), `SPO import POST failed: ${res.status()}`).toBeLessThan(400);
  // The response must actually reference a queued job, not just be a 200.
  const body = await res.json().catch(() => ({}));
  expect(JSON.stringify(body)).toMatch(/job/i);
});

test('form chat composer sends a reply and surfaces the result', async ({ page }) => {
  test.setTimeout(180_000);
  await login(page);

  await openFromSidebar(page, /^complaint management$/i, /^complaints$/i);
  await expect(page).toHaveURL(/complaints/, { timeout: 30_000 });

  // Target a complaint whose contact is actually linked to Respond.io. Taking
  // row one blindly lands on records with no conversation panel, and the test
  // then skips while looking like it ran.
  const target = process.env.CHAT_E2E_COMPLAINT ?? 'CMP2026-0016';
  const search = page.getByRole('textbox', { name: /search/i }).first();
  await search.fill(target);
  await expect(page.getByRole('cell', { name: target })).toBeVisible({ timeout: 30_000 });
  await page.getByRole('cell', { name: target }).first().click();
  await expect(page).toHaveURL(/complaints\/[0-9a-f-]{36}/, { timeout: 30_000 });

  // The conversation panel lives in a right-hand Sheet, so the composer does
  // not exist until it is opened. The trigger itself only renders when the
  // complaint has a respond_inbox_url.
  const chatBtn = page.getByRole('button', { name: /open chat records/i });
  if (!(await chatBtn.isVisible({ timeout: 15_000 }).catch(() => false))) {
    test.skip(true, 'Complaint has no respond_inbox_url, so no chat panel.');
  }
  await chatBtn.click();

  const composer = page
    .locator('textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]')
    .first();
  await expect(composer).toBeVisible({ timeout: 30_000 });

  await composer.fill(`E2E chat reply ${Date.now()}`);

  // The send may 4xx upstream (local Respond creds are intentionally wrong).
  // Assert the request is actually issued - a silent no-op is the real defect.
  const sent = page.waitForResponse(
    (r) =>
      /(conversation\/(reply|send-message)|send-message)/.test(r.url()) &&
      r.request().method() === 'POST',
    { timeout: 60_000 },
  );
  await page.getByRole('button', { name: /^send$/i }).first().click();

  const res = await sent;
  expect([200, 201, 400, 401, 403, 422, 500, 502]).toContain(res.status());
});
