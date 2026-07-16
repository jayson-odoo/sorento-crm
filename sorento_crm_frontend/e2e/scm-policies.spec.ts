/**
 * SCM Policy Configuration e2e — FE → BE → DB round-trip against the real
 * `scm` policy API. Exercises the reorder-policy CRUD + the resolution preview.
 *
 * Run against a running stack (FE :3000 + BE :8005 with the `scm` module
 * enabled for the tenant and the M0/M3 seed applied; worker NOT required):
 *
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   REQUEST_BATCH_E2E_EMAIL=admin@example.com \
 *   REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/scm-policies.spec.ts
 *
 * Credentials live in the frontend .env as REQUEST_BATCH_E2E_* (reused across the
 * SCM/e2e specs). Skips automatically when they aren't set so local dev isn't
 * blocked. Navigation ALWAYS goes through the sidebar (never a deep URL) so a
 * broken menu gate (moduleKey / permission) fails the test (AC-NAV-1).
 *
 * A product_class override is used for the create flow: categories are few, so
 * the SearchableSelect (client-filtered, first-100 cap) reliably lists one — the
 * SKU picker's 100-cap would be flaky here. Any listed product is fine for the
 * resolve step.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the SCM policies flow');

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

/**
 * Confirm the Supply Chain sidebar group + leaf render (catches missing-entry /
 * wrong-moduleKey / permission-gating bugs — AC-NAV-1), then navigate via the
 * leaf's resolved href. Clicking the <Link> directly hangs: the protected layout
 * fires a localhost:7242 ingest fetch that holds the page in a pre-load state and
 * intercepts Playwright's click auto-wait (established repo workaround).
 */
async function openScmLeaf(page: Page, leaf: RegExp) {
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: /supply chain/i }).first();
  await expect(group).toBeVisible({ timeout: 20_000 });
  const link = page.getByRole('link', { name: leaf }).first();
  // Expand the accordion group. A bounded real click dispatches the toggle
  // events during its action phase; only the post-action stability wait hangs on
  // the localhost:7242 ingest fetch, so we swallow that timeout and re-check.
  for (let i = 0; i < 6 && (await link.count()) === 0; i++) {
    await group.click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(400);
  }
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  if (!href) throw new Error(`Sidebar link "${leaf}" has no href`);
  await page.goto(href, { waitUntil: 'commit' });
}

/** The single SearchableSelect popover that is currently open. */
function openPopover(page: Page) {
  return page.locator('[data-slot="popover-content"][data-state="open"]');
}

/**
 * Pick a value in a SearchableSelect identified by its current trigger text,
 * within `root` (the modal or the page). Options are scoped to the OPEN popover
 * — a just-closed SearchableSelect keeps its content mounted, so an unscoped
 * `getByRole('option')` would leak the previous select's options.
 */
async function chooseInSearchable(
  page: Page,
  root: ReturnType<Page['getByRole']> | Page,
  triggerName: RegExp,
  optionName?: RegExp,
) {
  await (root as Page).getByRole('button', { name: triggerName }).first().click();
  const pop = openPopover(page);
  await expect(pop).toBeVisible({ timeout: 10_000 });
  const option = optionName ? pop.getByRole('option', { name: optionName }) : pop.getByRole('option');
  await expect(option.first()).toBeVisible({ timeout: 10_000 });
  const label = (await option.first().locator('span').first().textContent())?.trim() ?? '';
  await option.first().click();
  return label;
}

