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

/**
 * Click without Playwright's actionability auto-wait.
 *
 * The protected layout fires a localhost:7242 dev-ingest fetch that never
 * resolves in a test environment, so the page stays in a pre-load state and a
 * normal `.click()` hangs past its own timeout. `dispatchEvent` emits a real
 * bubbling MouseEvent, which React's root listener picks up, without waiting for
 * the page to settle first.
 */
async function tap(page: Page, locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  await locator.dispatchEvent('click');
}

/**
 * Type into a React-controlled input without actionability auto-wait.
 *
 * Same root cause as `tap`: the page never reaches a settled state, so
 * `locator.fill` hangs. Setting `.value` directly would be invisible to React,
 * which tracks the previous value on the DOM node - so this goes through the
 * native value setter and then fires a bubbling `input` event, which is exactly
 * what React's onChange listens for.
 */
async function type(locator: ReturnType<Page['locator']>, value: string) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  await locator.evaluate((el, v) => {
    const field = el as HTMLInputElement | HTMLTextAreaElement;
    // The setter has to come from the element's OWN prototype. Calling the
    // HTMLInputElement setter on a textarea throws "Illegal invocation".
    const prototype =
      field instanceof window.HTMLTextAreaElement
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(field, v);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

/**
 * Click at real screen coordinates.
 *
 * Radix tab triggers do not activate from a synthetic `click` event - they key
 * off pointer/focus - so `tap` is not enough for them. Real mouse events are,
 * and `boundingBox` only waits for layout rather than full actionability.
 */
async function tapReal(page: Page, locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
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
  await tap(page, page.getByRole('button', { name: /new page/i }).first());

  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10_000 });
  await type(page.getByLabel('Name'), name);
  await tap(page, page.getByRole('button', { name: /create page/i }));

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
    await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });
    // A page with no published label must say so rather than implying a live version.
    await expect(page.getByText(/not published/i).first()).toBeVisible();
  });

  test('save creates a version and publish makes it live', async ({ page }) => {
    await createPage(page, 'publish');

    // Nothing is saved yet, so there is nothing to publish.
    await expect(page.getByRole('button', { name: /^save$/i })).toBeDisabled();

    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));

    await expect(page.getByText(/unsaved changes/i)).toBeVisible({ timeout: 10_000 });
    await tap(page, page.getByRole('button', { name: /^save$/i }));

    await expect(page.getByText(/saved as version 1/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/unsaved changes/i)).toHaveCount(0);

    await tap(page, page.getByRole('button', { name: /^publish$/i }));
    await expect(page.getByText(/is now live/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Live · v1/)).toBeVisible();
  });

  test('rolling back moves the live version without losing either', async ({ page }) => {
    await createPage(page, 'rollback');

    // Version 1.
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));
    await tap(page, page.getByRole('button', { name: /^save$/i }));
    await expect(page.getByText(/saved as version 1/i)).toBeVisible({ timeout: 20_000 });
    await tap(page, page.getByRole('button', { name: /^publish$/i }));
    await expect(page.getByText(/Live · v1/)).toBeVisible({ timeout: 20_000 });

    // Version 2.
    await tap(page, page.getByRole('button', { name: /^text$/i }));
    await tap(page, page.getByRole('button', { name: /^save$/i }));
    await expect(page.getByText(/saved as version 2/i)).toBeVisible({ timeout: 20_000 });
    await tap(page, page.getByRole('button', { name: /^publish$/i }));
    await expect(page.getByText(/Live · v2/)).toBeVisible({ timeout: 20_000 });

    // Roll back through history. Both versions must survive it.
    await tap(page, page.getByRole('button', { name: /history/i }));
    await expect(page.getByText(/version history/i)).toBeVisible();
    await tap(page, page.getByRole('button', { name: /roll back to this/i }).first());

    await expect(page.getByRole('alertdialog')).toBeVisible();
    await tap(page, page.getByRole('button', { name: /^roll back$/i }));

    await expect(page.getByText(/Live · v1/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Version 2').first()).toBeVisible();
    await expect(page.getByText('Version 1').first()).toBeVisible();
  });

  test('the published page is readable with no login, and follows the label', async ({
    page,
    context,
  }) => {
    await createPage(page, 'public');

    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));
    await tap(page, page.getByRole('button', { name: /^save$/i }));
    await expect(page.getByText(/saved as version 1/i)).toBeVisible({ timeout: 20_000 });

    // Nothing is live yet, so there is no link to follow.
    await expect(page.getByRole('link', { name: /view live/i })).toHaveCount(0);

    await tap(page, page.getByRole('button', { name: /^publish$/i }));
    await expect(page.getByText(/Live · v1/)).toBeVisible({ timeout: 20_000 });

    const live = page.getByRole('link', { name: /view live/i });
    await expect(live, 'a published page offers its public link').toBeVisible({
      timeout: 10_000,
    });
    const href = await live.getAttribute('href');
    // The address carries the company segment; without it two companies'
    // identical slugs could not both resolve.
    expect(href).toMatch(/^\/c\/[^/]+\/zzt-public-/);

    // Read it as a stranger would: a fresh context with no session at all.
    const anonymous = await context.browser()!.newContext();
    const reader = await anonymous.newPage();
    try {
      await reader.goto(href!, { waitUntil: 'commit' });
      await expect(reader.locator('[data-dk-catalogue]')).toBeVisible({ timeout: 20_000 });
      // It rendered the catalogue rather than bouncing to a login screen.
      expect(reader.url()).toContain('/c/');
      await expect(reader.locator('input[type="password"]')).toHaveCount(0);
    } finally {
      await anonymous.close();
    }
  });

  test('an unpublished address is not readable by a stranger', async ({ page, context }) => {
    const name = await createPage(page, 'unpub');

    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));
    await tap(page, page.getByRole('button', { name: /^save$/i }));
    await expect(page.getByText(/saved as version 1/i)).toBeVisible({ timeout: 20_000 });

    // Saved but never published. Guessing the address must not reveal the draft.
    await openDealerKitLeaf(page, /catalogue pages/i);
    const row = page.getByRole('row', { name: new RegExp(name, 'i') }).first();
    await expect(row).toBeVisible({ timeout: 20_000 });
    const address = (await row.innerText()).match(/\/c\/[^\s]+/)?.[0];
    expect(address, 'the list shows the shareable address').toBeTruthy();

    const anonymous = await context.browser()!.newContext();
    const reader = await anonymous.newPage();
    try {
      await reader.goto(address!, { waitUntil: 'commit' });
      await expect(reader.getByText(/not available/i)).toBeVisible({ timeout: 20_000 });
      await expect(reader.locator('[data-dk-catalogue]')).toHaveCount(0);
    } finally {
      await anonymous.close();
    }
  });

  test('deleting a page asks first, then removes it', async ({ page }) => {
    const name = await createPage(page, 'delete-page');

    await openDealerKitLeaf(page, /catalogue pages/i);
    await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });

    await tap(page, page.getByRole('button', { name: new RegExp(`delete ${name}`, 'i') }));

    // A destructive action never happens on one click.
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText(/cannot be undone/i)).toBeVisible();

    await tap(page, dialog.getByRole('button', { name: /^delete$/i }));
    await expect(page.getByText(name)).toHaveCount(0, { timeout: 20_000 });
  });

  test('editing a heading in the inspector changes what the canvas shows', async ({ page }) => {
    await createPage(page, 'inspector');

    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));

    // The block is selected on insert, so the inspector is already showing it.
    const textarea = page.getByLabel('Block text');
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await type(textarea, 'ZZT Bathroom Range 2026');

    await expect(page.getByText('ZZT Bathroom Range 2026').first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test('picking products by hand creates a collection and renders tiles', async ({ page }) => {
    await createPage(page, 'collection');

    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^products$/i }));

    // Unbound, the block says so rather than showing a fake grid.
    await expect(page.getByText(/no products chosen/i).first()).toBeVisible({ timeout: 10_000 });

    await tap(page, page.getByRole('button', { name: /choose products/i }));
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    await tapReal(page, dialog.getByRole('tab', { name: /by hand/i }));

    // Products come from the real catalogue now, so pick whatever the first two
    // rows are rather than naming fixtures that no longer exist.
    const rows = dialog.getByRole('button', { name: /^include /i });
    await expect(rows.first()).toBeVisible({ timeout: 20_000 });
    await rows.nth(0).dispatchEvent('click');
    await rows.nth(1).dispatchEvent('click');

    await expect(dialog.locator('[data-dk-match-count]')).toHaveText(/2 products selected/i);
    await tap(page, dialog.getByRole('button', { name: /use these products/i }));

    // The selection round-trips through a page-scoped collection on the server
    // and comes back resolved, so real tiles render.
    await expect(page.locator('[data-dk-tile-grid]')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-dk-tile]').first()).toBeVisible();
  });

  test('a selection saved to the library can be bound to a second page', async ({ page }) => {
    // Half of AC-F7. This proves the SHARING: one library row, reachable from
    // the sidebar, bound to a second page and rendering there. That the same
    // row is promoted rather than copied - which is what makes a later edit
    // reach both pages - is asserted in
    // test_saving_as_reusable_keeps_the_same_row_so_the_page_stays_bound.
    // Editing the collection and watching BOTH pages change is not covered by
    // an E2E yet.
    const reusableName = zzt('shared-set');

    // Page one: pick a product, then promote the selection to the library.
    await createPage(page, 'shared-a');
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^products$/i }));
    await tap(page, page.getByRole('button', { name: /choose products/i }));

    const picker = page.getByRole('dialog');
    await tapReal(page, picker.getByRole('tab', { name: /by hand/i }));
    const rows = picker.getByRole('button', { name: /^include /i });
    await expect(rows.first()).toBeVisible({ timeout: 20_000 });
    await rows.nth(0).dispatchEvent('click');
    await tap(page, picker.getByRole('button', { name: /use these products/i }));

    await tap(page, page.getByRole('button', { name: /save as reusable/i }));
    await type(page.getByLabel('Name'), reusableName);
    await tap(page, page.getByRole('dialog').getByRole('button', { name: /^save$/i }));
    await expect(page.getByText(new RegExp(`saved "${reusableName}"`, 'i'))).toBeVisible({
      timeout: 20_000,
    });

    // It now appears in the library, reachable from the sidebar.
    await openDealerKitLeaf(page, /product collections/i);
    await expect(page.getByRole('heading', { name: /product collections/i })).toBeVisible({
      timeout: 20_000,
    });
    const libraryRow = page.getByRole('row', { name: new RegExp(reusableName, 'i') });
    await expect(libraryRow).toBeVisible({ timeout: 20_000 });

    // Page two binds the SAME collection and renders the same product.
    await createPage(page, 'shared-b');
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^products$/i }));

    await tapReal(page, page.getByRole('combobox', { name: /reusable collection/i }));
    await tap(page, page.getByRole('option', { name: new RegExp(reusableName, 'i') }));

    await expect(page.locator('[data-dk-tile-grid]')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-dk-tile]').first()).toBeVisible();
  });

  test('a tile design is authored, previewed, and bound to a products block', async ({
    page,
  }) => {
    const designName = zzt('design');

    await openDealerKitLeaf(page, /tile designs/i);
    await expect(page.getByRole('heading', { name: /tile designs/i })).toBeVisible({
      timeout: 20_000,
    });

    await tap(page, page.getByRole('button', { name: /new design/i }).first());
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    // 'Name' is also a tile field, so its reorder buttons match by label too.
    await type(dialog.getByRole('textbox', { name: 'Name' }), designName);

    // The preview is a real tile, so the design is judged as a design.
    await expect(dialog.locator('[data-dk-design-preview]')).toBeVisible();
    await expect(dialog.getByText('SK-3040')).toBeVisible();

    // Reordering is part of the design: price above the name is a real choice.
    await tap(page, dialog.getByRole('button', { name: /move price up/i }));

    await tap(page, dialog.getByRole('button', { name: /save design/i }));
    await expect(page.getByText(/tile design created/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(designName).first()).toBeVisible({ timeout: 20_000 });

    // It is immediately bindable from a page's products block.
    await createPage(page, 'design-bind');
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^products$/i }));

    await tapReal(page, page.getByRole('combobox', { name: /tile design/i }));
    await tap(page, page.getByRole('option', { name: new RegExp(designName, 'i') }));
  });

  test('a tile design cannot bind a field the renderer cannot draw', async ({ page }) => {
    // The whitelist is server-side; the UI simply never offers an unknown field.
    await openDealerKitLeaf(page, /tile designs/i);
    await tap(page, page.getByRole('button', { name: /new design/i }).first());

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText(/cost/i)).toHaveCount(0);
    await expect(dialog.getByText(/margin/i)).toHaveCount(0);
  });

  test('a bundle is created and shows as one price with its parts beneath', async ({ page }) => {
    const bundleName = zzt('bundle');

    await openDealerKitLeaf(page, /bundles/i);
    await expect(page.getByRole('heading', { name: /^bundles$/i })).toBeVisible({
      timeout: 20_000,
    });

    await tap(page, page.getByRole('button', { name: /new bundle/i }).first());
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    await type(dialog.getByRole('textbox', { name: 'Name' }), bundleName);
    await type(dialog.getByRole('spinbutton', { name: /bundle price/i }), '1800.00');

    await tapReal(page, dialog.getByRole('combobox').first());
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');

    await tap(page, dialog.getByRole('button', { name: /create bundle/i }));
    await expect(page.getByText(/bundle created/i)).toBeVisible({ timeout: 20_000 });

    // One priced heading, components beneath (AC-F12).
    const card = page.locator(`[data-dk-bundle]`).filter({ hasText: bundleName });
    await expect(card).toBeVisible({ timeout: 20_000 });
    // One priced heading. A single-component bundle does not repeat the
    // figure on the component line, so this matches exactly once.
    await expect(card.getByText('MYR 1,800.00')).toHaveCount(1);
  });

  test('a page the backend does not have shows an error, not an empty editor', async ({ page }) => {
    await page.goto('/dealer-kit/pages/00000000-0000-0000-0000-0000000000ff', {
      waitUntil: 'commit',
    });
    await expect(page.getByText(/could not open this page/i)).toBeVisible({ timeout: 20_000 });
  });

  test('switches breakpoints and reports the derived state', async ({ page }) => {
    await createPage(page, 'breakpoints');
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));

    await expect(page.getByText(/12 columns/)).toBeVisible({ timeout: 20_000 });

    await tapReal(page, page.getByRole('tab', { name: /mobile/i }));
    await expect(page.getByText(/4 columns/)).toBeVisible();
    await expect(page.getByText(/follows desktop/i).first()).toBeVisible();
  });

  test('draws page breaks in paper mode and nowhere else', async ({ page }) => {
    await createPage(page, 'paper');
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));

    // The desktop canvas is not at paper width, so a break line there would be a
    // guess presented as fact (AC-H6).
    await expect(page.getByTestId('dk-paper-page-label')).toHaveCount(0);
    await expect(page.getByTestId('dk-builder-canvas')).toBeVisible();

    await tapReal(page, page.getByRole('tab', { name: /paper/i }));
    await expect(page.getByTestId('dk-paper-page-label').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('dk-builder-canvas')).toHaveCount(0);
  });

  test('confirms before deleting a block', async ({ page }) => {
    await createPage(page, 'delete');
    await tap(page, page.getByRole('button', { name: /add section/i }));
    await tap(page, page.getByRole('button', { name: /^heading$/i }));

    await tap(page, page.getByRole('button', { name: /^delete .* block$/i }).first());
    await expect(page.getByText('Confirm delete')).toBeVisible();
    await expect(page.getByText(/cannot be undone/i)).toBeVisible();
  });

});

// Horizontal-overflow checks at three widths.
//
// The viewport is set through the FIXTURE, not `page.setViewportSize`. That call
// waits for the page to settle, and the dev-ingest fetch means it never does, so
// it hangs regardless of when it runs. `test.use` applies the size when the
// browser context is created, before any page exists.
for (const width of [1280, 768, 375]) {
  test.describe(`Dealer Kit page builder at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test('does not scroll the body sideways', async ({ page }) => {
      await login(page);

      // Below the desktop breakpoint the sidebar collapses into a drawer, so the
      // group button is legitimately absent. Menu gating is asserted at desktop
      // width in the first test; what is under test HERE is the page's own
      // layout, so it navigates directly.
      if (width >= 1280) {
        await openDealerKitLeaf(page, /catalogue pages/i);
      } else {
        await page.goto('/dealer-kit', { waitUntil: 'commit' });
      }

      await expect(page.getByRole('heading', { name: /catalogue pages/i })).toBeVisible({
        timeout: 20_000,
      });

      // Wide content scrolls inside its own container instead.
      const overflowsBy = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(
        overflowsBy,
        `body should not scroll horizontally at ${width}px`,
      ).toBeLessThanOrEqual(1);
    });
  });
}

