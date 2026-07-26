import { test, expect, type Page } from '@playwright/test';

/**
 * Dealer Kit page builder — full FE → BE → DB round-trip.
 *
 * Run:
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   REQUEST_BATCH_E2E_EMAIL=... \
 *   REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/dealer-kit-builder.spec.ts
 *
 * There are no fixtures here. Each test creates its own page through the UI, so
 * what is exercised is the real API, the real company scoping and the real
 * version/label tables. Every page is named with the reserved ZZT prefix so the
 * rows it leaves behind on the shared dev database are identifiable.
 *
 * The first assertion is deliberately the SIDEBAR, not a URL: reaching a deep
 * link directly would pass even if the menu entry were missing, mis-gated behind
 * a moduleKey the tenant lacks, or hidden under a collapsed group.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the Dealer Kit builder flow',
);

function zzt(stem: string): string {
  return `zzt-${stem}-${Math.random().toString(36).slice(2, 8)}`;
}

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
 * Open a Dealer Kit leaf via the sidebar.
 *
 * Two deliberate departures from a plain click, both established in the existing
 * specs. The protected layout fires a localhost:7242 dev-ingest fetch that holds
 * the page pre-load, so Playwright's actionability auto-wait never settles and a
 * real `.click()` hangs well past its own timeout. `dispatchEvent` skips
 * actionability, and navigation uses the leaf's resolved href. The sidebar
 * assertions still run, so a missing or mis-gated entry still fails here.
 */
async function openDealerKitLeaf(page: Page, leaf: RegExp) {
  await page.goto('/', { waitUntil: 'commit' });

  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });

  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }

  const link = page.getByRole('link', { name: leaf }).first();
  await expect(link, 'Dealer Kit leaf should render inside the group').toBeVisible({
    timeout: 15_000,
  });

  const href = await link.getAttribute('href');
  expect(href).toBeTruthy();
  await page.goto(href!, { waitUntil: 'commit' });
}

/** Create a page through the UI and land in its editor. Returns its name. */
async function createPage(page: Page, stem = 'catalogue'): Promise<string> {
  const name = zzt(stem);

  await openDealerKitLeaf(page, /catalogue pages/i);
  await page.getByRole('button', { name: /new page/i }).first().click();

  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10_000 });
  await page.getByLabel('Name').fill(name);
  await page.getByRole('button', { name: /create page/i }).click();

  await expect(page.getByRole('heading', { name: /page builder/i })).toBeVisible({
    timeout: 20_000,
  });
  return name;
}