test('policies: sidebar → create/edit/delete a product_class override + resolve', async ({ page }) => {
  const calls: string[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (u.includes('/api/v1/scm/policies')) calls.push(`${r.method()} ${new URL(u).pathname}`);
  });
  const seen = (method: string, pathRe: RegExp) =>
    calls.some((c) => c.startsWith(method) && pathRe.test(c));

  await login(page);

  // AC-NAV-1 — the Policies leaf renders under Supply Chain and routes.
  await openScmLeaf(page, /^Policies$/);
  await page.waitForURL(/\/scm\/policies$/);

  // Reorder-policies grid loads (list GET).
  await expect
    .poll(() => seen('GET', /\/scm\/policies$/), { timeout: 15_000 })
    .toBeTruthy();
  await expect(page.getByText(/most-specific-first/i)).toBeVisible();

  // ── Create a product_class override ──────────────────────────────────────
  const editDialog = page.getByRole('dialog', { name: /reorder policy/i });
  await page.getByRole('button', { name: /Add policy/i }).click();
  await expect(editDialog).toBeVisible();

  // Switch scope SKU → Product class.
  await chooseInSearchable(page, editDialog, /^SKU$/, /Product class/);

  // Open the class picker and choose a category that has NO existing active
  // policy (avoids the AC-VAL-8 uniqueness 409 on re-runs / seeded rows).
  await editDialog.getByRole('button', { name: /Search a product class/ }).click();
  const options = openPopover(page).getByRole('option');
  await expect(options.first()).toBeVisible({ timeout: 10_000 });
  const optionCount = await options.count();
  let className = '';
  for (let i = 0; i < optionCount; i++) {
    const label = (await options.nth(i).locator('span').first().textContent())?.trim() ?? '';
    if (!label) continue;
    if ((await page.getByRole('row').filter({ hasText: label }).count()) === 0) {
      className = label;
      await options.nth(i).click();
      break;
    }
  }
  expect(className, 'expected a product class with no existing policy').not.toBe('');

  // Submit (defaults for the numeric fields are valid).
  await editDialog.getByRole('button', { name: /^Add policy$/ }).click();

  await expect
    .poll(() => seen('POST', /\/scm\/policies$/), { timeout: 15_000 })
    .toBeTruthy();
  await expect(editDialog).toBeHidden({ timeout: 10_000 });
  // New row appears with the class label.
  await expect(page.getByText(className).first()).toBeVisible({ timeout: 10_000 });

  // ── Edit the override ────────────────────────────────────────────────────
  const row = page.getByRole('row').filter({ hasText: className }).first();
  await row.getByRole('button', { name: /Edit policy/i }).click();
  await expect(editDialog).toBeVisible();
  // Bump priority then save.
  const priority = editDialog.locator('input[type="number"]').last();
  await priority.fill('25');
  await editDialog.getByRole('button', { name: /Save changes/i }).click();
  await expect
    .poll(() => seen('PUT', /\/scm\/policies\//), { timeout: 15_000 })
    .toBeTruthy();
  await expect(editDialog).toBeHidden({ timeout: 10_000 });

  // ── Delete via the AlertDialog confirm ───────────────────────────────────
  await page.getByRole('row').filter({ hasText: className }).first()
    .getByRole('button', { name: /Delete policy/i }).click();
  const confirm = page.getByRole('dialog', { name: /confirm delete/i });
  await expect(confirm.getByText('Confirm delete')).toBeVisible();
  await expect(confirm.getByText(/This action cannot be undone/i)).toBeVisible();
  await confirm.getByRole('button', { name: /^Delete$/ }).click();
  await expect
    .poll(() => seen('DELETE', /\/scm\/policies\//), { timeout: 15_000 })
    .toBeTruthy();
  await expect(page.getByRole('row').filter({ hasText: className })).toHaveCount(0, { timeout: 10_000 });

  // ── Resolution preview ───────────────────────────────────────────────────
  await page.getByRole('tab', { name: /Resolution preview/i }).click();
  await chooseInSearchable(page, page, /Search a product/);
  await page.getByRole('button', { name: /^Resolve$/ }).click();
  await expect
    .poll(() => seen('GET', /\/scm\/policies\/resolve/), { timeout: 15_000 })
    .toBeTruthy();
  // Winner + chain render.
  await expect(page.getByText('Resolution chain')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('Winner').first()).toBeVisible();
});
