/**
 * Complaint Management e2e - verifies the new master data (root causes,
 * resolutions) under Complaint Management, plus the notify-salesperson buttons
 * on the complaint detail view.
 *
 * Run against a local stack with Phase 175 migration applied:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   COMPLAINT_E2E_EMAIL=admin@example.com \
 *   COMPLAINT_E2E_PASSWORD='...' \
 *   npx playwright test e2e/complaint-master-data-and-notify.spec.ts
 *
 * Skipped automatically when credentials env vars aren't set so it doesn't
 * block local dev. Per project memory rules every navigation goes through the
 * sidebar - no deep `page.goto('/complaint-management/...')`.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.COMPLAINT_E2E_EMAIL ?? process.env.TICKETS_E2E_EMAIL;
const PASSWORD = process.env.COMPLAINT_E2E_PASSWORD ?? process.env.TICKETS_E2E_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  'Set COMPLAINT_E2E_EMAIL and COMPLAINT_E2E_PASSWORD (or TICKETS_E2E_* fallback) to run',
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

async function expandComplaintGroup(page: Page) {
  const group = page.getByRole('button', { name: /complaint management/i }).first();
  await group.scrollIntoViewIfNeeded();
  await group.click().catch(() => {
    // already expanded
  });
}

function trackConsole(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      errors.push(`[${msg.type()}] ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => {
    errors.push(`[pageerror] ${err.message}`);
  });
  return { errors };
}

test('sidebar exposes Root Causes and Resolutions under Complaint Management', async ({
  page,
}) => {
  await login(page);
  await page.goto('/');
  await expandComplaintGroup(page);
  await expect(page.getByRole('link', { name: 'Root Causes' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Resolutions' })).toBeVisible();
});

test('CRUD a complaint root cause through the sidebar', async ({ page }) => {
  const cons = trackConsole(page);
  await login(page);
  await page.goto('/');
  await expandComplaintGroup(page);

  await page.getByRole('link', { name: 'Root Causes' }).click();
  await page.waitForURL(/\/complaint-management\/complaint-root-causes$/, {
    timeout: 15_000,
  });
  await expect(
    page.getByRole('heading', { name: 'Root Causes' }).first(),
  ).toBeVisible({ timeout: 15_000 });

  const name = `E2E Root Cause ${Date.now()}`;
  await page.getByRole('button', { name: /add root cause/i }).click();
  await page.getByLabel('Name *').fill(name);
  await page.getByLabel('Description').fill('Created by Playwright e2e');
  await page.getByRole('button', { name: 'Create' }).click();

  await expect(page.getByText('Root cause created')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(name)).toBeVisible({ timeout: 15_000 });

  // Edit: toggle inactive.
  const row = page.locator('tr', { hasText: name }).first();
  await row.getByRole('button', { name: /^edit$/i }).click();
  await page.getByLabel('Description').fill('Updated by Playwright e2e');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('Root cause updated')).toBeVisible({ timeout: 10_000 });

  // Delete via ConfirmDeleteDialog.
  await row.getByRole('button', { name: /^delete$/i }).click();
  await expect(page.getByText('Confirm delete')).toBeVisible();
  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Root cause deleted')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(name)).toHaveCount(0, { timeout: 10_000 });

  expect(cons.errors).toEqual([]);
});

test('CRUD a complaint resolution through the sidebar', async ({ page }) => {
  const cons = trackConsole(page);
  await login(page);
  await page.goto('/');
  await expandComplaintGroup(page);

  await page.getByRole('link', { name: 'Resolutions' }).click();
  await page.waitForURL(/\/complaint-management\/complaint-resolutions$/, {
    timeout: 15_000,
  });
  await expect(
    page.getByRole('heading', { name: 'Resolutions' }).first(),
  ).toBeVisible({ timeout: 15_000 });

  const name = `E2E Resolution ${Date.now()}`;
  await page.getByRole('button', { name: /add resolution/i }).click();
  await page.getByLabel('Name *').fill(name);
  await page.getByLabel('Description').fill('Created by Playwright e2e');
  await page.getByRole('button', { name: 'Create' }).click();

  await expect(page.getByText('Resolution created')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(name)).toBeVisible({ timeout: 15_000 });

  const row = page.locator('tr', { hasText: name }).first();
  await row.getByRole('button', { name: /^delete$/i }).click();
  await expect(page.getByText('Confirm delete')).toBeVisible();
  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Resolution deleted')).toBeVisible({ timeout: 10_000 });

  expect(cons.errors).toEqual([]);
});

/**
 * Notify-salesperson + approval-triggers-email flows depend on the test
 * environment having (a) a complaint already in `responded` status with a
 * `respond_inbox_url`, and (b) a `complaint_approved` automation seeded with
 * an EmailTemplate. Those prerequisites are out of scope for this spec; cover
 * them via direct backend pytest (see
 * `sorento_crm_backend/tests/test_complaint_notify_endpoints.py` and
 * `tests/test_complaint_approval_dispatches_automation.py`).
 */
test('detail view renders Root Cause + Resolution sections (always rendered)', async ({
  page,
}) => {
  await login(page);
  await page.goto('/');
  await expandComplaintGroup(page);
  await page.getByRole('link', { name: 'Complaints' }).click();
  await page.waitForURL(/\/complaint-management\/complaints$/, { timeout: 15_000 });

  const firstRow = page.locator('table tbody tr').first();
  if ((await firstRow.count()) === 0) {
    test.skip(true, 'No complaints seeded; skipping detail-view assertion.');
    return;
  }
  await firstRow.click();
  await page.waitForURL(/\/complaint-management\/complaints\/[^/]+$/, {
    timeout: 15_000,
  });

  // Both sections render even when the FK is unset - per ADR product standard.
  await expect(page.getByText('Root Cause', { exact: true })).toBeVisible();
  await expect(page.getByText('Resolution', { exact: true })).toBeVisible();
  // Two "Notify salesperson" buttons exist.
  const notifyButtons = page.getByRole('button', { name: /notify salesperson/i });
  await expect(notifyButtons).toHaveCount(2);
});