test.describe('Dealer Kit page builder', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('creates a page from the sidebar and lists it', async ({ page }) => {
    const name = await createPage(page, 'listed');

    await openDealerKitLeaf(page, /catalogue pages/i);
    await expect(page.getByText(name)).toBeVisible({ timeout: 20_000 });
    // A page with no published label must say so rather than implying a live version.
    await expect(page.getByText(/not published/i).first()).toBeVisible();
  });

  test('save creates a version and publish makes it live', async ({ page }) => {
    await createPage(page, 'publish');

    // Nothing is saved yet, so there is nothing to publish.
    await expect(page.getByRole('button', { name: /^save$/i })).toBeDisabled();

    await page.getByRole('button', { name: /add section/i }).click();
    await page.getByRole('button', { name: /^heading$/i }).click();

    await expect(page.getByText(/unsaved changes/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /^save$/i }).click();

    await expect(page.getByText(/saved as version 1/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/unsaved changes/i)).toHaveCount(0);

    await page.getByRole('button', { name: /^publish$/i }).click();
    await expect(page.getByText(/is now live/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Live · v1/)).toBeVisible();
  });

  test('rolling back moves the live version without losing either', async ({ page }) => {
    await createPage(page, 'rollback');

    // Version 1.
    await page.getByRole('button', { name: /add section/i }).click();
    await page.getByRole('button', { name: /^heading$/i }).click();
    await page.getByRole('button', { name: /^save$/i }).click();
    await expect(page.getByText(/saved as version 1/i)).toBeVisible({ timeout: 20_000 });
    await page.getByRole('button', { name: /^publish$/i }).click();
    await expect(page.getByText(/Live · v1/)).toBeVisible({ timeout: 20_000 });

    // Version 2.
    await page.getByRole('button', { name: /^text$/i }).click();
    await page.getByRole('button', { name: /^save$/i }).click();
    await expect(page.getByText(/saved as version 2/i)).toBeVisible({ timeout: 20_000 });
    await page.getByRole('button', { name: /^publish$/i }).click();
    await expect(page.getByText(/Live · v2/)).toBeVisible({ timeout: 20_000 });

    // Roll back through history. Both versions must survive it.
    await page.getByRole('button', { name: /history/i }).click();
    await expect(page.getByText(/version history/i)).toBeVisible();
    await page.getByRole('button', { name: /roll back to this/i }).first().click();

    await expect(page.getByRole('alertdialog')).toBeVisible();
    await page.getByRole('button', { name: /^roll back$/i }).click();

    await expect(page.getByText(/Live · v1/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Version 2')).toBeVisible();
    await expect(page.getByText('Version 1')).toBeVisible();
  });

  test('a page the backend does not have shows an error, not an empty editor', async ({ page }) => {
    await page.goto('/dealer-kit/pages/00000000-0000-0000-0000-0000000000ff', {
      waitUntil: 'commit',
    });
    await expect(page.getByText(/could not open this page/i)).toBeVisible({ timeout: 20_000 });
  });

  test('switches breakpoints and reports the derived state', async ({ page }) => {
    await createPage(page, 'breakpoints');
    await page.getByRole('button', { name: /add section/i }).click();
    await page.getByRole('button', { name: /^heading$/i }).click();

    await expect(page.getByText(/12 columns/)).toBeVisible({ timeout: 20_000 });

    await page.getByRole('tab', { name: /mobile/i }).click();
    await expect(page.getByText(/4 columns/)).toBeVisible();
    await expect(page.getByText(/follows desktop/i).first()).toBeVisible();
  });

  test('draws page breaks in paper mode and nowhere else', async ({ page }) => {
    await createPage(page, 'paper');
    await page.getByRole('button', { name: /add section/i }).click();
    await page.getByRole('button', { name: /^heading$/i }).click();

    // The desktop canvas is not at paper width, so a break line there would be a
    // guess presented as fact (AC-H6).
    await expect(page.getByTestId('dk-paper-page-label')).toHaveCount(0);
    await expect(page.getByTestId('dk-builder-canvas')).toBeVisible();

    await page.getByRole('tab', { name: /paper/i }).click();
    await expect(page.getByTestId('dk-paper-page-label').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('dk-builder-canvas')).toHaveCount(0);
  });

  test('confirms before deleting a block', async ({ page }) => {
    await createPage(page, 'delete');
    await page.getByRole('button', { name: /add section/i }).click();
    await page.getByRole('button', { name: /^heading$/i }).click();

    await page.getByRole('button', { name: /^delete .* block$/i }).first().click();
    await expect(page.getByText('Confirm delete')).toBeVisible();
    await expect(page.getByText(/cannot be undone/i)).toBeVisible();
  });

  test('does not scroll sideways from desktop down to phone width', async ({ page }) => {
    await openDealerKitLeaf(page, /catalogue pages/i);
    await expect(page.getByRole('heading', { name: /catalogue pages/i })).toBeVisible({
      timeout: 20_000,
    });

    for (const width of [1280, 768, 375]) {
      await page.setViewportSize({ width, height: 900 });
      const overflowsBy = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(
        overflowsBy,
        `page body should not scroll horizontally at ${width}px`,
      ).toBeLessThanOrEqual(1);
    }
  });
});
