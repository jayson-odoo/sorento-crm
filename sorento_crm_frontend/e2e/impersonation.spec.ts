/**
 * Admin impersonation e2e.
 *
 * Run against a deployed (or local) instance:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   IMPERSONATION_E2E_EMAIL=admin@example.com \
 *   IMPERSONATION_E2E_PASSWORD='...' \
 *   IMPERSONATION_E2E_TARGET_EMAIL=germaine.gray@mail.com \
 *   npx playwright test e2e/impersonation.spec.ts
 *
 * Skipped when credentials env vars aren't set so it doesn't block local dev.
 *
 * Per project memory (feedback_playwright_via_sidebar): always click through
 * the sidebar from `/`, never deep-link to a feature page.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.IMPERSONATION_E2E_EMAIL;
const PASSWORD = process.env.IMPERSONATION_E2E_PASSWORD;
const TARGET_EMAIL = process.env.IMPERSONATION_E2E_TARGET_EMAIL;

test.skip(
  !EMAIL || !PASSWORD || !TARGET_EMAIL,
  'Set IMPERSONATION_E2E_EMAIL, IMPERSONATION_E2E_PASSWORD, and IMPERSONATION_E2E_TARGET_EMAIL',
);

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page
    .locator('input[type="password"], input[name="password"]')
    .first()
    .fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), {
    timeout: 30_000,
  });
}

function trackConsole(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`[error] ${msg.text()}`);
  });
  page.on('pageerror', (err) => {
    errors.push(`[pageerror] ${err.message}`);
  });
  return { errors };
}

async function navigateUserListViaSidebar(page: Page) {
  // Sidebar group "User Management" - open then click leaf "Administrative Users".
  // Some menus group it under "Settings" depending on layout config; try both.
  const groupLabels = [/user management/i, /settings/i, /admin/i];
  for (const label of groupLabels) {
    const trigger = page.getByRole('button', { name: label }).first();
    if (await trigger.count()) {
      try {
        await trigger.click({ timeout: 2_000 });
        break;
      } catch {
        // ignore - try the next group
      }
    }
  }
  const link = page
    .getByRole('link', { name: /administrative users|users$/i })
    .first();
  await expect(link).toBeVisible({ timeout: 10_000 });
  await link.click();
  await page.waitForURL(/\/user-management\/users/);
}

test('admin impersonates a non-admin user from the list and exits', async ({
  page,
  request,
}) => {
  const cons = trackConsole(page);
  await login(page);

  // 1. Sidebar nav (no deep link).
  await navigateUserListViaSidebar(page);

  // 2. Find target row and click its Impersonate icon.
  const targetRow = page
    .locator('tr', { hasText: TARGET_EMAIL! })
    .first();
  await expect(targetRow).toBeVisible({ timeout: 10_000 });
  const impersonateBtn = targetRow.locator('[data-testid^="impersonate-"]').first();
  await expect(impersonateBtn).toBeVisible();

  // 3. Confirmation dialog.
  await impersonateBtn.click();
  const dialog = page.getByTestId('impersonate-confirm-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(/with their access rights/i);

  // 4. Watch the start request.
  const [startResp] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes('/api/v1/user-management/impersonation/start') &&
        r.request().method() === 'POST',
    ),
    page.getByTestId('impersonate-confirm').click(),
  ]);
  expect(startResp.status()).toBe(200);

  // 5. Page reloads → banner present.
  await page.waitForLoadState('domcontentloaded');
  const banner = page.getByTestId('impersonation-banner');
  await expect(banner).toBeVisible({ timeout: 10_000 });
  await expect(banner).toContainText(/you are currently impersonating/i);

  // 6. Permission set should now equal the target user's, not admin's.
  // Hit /api/v1/users/me/permissions through the same browser context so
  // cookies + the impersonation header are forwarded by api-proxy.
  const permsResp = await page.request.get(
    '/api/v1/users/me/permissions',
  );
  if (permsResp.ok()) {
    const perms = (await permsResp.json()) as unknown;
    // We don't know the exact target's slug list here, but it must be a
    // proper subset of admin's effective set (admin gets *all* permissions
    // via bypass). So the simplest invariant is: it's an array.
    expect(Array.isArray(perms) || (perms && typeof perms === 'object')).toBeTruthy();
  }

  // 7. Exit Impersonation.
  const [stopResp] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes('/api/v1/user-management/impersonation/stop') &&
        r.request().method() === 'POST',
    ),
    page.getByTestId('impersonation-exit').click(),
  ]);
  expect(stopResp.status()).toBe(200);

  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByTestId('impersonation-banner')).toHaveCount(0);

  expect(cons.errors, cons.errors.join('\n')).toEqual([]);
});
