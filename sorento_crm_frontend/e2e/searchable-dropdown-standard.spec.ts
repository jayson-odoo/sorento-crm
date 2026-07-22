/**
 * Searchable Dropdown Standard — browser regression cover.
 *
 * Run:
 *   PORTAL_E2E_BASE_URL=http://localhost:3100 \
 *   REQUEST_BATCH_E2E_EMAIL=... REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/searchable-dropdown-standard.spec.ts
 *
 * Credentials live in the frontend .env as REQUEST_BATCH_E2E_* (shared with the other
 * specs). Skips automatically when unset so local dev isn't blocked.
 *
 * Why a spec rather than ad-hoc clicking: this standard has already produced one bug that
 * passed every DOM assertion and was only visible on screen — a popover inside a dialog
 * flipped upward and was clipped by the dialog's overflow, while getBoundingClientRect
 * happily reported it on-screen. So the clipping check here asserts real paint geometry
 * (elementFromPoint), not layout coordinates.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the dropdown spec');

const TRIGGER = '[data-slot="searchable-select-trigger"]';
const MULTI_TRIGGER = '[data-slot="searchable-multi-select-trigger"]';
const SELECT_ALL = '[data-slot="searchable-multi-select-all"]';

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

const searchBox = (page: Page) => page.locator('input[cmdk-input]');
const optionTexts = (page: Page) => page.getByRole('option').allTextContents();

test.beforeEach(async ({ page }) => {
  await login(page);
});

test('static filtering is all-tokens substring, not fuzzy subsequence', async ({ page }) => {
  await page.goto('/user-management/settings');

  const timezone = page.locator(TRIGGER).filter({ hasText: /timezone|GMT/i }).first();
  await expect(timezone).toBeVisible({ timeout: 20_000 });
  await timezone.click();

  await searchBox(page).fill('kuala');
  await expect(page.getByRole('option')).toHaveCount(1);
  expect((await optionTexts(page))[0]).toContain('Kuala Lumpur');

  // Every token must match: "asia kuala" still hits, "asia dakota" cannot.
  await searchBox(page).fill('asia kuala');
  await expect(page.getByRole('option')).toHaveCount(1);
  await searchBox(page).fill('asia dakota');
  await expect(page.getByRole('option')).toHaveCount(0);
});

test('saved values resolve into triggers on the settings page', async ({ page }) => {
  await page.goto('/user-management/settings');
  await expect(page.locator(TRIGGER).first()).toBeVisible({ timeout: 20_000 });

  const labels = await page.locator(TRIGGER).allTextContents();
  // Language / currency / currency-format all persist a value; none may render blank.
  expect(labels.length).toBeGreaterThanOrEqual(4);
  expect(labels.some((l) => /English/i.test(l))).toBe(true);
  expect(labels.some((l) => /MYR/i.test(l))).toBe(true);
});

test('renderTrigger keeps the icon-only trigger and still opens the menu', async ({ page }) => {
  await page.goto('/user-management/settings/system-health');

  // The notify pickers hang off compact icon buttons, not select boxes: exactly one default
  // select trigger exists on this page (the latency percentile), and the notify controls are
  // icon buttons rendered through renderTrigger.
  const rolesTrigger = page.getByTestId('notify-roles-trigger');
  await expect(rolesTrigger).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('notify-users-trigger')).toBeVisible();
  await expect(page.locator(TRIGGER)).toHaveCount(1);

  // Still a real dropdown underneath.
  await rolesTrigger.click();
  await expect(searchBox(page)).toBeVisible();
  await expect(page.getByRole('option').first()).toBeVisible();
});

test('multi-select offers select all, and it respects the active search', async ({ page }) => {
  await page.goto('/user-management/settings/system-health');

  await page.getByTestId('notify-roles-trigger').click();

  const selectAll = page.locator(SELECT_ALL);
  await expect(selectAll).toBeVisible({ timeout: 10_000 });
  await expect(selectAll).toContainText(/Select all \(\d+\)/);

  // Filtering rewords it, so the control can only ever act on what is on screen.
  await searchBox(page).fill('a');
  await expect(selectAll).toContainText(/Select \d+ matching|Clear \d+ matching/);
});

test('a dropdown inside a dialog is not clipped when its menu flips upward', async ({ page }) => {
  // The config viewport is 1400x1600 — tall enough that the menu always opens downward and
  // never exercises the flip. Shrink it so the dialog sits low and the Column menu is forced
  // upward, which is the case that was clipped.
  await page.goto('/master-data-management/lookup-sets', { waitUntil: 'domcontentloaded' });
  await page.setViewportSize({ width: 1280, height: 560 });

  const row = page.getByRole('cell').filter({ hasText: /procurement_sponsor_subject/ }).first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.click();

  await page.getByRole('button', { name: /add binding/i }).click();
  const table = page.locator(TRIGGER).filter({ hasText: /select table/i }).first();
  await table.click();
  await searchBox(page).fill('purchase requests');
  await page.getByRole('option').filter({ hasText: /^Purchase Requests$/ }).first().click();

  // The Column menu is the one that flips upward inside the dialog.
  await page.locator(TRIGGER).filter({ hasText: /select column/i }).first().click();
  const input = searchBox(page);
  await expect(input).toBeVisible();

  // Guard the guard: if the menu ever stops flipping, this test would pass without
  // covering anything, so assert the precondition explicitly.
  const side = await page
    .locator('[data-slot="popover-content"][data-state="open"]')
    .getAttribute('data-side');
  expect(side).toBe('top');

  // Actually painted, not merely laid out: whatever is at the input's centre must be the
  // input itself (or inside it). A clipped popover fails here while passing a rect check.
  const painted = await input.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && (hit === el || el.contains(hit) || hit.contains(el));
  });
  expect(painted).toBe(true);
});
