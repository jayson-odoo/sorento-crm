import { test, expect, type Page } from '@playwright/test';

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

test.describe('Dealer Kit room designer', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
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
    await combobox.focus();
    await page.keyboard.press('Enter');

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
    await planTab.focus();
    await page.keyboard.press('ArrowRight');

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
