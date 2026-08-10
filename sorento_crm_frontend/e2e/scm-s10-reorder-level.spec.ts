/**
 * SCM S10 - the reorder level as a planning basis, end to end against the live stack.
 *
 * Two things only a browser proves:
 *
 *   1. The buyer's weekly lookups reach the row. On a real plan, opening the checklist on
 *      a buy row shows on hand / incoming SPO / outstanding PO / outstanding sales / the
 *      level / the last price, with NO network call - every figure is frozen with the
 *      recommendation, and a fetch here would mean the row is re-deriving against stock
 *      that has since moved.
 *
 *   2. The bands are reachable. "Needs a level" has to render as its own tile and its own
 *      collapsible section, because an item the plan could not size must be visible rather
 *      than absent - a plan that drops it reports "nothing to do" for stock that was
 *      simply never set up.
 *
 * Navigation ALWAYS goes through the sidebar (never a deep URL), so a missing menu entry
 * or a broken permission gate fails the test rather than being skipped past.
 *
 * Run against a running stack:
 *   PORTAL_E2E_BASE_URL=http://localhost:3060 \
 *   REQUEST_BATCH_E2E_EMAIL=... REQUEST_BATCH_E2E_PASSWORD=... \
 *   npx playwright test e2e/scm-s10-reorder-level.spec.ts
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the SCM S10 flow');

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

/** Confirm the sidebar group + leaf render, then follow the leaf's resolved href
 *  (clicking the <Link> hangs on the protected layout's ingest fetch - repo workaround). */
async function openLeaf(page: Page, group: RegExp, leaf: RegExp) {
  await page.goto('/', { waitUntil: 'commit' });
  const groupBtn = page.getByRole('button', { name: group }).first();
  await expect(groupBtn).toBeVisible({ timeout: 20_000 });
  const link = page.getByRole('link', { name: leaf }).first();
  for (let i = 0; i < 6 && (await link.count()) === 0; i++) {
    await groupBtn.click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(400);
  }
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  if (!href) throw new Error(`Sidebar link "${leaf}" has no href`);
  await page.goto(href, { waitUntil: 'commit' });
}

test('the plan shows a Needs a level band and the buyer checklist on a row', async ({ page }) => {
  test.setTimeout(180_000);
  const calls: string[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (/\/api\/v1\/scm\//.test(u)) calls.push(`${r.method()} ${new URL(u).pathname}`);
  });

  await login(page);
  await openLeaf(page, /supply chain/i, /^Reorder Planning$/);

  // The band and its tile exist whichever basis the plan ran on - an empty one still says
  // so, because "no unsized items" and "we did not look" must not render identically.
  await expect(page.getByText('Needs a level').first()).toBeVisible({ timeout: 60_000 });

  // It is fetched as its own kind, not folded into the buys.
  await expect
    .poll(() => calls.some((c) => /GET .*\/recommendations$/.test(c)), { timeout: 60_000 })
    .toBe(true);

  // Open the band and confirm it renders a table or an honest empty state, never nothing.
  await page.getByRole('button', { name: /needs a level/i }).first().click();
  await expect(
    page
      .getByText(/every item in this plan has a level|still to set of|no reorder level set/i)
      .first(),
  ).toBeVisible({ timeout: 20_000 });

  // ── the checklist on a buy row ───────────────────────────────────────────────
  const checklist = page.getByRole('button', { name: /what the plan checked/i }).first();
  if ((await checklist.count()) === 0) {
    test.info().annotations.push({
      type: 'note',
      description: 'No buy row in today plan, so the row checklist could not be exercised',
    });
    return;
  }

  const before = calls.length;
  await checklist.click();
  await expect(page.getByText('Incoming (SPO)')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('Outstanding PO')).toBeVisible();
  await expect(page.getByText('Outstanding sales')).toBeVisible();
  await expect(page.getByText('Reorder level')).toBeVisible();

  // Frozen, not re-derived: opening it must not have called the API.
  await page.waitForTimeout(500);
  expect(calls.length, 'the checklist must read frozen figures, not fetch').toBe(before);
});

test('a warehouse says who it sells to, on the read view and the edit view alike', async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page);
  await openLeaf(page, /inventory/i, /^Warehouses$/);

  const firstRow = page.locator('table tbody tr').first();
  await expect(firstRow).toBeVisible({ timeout: 30_000 });
  await firstRow.click();

  // Read view: the planning tab carries it.
  await page.getByRole('tab', { name: /planning/i }).click();
  await expect(page.getByText('Sells to')).toBeVisible({ timeout: 15_000 });

  // Edit view: same tab, same position - the read view is what teaches where things are.
  await page.getByRole('link', { name: /^edit$/i }).first().click();
  await page.getByRole('tab', { name: /planning/i }).click();
  await expect(page.getByText('Sells to')).toBeVisible({ timeout: 15_000 });
});
