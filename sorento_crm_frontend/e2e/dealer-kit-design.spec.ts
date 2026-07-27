import { test, expect, type Page } from '@playwright/test';

import { purgeSelections } from './dealerKitCleanup';

/**
 * The room designer, in a real browser.
 *
 * WebGL is the reason this is an E2E and not a component test: jsdom has no
 * canvas context, so the 3D view cannot be exercised anywhere else.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the designer flow');

async function tap(page: Page, locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  await locator.dispatchEvent('click');
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

async function openDesigner(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }
  const link = page.getByRole('link', { name: /room designer/i }).first();
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  await page.goto(href!, { waitUntil: 'commit' });
}

/**
 * Every selection this run creates, so the teardown can delete exactly those.
 * The dev database is a copy of production; a suite that leaves rows behind
 * makes the real lists unreadable within a few runs.
 */
const createdSelections: string[] = [];

test.describe('Dealer Kit room designer', () => {
  // Each test logs in fresh AND now does real server round trips (the design is
  // persisted, not local state), so the default 90s is not enough headroom.
  test.describe.configure({ timeout: 180_000 });

  test.beforeEach(async ({ page }) => {
    page.on('response', (response) => {
      if (
        response.request().method() === 'POST' &&
        /\/dealer-kit\/selections$/.test(response.url()) &&
        response.status() === 201
      ) {
        response
          .json()
          .then((body: { id?: string }) => body?.id && createdSelections.push(body.id))
          .catch(() => undefined);
      }
    });
    await login(page);
  });

  test.afterAll(async ({ browser }, testInfo) => {
    await purgeSelections(browser, createdSelections, testInfo.project.use.baseURL);
  });

  test('opens from the sidebar with a room and no products', async ({ page }) => {
    await openDesigner(page);

    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.locator('[data-dk-room-plan]')).toBeVisible();
    // The starting room is 4m x 3m, and the area is derived, never stored.
    // The figure appears on the plan overlay and in the summary.
    await expect(page.getByText(/12\.0 m/).first()).toBeVisible();
    await expect(page.getByText(/nothing placed yet/i)).toBeVisible();
  });

  test('adding a product puts a box in the room', async ({ page }) => {
    await openDesigner(page);

    // Keyboard, not a real mouse click: mouse.click wedges against this
    // layout's never-resolving dev-ingest fetch under load, which made this
    // pass alone and flake in a full run.
    const combobox = page.getByRole('combobox').first();
    await expect(combobox).toBeVisible({ timeout: 20_000 });
    // Pressing through the locator, not page.keyboard: the page-level keyboard
    // waits on page state, and this layout's dev-ingest fetch never resolves,
    // so under load that wait can outlive the whole test.
    await combobox.press('Enter');

    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');

    await tap(page, page.getByRole('button', { name: /add product to room/i }));

    // It appears on the plan as a real polygon, not a list entry only.
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 20_000 });
    // And the estimate is stated rather than hidden (AC-V2).
    await expect(page.getByText(/sizes are estimated/i)).toBeVisible();
  });

  test('the 3D view renders a WebGL canvas', async ({ page }) => {
    await openDesigner(page);

    // Radix tabs activate on arrow keys, and keyboard avoids the real-mouse
    // path entirely - a synthetic click does not move a Radix tab, and
    // page.mouse.click wedges against this layout's never-resolving fetch.
    const planTab = page.getByRole('tab', { name: /^plan$/i });
    await expect(planTab).toBeVisible({ timeout: 20_000 });
    await planTab.press('ArrowRight');

    const scene = page.locator('[data-dk-room-scene] canvas');
    await expect(scene).toBeVisible({ timeout: 20_000 });

    // A canvas that exists but never got a context is the failure worth
    // catching: it looks identical to a working one in a screenshot.
    const hasContext = await scene.evaluate(
      (node) => Boolean((node as HTMLCanvasElement).getContext('webgl2') ||
        (node as HTMLCanvasElement).getContext('webgl')),
    );
    expect(hasContext).toBe(true);
  });

  test('wall lengths are shown live in millimetres', async ({ page }) => {
    await openDesigner(page);

    // AC-R1: a user reshaping a room must see the dimensions, not just an area.
    // Without these, "roughly right" is how a worktop gets ordered 200mm short.
    await expect(page.getByText('4000 mm').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('3000 mm').first()).toBeVisible();
  });

  test('a design survives a reload', async ({ page }) => {
    await openDesigner(page);

    const combobox = page.getByRole('combobox').first();
    await expect(combobox).toBeVisible({ timeout: 20_000 });
    // Pressing through the locator, not page.keyboard: the page-level keyboard
    // waits on page state, and this layout's dev-ingest fetch never resolves,
    // so under load that wait can outlive the whole test.
    await combobox.press('Enter');
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    const chosen = ((await option.textContent()) ?? '').split('\u00b7')[0].trim();
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));

    // Wait for the box to exist before saving. Saving mid-write is a no-op -
    // the button is disabled while the line request is in flight - and a
    // synthetic click on a disabled button fails silently, which looks exactly
    // like a broken save.
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 30_000 });

    // The line comes back from the SERVER, so its presence proves the write
    // landed rather than that local state changed (AC-T3).
    const saved = page.waitForResponse(
      (response) =>
        /\/dealer-kit\/selections\/[^/]+\/room$/.test(response.url()) && response.ok(),
    );
    await tap(page, page.getByRole('button', { name: /save design/i }));
    const body = await (await saved).json();
    expect(body.roomAreaSqm).toBe(12);
    expect(body.lines.length).toBeGreaterThan(0);
    // A line never carries a price of its own - it is resolved per viewer.
    expect(body.lines[0]).not.toHaveProperty('unitPrice');

    await page.reload({ waitUntil: 'commit' });
    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    // Reopened from the server, not from memory: the product is still there.
    // Targeted at the panel row rather than any text match - the plan box
    // carries an SVG <title> with the same label for its hover tooltip, and a
    // loose getByText picks that hidden node first.
    await expect(
      page.getByRole('button', { name: `Select ${chosen}` }).first(),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 20_000 });
  });

});

// A separate describe with test.use: setViewportSize mid-test wedges against
// the protected layout's never-resolving dev-ingest fetch, which is why the
// builder spec does it this way too.
test.describe('Dealer Kit room designer at 375px', () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test('does not scroll the body sideways', async ({ page }) => {
    await login(page);
    await page.goto('/dealer-kit/design', { waitUntil: 'commit' });

    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
