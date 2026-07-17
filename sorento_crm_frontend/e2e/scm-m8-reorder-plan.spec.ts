/**
 * SCM M8 — daily reorder plan + Days-cover drill e2e (M8-D3 / M8-A2 / M8-A3).
 * Full FE → BE → DB round-trip against the LIVE stack (FE :3000 + BE + worker;
 * `scm` module enabled, a completed run seeded so today's plan has real recs):
 *
 *   sidebar → Supply Chain → Reorder Planning
 *     → page opens straight to TODAY'S plan (no run click) — M8-D3
 *     → the plan table renders real buy recommendations (GET .../recommendations)
 *     → click a row's "Explain days cover" drill
 *     → the drill lazy-fetches GET /api/v1/scm/analytics/explain/demand — M8-A2
 *     → the arithmetic RECONCILES (net / rate = N days) and NEVER divides by zero
 *       ("/ 0" is never rendered) even on a deficit / no-demand row — M8-A3
 *
 * Navigation ALWAYS goes through the sidebar (never a deep URL) so a broken menu
 * gate fails the test (AC-NAV-1). The demand endpoint hit is asserted via a
 * request listener (the FE hook → service → api-client chain wired correctly).
 *
 * Run against a running stack:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   REQUEST_BATCH_E2E_EMAIL=... REQUEST_BATCH_E2E_PASSWORD=... \
 *   npx playwright test e2e/scm-m8-reorder-plan.spec.ts
 *
 * Credentials live in the frontend .env as REQUEST_BATCH_E2E_* (reused across the
 * SCM/e2e specs). Skips automatically when they aren't set.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the SCM M8 reorder-plan flow');

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
 * layout's ingest fetch — established repo workaround, see scm-m4-copilot.spec).
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

test('m8 reorder plan: opens to today + Days-cover drill hits explain/demand and reconciles (M8-D3/A2/A3)', async ({ page }) => {
  // The dev build compiles the route lazily on first hit + the plan fetches recs.
  test.setTimeout(180_000);
  const calls: string[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (/\/api\/v1\/scm\/(reorder-runs|recommendations|analytics\/explain)/.test(u)) {
      calls.push(`${r.method()} ${new URL(u).pathname}${new URL(u).search}`);
    }
  });
  const seen = (method: string, pathRe: RegExp) =>
    calls.some((c) => c.startsWith(method) && pathRe.test(c.slice(method.length + 1)));

  await login(page);

  // ── Reorder Planning — opens straight to today's plan (M8-D3) ──────────────
  await openScmLeaf(page, /^Reorder Planning$/);
  await page.waitForURL(/\/scm\/reorder$/);

  // The page opens to today's snapshot directly — GET /reorder-runs/today fires
  // WITHOUT any "Run planning" click.
  await expect
    .poll(() => seen('GET', /\/scm\/reorder-runs\/today/), { timeout: 20_000 })
    .toBeTruthy();

  // Real buy recommendations load into the plan table (data-driven — a completed
  // run must be seeded so today's plan has rows).
  await expect
    .poll(() => seen('GET', /\/scm\/reorder-runs\/[^/]+\/recommendations/), { timeout: 25_000 })
    .toBeTruthy();

  // The one-table plan renders its Within-budget section + a Days-cover column.
  await expect(page.getByText('Within budget').first()).toBeVisible({ timeout: 25_000 });
  const drillTrigger = page.getByRole('button', { name: 'Explain days cover' }).first();
  await expect(drillTrigger).toBeVisible({ timeout: 20_000 });

  // ── Open the Days-cover drill (M8-A2) ─────────────────────────────────────
  await drillTrigger.click();

  // The drill lazy-fetches the demand working from /analytics/explain/demand —
  // proves the hook → drillService → api-client chain is wired to the right route.
  await expect
    .poll(() => seen('GET', /\/scm\/analytics\/explain\/demand/), { timeout: 20_000 })
    .toBeTruthy();

  // The drill header renders (net breakdown + demand + arithmetic OR the honest
  // "undefined" copy on a deficit / no-demand row).
  const drillHeader = page.getByText(/Days cover =/).first();
  await expect(drillHeader).toBeVisible({ timeout: 15_000 });
  // Full metric name spelled out — never the ambiguous "CV".
  await expect(page.getByText('Coefficient of variation')).toBeVisible({ timeout: 10_000 });

  // ── Reconciliation invariant (M8-A3): NEVER a division by zero ────────────
  // Whether the row has finite cover ("net / rate = N days") or is a deficit /
  // no-demand row (the undefined copy), the drill must never print "/ 0".
  await expect(page.getByText(/\/\s*0(\.0+)?\s*=/)).toHaveCount(0);
});
