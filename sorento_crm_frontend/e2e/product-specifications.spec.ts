/**
 * Product Specifications workbench end-to-end - FE→BE→DB round-trip.
 *
 * The thing worth testing here is the promise the screen makes: a specification can be
 * added, taught how to read itself, and tuned, WITHOUT a release. Hand-clicking through
 * it is how "Add a specification" stayed missing from the UI for a whole build while the
 * API endpoint sat there unused - nothing failed, because nothing was checking.
 *
 * Asserts the FE hit the real backend routes:
 *   GET   /api/v1/master-data/spec-registry
 *   POST  /api/v1/master-data/spec-registry                    (add a spec)
 *   PATCH /api/v1/master-data/spec-registry/{key}              (rules, preferences)
 *   GET   /api/v1/master-data/spec-registry/policy
 *   PATCH /api/v1/master-data/spec-registry/policy/{key}       (ranking)
 *   POST  /api/v1/master-data/product-specifications/preview-search
 *
 * ALWAYS sidebar-navigate (feedback_playwright_via_sidebar), never deep-link.
 *
 * Required env (spec skipped otherwise):
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD  (set in BE .env)
 * The user needs `master_data.spec_registry.edit`.
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_* env vars to run this spec.');

// Named so a failed run leaves something obviously disposable behind rather than a row
// somebody later mistakes for a real specification.
const SPEC_LABEL = 'ZZT e2e rough in';
const SPEC_KEY = 'zzt_e2e_rough_in';

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

async function navigateToSpecifications(page: Page) {
  await page.getByRole('button', { name: /product management/i }).first().click();
  await page.getByRole('link', { name: /product specifications/i }).first().click();
  await expect(page.getByRole('heading', { name: /product specifications/i })).toBeVisible({
    timeout: 20_000,
  });
}

test.describe('Product Specifications workbench', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await navigateToSpecifications(page);
  });

  test('the three jobs are reachable and named', async ({ page }) => {
    // The complaint that produced this layout was "I don't know where to click".
    await expect(page.getByRole('heading', { name: /try a customer phrase/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /specifications/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /ranking/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /catalogue/i })).toBeVisible();
  });

  test('a customer phrase returns products, and each links to its specs', async ({ page }) => {
    const preview = page.waitForResponse(
      (r) => r.url().includes('/product-specifications/preview-search') && r.status() === 200,
    );
    await page.locator('#spec-phrase').fill('stainless steel kitchen sink');
    await page.getByRole('button', { name: /^search$/i }).click();
    await preview;

    await expect(page.getByText(/what the customer would see/i)).toBeVisible();
    const first = page.locator('a[href*="?tab=specifications"]').first();
    await expect(first).toBeVisible();
    await expect(first).toContainText(/sink/i);
  });

  test('a specification can be added and taught to read itself, with no release', async ({
    page,
  }) => {
    await page.getByRole('tab', { name: /specifications/i }).click();

    // --- add it -----------------------------------------------------------
    await page.getByRole('button', { name: /add a specification/i }).click();
    await page.locator('#new-spec-label').fill(SPEC_LABEL);

    const created = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/v1/master-data/spec-registry') &&
        r.request().method() === 'POST' &&
        r.status() === 201,
    );
    await page.getByRole('button', { name: /^add specification$/i }).click();
    await created;

    // The key it will be known by, derived from the label.
    await expect(page.getByText(SPEC_KEY, { exact: false }).first()).toBeVisible();

    // --- teach it a rule --------------------------------------------------
    // A key with no rules reads nothing, so the editor opens straight away.
    await expect(page.getByText(/how this is read from a product/i)).toBeVisible();
    await page.getByRole('button', { name: /add a rule/i }).click();
    await page.getByPlaceholder('what to look for').last().fill('ROUGH IN 180');
    await page.getByPlaceholder('value').last().fill('180');

    const saved = page.waitForResponse(
      (r) =>
        r.url().includes(`/spec-registry/${SPEC_KEY}`) &&
        r.request().method() === 'PATCH' &&
        r.status() === 200,
    );
    await page.getByRole('button', { name: /^save$/i }).click();
    const response = await saved;

    const body = await response.json();
    expect(body.derivation_rules).toHaveLength(1);
    expect(body.derivation_rules[0]).toMatchObject({
      match: 'contains',
      pattern: 'ROUGH IN 180',
      value: '180',
    });
  });

  test('a bad rule is refused with a reason, not saved silently', async ({ page }) => {
    await page.getByRole('tab', { name: /specifications/i }).click();
    await page.locator('tr', { hasText: /^Material/ }).getByRole('button', { name: /edit/i }).click();

    await page.getByRole('button', { name: /add a rule/i }).click();
    // A rule with a pattern and no value cannot produce anything.
    await page.getByPlaceholder('what to look for').last().fill('SOMETHING');
    await page.getByRole('button', { name: /^save$/i }).click();

    await expect(page.getByText(/needs the value it should produce/i)).toBeVisible();
  });

  test('a ranking setting is editable and comes back changed', async ({ page }) => {
    await page.getByRole('tab', { name: /ranking/i }).click();
    await expect(page.getByText(/being discontinued costs/i)).toBeVisible();

    const row = page.locator('div', { hasText: /^Being discontinued costs/ }).last();
    const input = row.locator('input[type="number"]').first();
    const original = await input.inputValue();
    const next = original === '3' ? '2' : '3';

    const patched = page.waitForResponse(
      (r) =>
        r.url().includes('/spec-registry/policy/discontinued_penalty') &&
        r.request().method() === 'PATCH' &&
        r.status() === 200,
    );
    await input.fill(next);
    await row.getByRole('button', { name: /^save$/i }).click();
    const response = await patched;

    expect((await response.json()).value).toBe(Number(next));

    // Put it back, so the suite leaves the ranker where it found it.
    const restored = page.waitForResponse(
      (r) => r.url().includes('/spec-registry/policy/discontinued_penalty') && r.status() === 200,
    );
    await input.fill(original);
    await row.getByRole('button', { name: /^save$/i }).click();
    await restored;
  });

  test('the catalogue tab shows what each value was read from', async ({ page }) => {
    await page.getByRole('tab', { name: /catalogue/i }).click();
    await expect(page.getByText(/derived specifications/i)).toBeVisible();
  });
});
