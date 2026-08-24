/**
 * AI Assistant Prompt Registry (M1) end-to-end - FE→BE→DB round-trip.
 *
 * UAC F1-F4/F8: an admin edits a prompt, saves a new immutable version, and
 * publishes it (moves the `production` label) - all without a redeploy. Asserts
 * the FE hit the real backend routes:
 *   GET  /api/v1/system/ai-assistant/prompts
 *   GET  /api/v1/system/ai-assistant/prompts/{name}/versions
 *   POST /api/v1/system/ai-assistant/prompts/{name}/versions   (save)
 *   POST /api/v1/system/ai-assistant/prompts/{name}/labels      (publish)
 *
 * ALWAYS sidebar-navigate (feedback_playwright_via_sidebar), never deep-link.
 *
 * Required env (spec skipped otherwise):
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD  (set in BE .env)
 * The user needs `system.ai_assistant_settings.edit`.
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

async function navigateToPrompts(page: Page) {
  await page.getByRole('button', { name: /system management/i }).first().click();
  await page.getByRole('button', { name: /^ai assistant$/i }).first().click();
  await page.getByRole('link', { name: /^prompts$/i }).first().click();
  await expect(page.getByRole('heading', { name: /ai assistant prompts/i })).toBeVisible({
    timeout: 20_000,
  });
}

test.describe('AI prompt registry', () => {
  test('edit → save new version → publish moves production, via real API', async ({ page }) => {
    await login(page);
    await navigateToPrompts(page);

    // Open the reformulator detail page from the list.
    await page.getByTestId('prompt-link-reformulator').click();
    await expect(page.getByRole('heading', { name: 'reformulator' })).toBeVisible({ timeout: 20_000 });

    // Edit the template - keep the required {{current_date}} var so save is not
    // hard-blocked. Append a detectable marker line.
    const editor = page.getByTestId('prompt-editor');
    await expect(editor).toBeVisible();
    const marker = `E2E marker ${Date.now()}`;
    const current = await editor.inputValue();
    await editor.fill(`${current}\n${marker}`);

    await page.getByTestId('commit-message').fill('e2e: append marker line');

    const saveResp = page.waitForResponse(
      (r) =>
        /\/ai-assistant\/prompts\/reformulator\/versions$/.test(r.url()) && r.request().method() === 'POST',
    );
    await page.getByTestId('save-version').click();
    const saved = await saveResp;
    expect(saved.status()).toBe(201);
    const savedBody = await saved.json();
    const newVersion: number = savedBody.version;
    expect(newVersion).toBeGreaterThan(1);

    // The new version row should appear in history.
    await expect(page.getByTestId(`version-row-${newVersion}`)).toBeVisible({ timeout: 20_000 });

    // Publish the new version to production.
    await page.getByTestId(`publish-production-${newVersion}`).click();
    await expect(page.getByRole('alertdialog')).toBeVisible();
    await expect(
      page.getByText(new RegExp(`Publish reformulator v${newVersion} to production`, 'i')),
    ).toBeVisible();

    const labelResp = page.waitForResponse(
      (r) => /\/ai-assistant\/prompts\/reformulator\/labels$/.test(r.url()) && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /publish to production/i }).click();
    const labelled = await labelResp;
    expect(labelled.status()).toBe(200);
    const labelBody = await labelled.json();
    expect(labelBody.labels.production).toBe(newVersion);

    // The production badge now sits on the new version row.
    await expect(
      page.getByTestId(`version-row-${newVersion}`).getByText(/production/i),
    ).toBeVisible({ timeout: 20_000 });
  });
});
