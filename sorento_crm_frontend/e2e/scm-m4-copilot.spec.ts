/**
 * SCM M4 Slice B — cash co-pilot decision → draft PO → confirm → GR e2e (AC-M4.15).
 * Full FE → BE → DB round-trip against the LIVE stack (FE :3000 + BE :8005 +
 * worker; `scm` module enabled, M0/M3/M4 seed applied + a completed run with
 * costed buys). Exercises the whole loop:
 *
 *   sidebar → Reorder Planning → open a completed run w/ costed buys
 *     → select-all funded → Actions → Accept (count-bearing confirm)
 *   sidebar → Purchase Orders → draft POs present + "Not on order"
 *     → select-all (all rows) → Actions → "Confirm N drafts" → confirm
 *     → drafts become PO-YYYY/MM-#### Active + On order (NO "NaN", NO "DRAFT")
 *     → Create GR on an active PO → "Goods receipt" toast
 *
 * The right /api/v1/scm/recommendations/* + /scm/purchase-orders/* calls are
 * asserted via a request listener. Navigation ALWAYS goes through the sidebar
 * (never a deep URL) so a broken menu gate fails the test (AC-NAV-1).
 *
 * Run against a running stack:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   REQUEST_BATCH_E2E_EMAIL=... REQUEST_BATCH_E2E_PASSWORD=... \
 *   npx playwright test e2e/scm-m4-copilot.spec.ts
 *
 * Credentials live in the frontend .env as REQUEST_BATCH_E2E_* (reused across the
 * SCM/e2e specs). Skips automatically when they aren't set.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the SCM M4 co-pilot flow');

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
 * leaf's resolved href (clicking the <Link> directly hangs on the protected
 * layout's ingest fetch — established repo workaround, see scm-policies.spec).
 */
async function openScmLeaf(page: Page, leaf: RegExp) {
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: /supply chain/i }).first();
  await expect(group).toBeVisible({ timeout: 20_000 });
  const link = page.getByRole('link', { name: leaf }).first();
  for (let i = 0; i < 6 && (await link.count()) === 0; i++) {
    await group.click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(400);
  }
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  if (!href) throw new Error(`Sidebar link "${leaf}" has no href`);
  await page.goto(href, { waitUntil: 'commit' });
}

test('m4 co-pilot: accept funded buys → confirm draft POs → create GR (AC-M4.15)', async ({ page }) => {
  // Multi-page round-trip; the dev build compiles each route lazily on first hit.
  test.setTimeout(240_000);
  const calls: string[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (/\/api\/v1\/scm\/(recommendations|purchase-orders|reorder-runs)/.test(u)) {
      calls.push(`${r.method()} ${new URL(u).pathname}`);
    }
  });
  const seen = (method: string, pathRe: RegExp) =>
    calls.some((c) => c.startsWith(method) && pathRe.test(c.slice(method.length + 1)));

  await login(page);

  // ── Reorder Planning — open a completed run with costed buys ──────────────
  await openScmLeaf(page, /^Reorder Planning$/);
  await page.waitForURL(/\/scm\/reorder$/);

  // The run-history list loads; pick the most recent completed run to view its
  // cash co-pilot results (data-driven — a seeded completed run must exist).
  await expect
    .poll(() => seen('GET', /\/scm\/reorder-runs/), { timeout: 20_000 })
    .toBeTruthy();
  // Run-history rows are <button>s carrying a "Completed" status badge.
  const completedRun = page
    .getByRole('button')
    .filter({ hasText: 'Completed' })
    .first();
  await expect(completedRun).toBeVisible({ timeout: 20_000 });
  await completedRun.click();

  // The Funded card + its budget-driven results render (buy recs fetched).
  await expect
    .poll(() => seen('GET', /\/scm\/reorder-runs\/[^/]+\/recommendations/), { timeout: 20_000 })
    .toBeTruthy();
  await expect(page.getByText('Funded').first()).toBeVisible({ timeout: 20_000 });

  // Select-all funded rows, then Accept via the unified Actions dropdown.
  const fundedSelectAll = page.getByLabel('Select all rows on this page').first();
  await expect(fundedSelectAll).toBeVisible({ timeout: 15_000 });
  await fundedSelectAll.click();
  await page.getByRole('button', { name: /^Actions$/ }).first().click();
  await page.getByRole('menuitem', { name: /^Accept$/ }).click();

  // Count-bearing confirm dialog → Accept.
  const acceptDialog = page.getByRole('alertdialog');
  await expect(acceptDialog.getByText(/Accept \d+ recommendation/i)).toBeVisible({ timeout: 10_000 });
  await acceptDialog.getByRole('button', { name: /^Accept$/ }).click();

  // The bulk-accept fired against the recommendations endpoint (draft POs created).
  await expect
    .poll(() => seen('POST', /\/scm\/recommendations\/bulk-accept/), { timeout: 20_000 })
    .toBeTruthy();
  await expect(page.getByText(/draft PO/i).first()).toBeVisible({ timeout: 15_000 });

  // ── Purchase Orders — drafts present + "Not on order" ─────────────────────
  await openScmLeaf(page, /^Purchase Orders$/);
  await page.waitForURL(/\/scm\/purchase-orders$/);
  await expect
    .poll(() => seen('GET', /\/scm\/purchase-orders/), { timeout: 20_000 })
    .toBeTruthy();

  await expect(page.getByText('Not on order').first()).toBeVisible({ timeout: 20_000 });
  // No broken numbers should ever render.
  await expect(page.getByText(/NaN/)).toHaveCount(0);

  // Select-all (all rows) → Actions → "Confirm N drafts" → confirm.
  await page.getByLabel('Select all rows on this page').first().click();
  await page.getByRole('button', { name: /^Actions$/ }).first().click();
  const confirmItem = page.getByRole('menuitem', { name: /Confirm \d+ draft/i });
  await expect(confirmItem).toBeVisible({ timeout: 10_000 });
  await confirmItem.click();
  const confirmDialog = page.getByRole('alertdialog');
  await expect(confirmDialog.getByText(/Confirm purchase orders\?/i)).toBeVisible();
  await confirmDialog.getByRole('button', { name: /^Confirm POs$/ }).click();

  // bulk-confirm fired; drafts become canonical PO-YYYY/MM-#### Active + On order.
  await expect
    .poll(() => seen('POST', /\/scm\/purchase-orders\/bulk-confirm/), { timeout: 20_000 })
    .toBeTruthy();
  await expect(page.getByText(/PO-\d{4}\/\d{2}-\d+/).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('On order').first()).toBeVisible({ timeout: 15_000 });
  // No provisional draft numbers or broken values remain after confirm.
  await expect(page.getByText(/PO-DRAFT-/)).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByText(/NaN/)).toHaveCount(0);

  // ── Create GR on an active PO ─────────────────────────────────────────────
  const grButton = page.getByRole('button', { name: /Create GR/i }).first();
  await expect(grButton).toBeVisible({ timeout: 15_000 });
  await grButton.click();
  const grDialog = page.getByRole('alertdialog');
  await expect(grDialog.getByText(/Create goods receipt\?/i)).toBeVisible();
  await grDialog.getByRole('button', { name: /^Create GR$/ }).click();

  await expect
    .poll(() => seen('POST', /\/scm\/purchase-orders\/[^/]+\/create-gr/), { timeout: 20_000 })
    .toBeTruthy();
  // Goods-receipt success toast.
  await expect(page.getByText(/Goods receipt/i).first()).toBeVisible({ timeout: 15_000 });
});
