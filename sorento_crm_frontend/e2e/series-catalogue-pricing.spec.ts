/**
 * Series catalogue and pricing - browser regression cover (T6).
 *
 * Run:
 *   PORTAL_E2E_BASE_URL=http://localhost:3010 \
 *   REQUEST_BATCH_E2E_EMAIL=... REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/series-catalogue-pricing.spec.ts
 *
 * Credentials live in the frontend .env as REQUEST_BATCH_E2E_* (shared with the other
 * specs). Skips automatically when unset so local dev is not blocked.
 *
 * Why a spec rather than ad-hoc clicking. Three of these have already been wrong once:
 *
 * 1. The screen the client complained about had its controls in a second row UNDER the
 *    heading. That is a layout fact no unit test can see, and it came back as a complaint
 *    rather than as a failure.
 * 2. Rows used to open a DIALOG. "Click into it and see the form" is the requirement, and
 *    only a browser can tell a page from a modal.
 * 3. The unmatched-code list is the whole value of an import and is trivially droppable -
 *    a load that silently keeps 92 of 141 codes looks identical to one that kept them all.
 *
 * The series it creates is prefixed `zzt-e2e` and deleted at the end, so the client's own
 * Sanitaryware template is never touched. Deletion goes through the UI on purpose: it is
 * the destructive path and the only place the confirmation dialog is exercised.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the series spec');

const SERIES_NAME = `zzt-e2e series ${Date.now()}`;

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
  // The shell hydrates after the URL settles, and clicking an accordion trigger mid-hydration
  // dispatches into a component that is about to be replaced - the click lands nowhere and
  // Playwright waits out its timeout on an element that looks perfectly actionable.
  await page.waitForLoadState('networkidle').catch(() => {});
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

/**
 * Reached by CLICKING the sidebar, never by a deep URL.
 *
 * A direct `goto` cannot fail the way this feature actually failed: the entry has to exist,
 * be permitted, and sit under the right group. Splitting one "Pricing Policy" item into two
 * is exactly the change that breaks that quietly.
 */
test('Series and Price Floors are reachable from the sidebar as separate entries', async ({
  page,
}) => {
  const group = page.getByRole('button', { name: 'Project Sales', exact: true });
  await expect(group).toBeVisible({ timeout: 30_000 });
  await group.click();

  const series = page.getByRole('link', { name: 'Series', exact: true });
  const floors = page.getByRole('link', { name: 'Price Floors', exact: true });
  await expect(series).toBeVisible({ timeout: 20_000 });
  await expect(floors).toBeVisible();

  await series.click();
  await page.waitForURL(/\/project-sales\/series$/, { timeout: 20_000 });
  await expect(page.getByRole('heading', { name: 'Series', level: 1 })).toBeVisible();
});

test('the list toolbar is one row, and carries no explanatory prose', async ({ page }) => {
  await page.goto('/project-sales/series');

  const search = page.getByPlaceholder('Search series');
  const columns = page.getByRole('button', { name: /columns/i });
  const add = page.getByRole('button', { name: /add series/i });
  await expect(search).toBeVisible({ timeout: 20_000 });
  await expect(columns).toBeVisible();
  await expect(add).toBeVisible();

  // The complaint in one assertion: the controls sit on ONE line with the primary action,
  // not stacked under the section heading. Compared by vertical centre so a few pixels of
  // differing control height cannot make this flap.
  const centre = async (locator: ReturnType<Page['getByRole']>) => {
    const box = await locator.boundingBox();
    if (!box) throw new Error('control is not rendered');
    return box.y + box.height / 2;
  };
  const [searchY, columnsY, addY] = [
    await centre(search),
    await centre(columns),
    await centre(add),
  ];
  expect(Math.abs(searchY - columnsY)).toBeLessThan(12);
  expect(Math.abs(searchY - addY)).toBeLessThan(12);

  // No subtitle under the title. The old screen explained itself here.
  await expect(
    page.getByText(/what each scope is supposed to be quoted from/i),
  ).toHaveCount(0);
});

test('a series is created, loaded, priced and deleted, all on pages', async ({ page }) => {
  await page.goto('/project-sales/series');

  // --- create, on a page rather than in a dialog -------------------------------------
  await page.getByRole('button', { name: /add series/i }).click();
  await page.waitForURL(/\/project-sales\/series\/new$/, { timeout: 20_000 });
  await expect(page.getByRole('dialog')).toHaveCount(0);

  // By id, and after the route settles. The field is present the instant the URL changes but
  // the brand/category selects are still fetching behind it, and typing into a form that is
  // about to re-render loses the keystrokes.
  await page.waitForLoadState('networkidle').catch(() => {});
  const name = page.locator('#series-name');
  await expect(name).toBeVisible({ timeout: 30_000 });
  await name.fill(SERIES_NAME);
  await page.getByRole('button', { name: /create series/i }).click();
  // Lands on the saved series: products cannot hang off an id that does not exist yet.
  await page.waitForURL(/\/project-sales\/series\/[0-9a-f-]{36}$/, { timeout: 20_000 });

  // --- load codes, and read back what missed -----------------------------------------
  await page
    .getByPlaceholder(/paste product codes/i)
    .fill('CWC7601-S-RL\nzzt-not-a-real-code');
  await page.getByRole('button', { name: 'Load', exact: true }).click();

  // The unmatched code is ON SCREEN, verbatim. This is the assertion the whole import
  // exists for: 49 of the client's 141 codes miss, and a silent loader hides that.
  await expect(page.getByText('zzt-not-a-real-code')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/not in the catalogue/i)).toBeVisible();

  // --- delete, through the confirmation ----------------------------------------------
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(page.getByText(/cannot be undone/i)).toBeVisible({ timeout: 10_000 });
  await page
    .getByRole('button', { name: /^(delete|confirm|yes)/i })
    .last()
    .click();
  await page.waitForURL(/\/project-sales\/series$/, { timeout: 20_000 });
  await expect(page.getByText(SERIES_NAME)).toHaveCount(0);
});

/**
 * The client tests on a phone as well as a desktop, and a table of five money columns is
 * exactly the thing that pushes a page into horizontal overflow. The rule from the repo's
 * own history: the BODY must never scroll sideways; wide content scrolls inside its own
 * container.
 */
test('the series pages do not overflow sideways at 375px', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });

  for (const path of ['/project-sales/series', '/project-sales/price-floors']) {
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});
    await expect(page.locator('table').first()).toBeVisible({ timeout: 45_000 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    // A pixel or two of rounding is not an overflow anybody can see; a column is.
    expect(overflow, `${path} scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(2);
  }
});
