import { test, expect, type Page } from '@playwright/test';

/**
 * Dealer Kit page builder - S1 phase 1 (prototype on fixtures).
 *
 * Run:
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   REQUEST_BATCH_E2E_EMAIL=... \
 *   REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/dealer-kit-builder.spec.ts
 *
 * The first assertion is deliberately the SIDEBAR, not the page: reaching a deep
 * URL directly would pass even if the menu entry were missing, mis-gated behind a
 * moduleKey the tenant does not have, or hidden under a collapsed group. That is
 * the failure this spec exists to catch.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the Dealer Kit builder flow',
);

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
 * Open a Dealer Kit leaf by going through the sidebar.
 *
 * Two deliberate departures from a plain click, both established in the existing
 * specs. The protected layout fires a localhost:7242 dev-ingest fetch that holds
 * the page in a pre-load state, so Playwright's actionability auto-wait never
 * settles: a real `.click()` hangs far past its own timeout. `dispatchEvent`
 * skips actionability entirely, and navigation goes to the leaf's resolved href
 * rather than through the <Link>.
 *
 * The sidebar assertions still run, so a missing entry, a wrong moduleKey or a
 * permission-gated leaf all still fail here - which is the point of the helper.
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

/** Open the fixture page's editor without clicking through a hanging <Link>. */
async function openFixtureEditor(page: Page) {
  await openDealerKitLeaf(page, /catalogue pages/i);
  await expect(page.getByText('Bathroom Catalogue 2026')).toBeVisible({ timeout: 20_000 });
  await page.goto('/dealer-kit/pages/page-2026-bathroom', { waitUntil: 'commit' });
}

test.describe('Dealer Kit page builder', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('reaches Catalogue Pages from the sidebar and lists pages', async ({ page }) => {
    await openDealerKitLeaf(page, /catalogue pages/i);

    await expect(page.getByRole('heading', { name: /catalogue pages/i })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText('Bathroom Catalogue 2026')).toBeVisible({ timeout: 20_000 });

    // Publish state must be legible from the list, not only inside the editor.
    await expect(page.getByText(/Live · v2/)).toBeVisible();
    await expect(page.getByText(/Not published/)).toBeVisible();
  });

  test('opens the editor and switches breakpoints', async ({ page }) => {
    await openFixtureEditor(page);

    await expect(page.getByRole('heading', { name: /page builder/i })).toBeVisible({
      timeout: 20_000,
    });

    // Desktop is authored directly, so it reports its column count and nothing else.
    await expect(page.getByText(/12 columns/)).toBeVisible({ timeout: 20_000 });

    await page.getByRole('tab', { name: /mobile/i }).click();
    await expect(page.getByText(/4 columns/)).toBeVisible();
    await expect(page.getByText(/follows desktop/i).first()).toBeVisible();
  });

  test('draws page breaks in paper mode and nowhere else', async ({ page }) => {
    await openFixtureEditor(page);
    await expect(page.getByRole('heading', { name: /page builder/i })).toBeVisible({
      timeout: 20_000,
    });

    // The desktop canvas is not at paper width, so a break line there would be a
    // guess presented as fact (AC-H6).
    await expect(page.getByTestId('dk-paper-page-label')).toHaveCount(0);
    await expect(page.getByTestId('dk-builder-canvas')).toBeVisible();

    await page.getByRole('tab', { name: /paper/i }).click();

    const pageLabels = page.getByTestId('dk-paper-page-label');
    await expect(pageLabels.first()).toBeVisible({ timeout: 15_000 });
    await expect(pageLabels.first()).toHaveText('Cover');
    // A section marked breakBefore must start its own page, so there is more
    // than the cover once paper mode paginates.
    await expect(pageLabels).not.toHaveCount(1);

    // Break lines belong to paper mode only - the grid canvas is gone here.
    await expect(page.getByTestId('dk-builder-canvas')).toHaveCount(0);
  });

  test('does not claim unsaved changes before the user edits anything', async ({ page }) => {
    await openFixtureEditor(page);
    await expect(page.getByText(/12 columns/)).toBeVisible({ timeout: 20_000 });

    // The grid compacts and grows blocks to fit their content on load. None of
    // that is an edit the user made, and reporting it as one teaches people to
    // ignore the indicator.
    await expect(page.getByText(/unsaved changes/i)).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^save$/i })).toBeDisabled();
  });

  test('dragging a block moves it on the grid and marks the page dirty', async ({ page }) => {
    await openFixtureEditor(page);
    await expect(page.getByText(/12 columns/)).toBeVisible({ timeout: 20_000 });

    const item = page.locator('.react-grid-item').first();
    const before = await item.boundingBox();
    expect(before).not.toBeNull();

    // The handle only appears on hover, and RGL listens for real pointer events,
    // so this has to be a genuine press-move-release rather than dragTo().
    await item.hover();
    const handle = item.locator('[data-dk-drag-handle]').first();
    const handleBox = await handle.boundingBox();
    expect(handleBox).not.toBeNull();

    await page.mouse.move(
      handleBox!.x + handleBox!.width / 2,
      handleBox!.y + handleBox!.height / 2,
    );
    await page.mouse.down();
    // Past RGL's drag threshold, then a real distance so it lands a column over.
    await page.mouse.move(handleBox!.x + 40, handleBox!.y + 120, { steps: 12 });
    await page.mouse.move(handleBox!.x + 160, handleBox!.y + 200, { steps: 12 });
    await page.mouse.up();

    const after = await item.boundingBox();
    expect(after).not.toBeNull();

    const moved =
      Math.abs(after!.x - before!.x) > 4 || Math.abs(after!.y - before!.y) > 4;
    expect(moved, 'block should have moved on the grid').toBe(true);

    // A real gesture IS an edit, unlike the reflow the grid does on load.
    await expect(page.getByText(/unsaved changes/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /^save$/i })).toBeEnabled();
  });

  test('confirms before deleting a block', async ({ page }) => {
    await openFixtureEditor(page);
    await expect(page.getByText(/12 columns/)).toBeVisible({ timeout: 20_000 });

    await page.getByRole('button', { name: /^delete .* block$/i }).first().click();

    await expect(page.getByText('Confirm delete')).toBeVisible();
    await expect(page.getByText(/cannot be undone/i)).toBeVisible();
  });

  test('does not scroll sideways at phone width', async ({ page }) => {
    // Sidebar nav is asserted in the first test. Here the page is loaded at
    // desktop width and then resized, which is both faster and closer to the
    // thing under test: the layout reflowing, not a cold mobile navigation.
    await openDealerKitLeaf(page, /catalogue pages/i);
    await expect(page.getByText('Bathroom Catalogue 2026')).toBeVisible({ timeout: 20_000 });

    for (const width of [1280, 768, 375]) {
      await page.setViewportSize({ width, height: 900 });

      // The body must never scroll sideways; wide content scrolls inside its
      // own container instead.
      const overflowsBy = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflowsBy, `page body should not scroll horizontally at ${width}px`).toBeLessThanOrEqual(1);
    }

    // Still legible after the reflow, not merely non-overflowing.
    await expect(page.getByText('Bathroom Catalogue 2026')).toBeVisible();
  });
});
