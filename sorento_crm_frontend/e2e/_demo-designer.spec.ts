import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL!;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD!;
const OUT = '/tmp/dk-shots';
const API = 'http://localhost:8020';

test.skip(!EMAIL || !PASSWORD, 'creds required');
test.setTimeout(420_000);

async function tap(page: Page, locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 30_000 });
  await locator.dispatchEvent('click');
}

async function shot(page: Page, name: string) {
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

test('designer shots', async ({ page }) => {
  const selections: string[] = [];
  page.on('response', async (r) => {
    if (r.request().method() === 'POST' && /\/dealer-kit\/selections$/.test(r.url()) && r.status() === 201) {
      try { selections.push((await r.json()).id); } catch { /* ignore */ }
    }
  });

  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 30_000 });
  await email.fill(EMAIL);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((u) => !/\/sign-?in/.test(u.toString()), { timeout: 60_000 });

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

  await page.getByRole('tab', { name: /^plan$/i }).press('ArrowRight');
  await page.waitForTimeout(4000);
  await shot(page, '10-designer-3d');

  await tap(page, page.getByRole('button', { name: /save design/i }));
  await page.waitForTimeout(2500);
  await shot(page, '11-designer-saved');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dealer-kit/design', { waitUntil: 'commit' });
  await page.waitForTimeout(3500);
  await shot(page, '12-designer-phone');

  const token = (await (await page.request.get('/api/auth/token')).json()).token;
  for (const id of new Set(selections)) {
    await page.request.delete(`${API}/api/v1/dealer-kit/selections/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }
  console.log(`CLEANED selections=${selections.length}`);
});
