import { test, expect, type Page } from '@playwright/test';

/**
 * Screenshot walkthrough for the product team.
 *
 * Seeds realistically-named content, photographs each screen, then deletes
 * exactly what it created. The dev database is a copy of production, so this
 * must not leave demo rows behind.
 */
const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL!;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD!;
const OUT = '/tmp/dk-shots';
const API = 'http://localhost:8020';

test.skip(!EMAIL || !PASSWORD, 'creds required');
test.setTimeout(600_000);

async function tap(page: Page, locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 30_000 });
  await locator.dispatchEvent('click');
}

async function type(locator: ReturnType<Page['locator']>, value: string) {
  await expect(locator).toBeVisible({ timeout: 30_000 });
  await locator.evaluate((el, v) => {
    const field = el as HTMLInputElement | HTMLTextAreaElement;
    const proto =
      field instanceof window.HTMLTextAreaElement
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(field, v);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

async function shot(page: Page, name: string) {
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

test('demo walkthrough', async ({ page }) => {
  const createdPages: string[] = [];
  const createdSelections: string[] = [];
  page.on('response', async (r) => {
    const url = r.url();
    if (r.request().method() !== 'POST' || r.status() >= 300) return;
    try {
      if (/\/dealer-kit\/pages$/.test(url)) createdPages.push((await r.json()).id);
      if (/\/dealer-kit\/selections$/.test(url)) createdSelections.push((await r.json()).id);
    } catch { /* not json */ }
  });

  // --- sign in ---
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 30_000 });
  await email.fill(EMAIL);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((u) => !/\/sign-?in/.test(u.toString()), { timeout: 60_000 });

  // --- sidebar ---
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group).toBeVisible({ timeout: 30_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') await group.dispatchEvent('click');
  await shot(page, '01-sidebar');

  // --- build a catalogue page ---
  await page.goto('/dealer-kit', { waitUntil: 'commit' });
  await tap(page, page.getByRole('button', { name: /new page/i }).first());
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 20_000 });
  await type(page.getByLabel('Name'), 'Sorento Bathroom Collection 2026');
  await tap(page, page.getByRole('button', { name: /create page/i }));
  await expect(page.getByRole('heading', { name: /page builder/i })).toBeVisible({ timeout: 40_000 });

  await tap(page, page.getByRole('button', { name: /add section/i }));
  await tap(page, page.getByRole('button', { name: /^heading$/i }));
  await type(page.getByLabel('Block text'), 'Bathroom Collection 2026');
  await page.waitForTimeout(600);
  await shot(page, '02-editor-heading');

  await tap(page, page.getByRole('button', { name: /^products$/i }));
  await tap(page, page.getByRole('button', { name: /choose products/i }));
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout: 20_000 });
  await shot(page, '03-product-picker');

  const byHand = dialog.getByRole('tab', { name: /by hand/i });
  const box = await byHand.boundingBox();
  if (box) await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const rows = dialog.getByRole('button', { name: /^include /i });
  await expect(rows.first()).toBeVisible({ timeout: 40_000 });
  for (const i of [0, 1, 2, 3]) await rows.nth(i).dispatchEvent('click');
  await shot(page, '04-picker-chosen');
  await tap(page, dialog.getByRole('button', { name: /use these products/i }));
  await expect(page.locator('[data-dk-tile-grid]')).toBeVisible({ timeout: 40_000 });
  await shot(page, '05-editor-with-products');

  await tap(page, page.getByRole('button', { name: /^save$/i }));
  await page.waitForTimeout(1500);
  await tap(page, page.getByRole('button', { name: /publish/i }));
  await page.waitForTimeout(2500);
  await shot(page, '06-editor-published');

  // --- the public catalogue, as a customer sees it ---
  await page.goto('/dealer-kit', { waitUntil: 'commit' });
  await page.waitForTimeout(2500);
  await shot(page, '07-pages-list');
  const address = await page.locator('td, div').filter({ hasText: /^\/c\// }).first().textContent();
  if (address) {
    await page.goto(address.trim(), { waitUntil: 'commit' });
    await page.waitForTimeout(3000);
    await shot(page, '08-public-catalogue');
  }

  // --- the room designer ---
  await page.goto('/dealer-kit/design', { waitUntil: 'commit' });
  const combobox = page.getByRole('combobox').first();
  await expect(combobox).toBeVisible({ timeout: 40_000 });
  for (let i = 0; i < 3; i += 1) {
    await combobox.press('Enter');
    const option = page.getByRole('option').nth(i);
    await expect(option).toBeVisible({ timeout: 30_000 });
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));
    await page.waitForTimeout(2500);
  }
  await shot(page, '09-designer-plan');

  const planTab = page.getByRole('tab', { name: /^plan$/i });
  await planTab.press('ArrowRight');
  await page.waitForTimeout(3500);
  await shot(page, '10-designer-3d');

  await tap(page, page.getByRole('button', { name: /save design/i }));
  await page.waitForTimeout(2500);
  await shot(page, '11-designer-saved');

  // --- phone width ---
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dealer-kit/design', { waitUntil: 'commit' });
  await page.waitForTimeout(3000);
  await shot(page, '12-designer-phone');

  // --- delete exactly what was created ---
  const token = (await (await page.request.get('/api/auth/token')).json()).token;
  const auth = { Authorization: `Bearer ${token}` };
  for (const id of new Set(createdSelections)) {
    await page.request.delete(`${API}/api/v1/dealer-kit/selections/${id}`, { headers: auth });
  }
  for (const id of new Set(createdPages)) {
    await page.request.delete(`${API}/api/v1/dealer-kit/pages/${id}`, { headers: auth });
  }
  console.log(`CLEANED pages=${createdPages.length} selections=${createdSelections.length}`);
});
