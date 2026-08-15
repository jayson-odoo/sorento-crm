/**
 * Customer importer e2e (documentation/plans/PLAN-customer-importer.md).
 *
 * The whole journey, FE -> BE -> DB, against a real committed debtor-listing fixture:
 *   1. Sidebar -> Order Management -> Customers (never a deep link: a direct URL hides
 *      a missing nav entry, a wrong moduleKey and broken permission gating).
 *   2. Import -> choose the workbook -> Test. The dry run POSTs
 *      `/customers/import?validate_only=true` and reports the counts.
 *   3. Confirm queues the job (202) and the upload drawer opens on it.
 *   4. The job reaches a terminal state on the import-jobs detail page with per-row
 *      outcomes, and the imported customers are searchable in the list.
 *
 * The fixture is a real export shape, title lines and all, and deliberately carries the
 * two cases that matter: ONE code under two different debtor names (which must produce
 * two rows, not one), and a row with no name (which must be skipped while the rest of
 * the file still imports).
 *
 * Run against a local stack (backend + RQ worker must both be up - the import runs ONLY
 * on the worker):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   CUSTOMER_IMPORT_E2E_EMAIL=admin@example.com \
 *   CUSTOMER_IMPORT_E2E_PASSWORD='...' \
 *   npx playwright test e2e/customer-import.spec.ts
 *
 * Skipped automatically when the credentials env vars aren't set.
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';

const EMAIL = process.env.CUSTOMER_IMPORT_E2E_EMAIL ?? process.env.TICKETS_E2E_EMAIL;
const PASSWORD = process.env.CUSTOMER_IMPORT_E2E_PASSWORD ?? process.env.TICKETS_E2E_PASSWORD;

const FIXTURE = path.join(__dirname, 'fixtures', 'debtor-listing.xlsx');

test.skip(
  !EMAIL || !PASSWORD,
  'Set CUSTOMER_IMPORT_E2E_EMAIL and CUSTOMER_IMPORT_E2E_PASSWORD (or TICKETS_E2E_* fallback) to run',
);

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

test('a debtor listing imports from the customers list', async ({ page }) => {
  test.setTimeout(240_000);
  await login(page);

  // 1. Sidebar navigation, so a missing or mis-gated menu entry fails here.
  const group = page.getByRole('button', { name: /order management/i }).first();
  await group.scrollIntoViewIfNeeded();
  await group.click();
  await page.getByRole('link', { name: 'Customers', exact: true }).click();
  await page.waitForURL(/\/order-management\/customers/, { timeout: 30_000 });

  // 2. Test: reads the file, writes nothing.
  await page.getByRole('button', { name: 'Import', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: /import customers/i });
  await expect(dialog).toBeVisible();

  await dialog.locator('input[type="file"]').setInputFiles(FIXTURE);

  const dryRun = page.waitForResponse(
    (r) =>
      r.url().includes('/order-management/customers/import') &&
      r.url().includes('validate_only=true') &&
      r.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: /^Test/ }).click();
  expect((await dryRun).status()).toBe(200);
  await expect(dialog.getByText('New customers')).toBeVisible();

  // 3. Confirm: the queue accepts it and the drawer opens on the job.
  const queued = page.waitForResponse(
    (r) =>
      r.url().includes('/order-management/customers/import') &&
      !r.url().includes('validate_only') &&
      r.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: /^Confirm/ }).click();
  // The row with no name is a warning, not a block: acknowledge it.
  const acknowledge = page.getByRole('button', { name: 'Import anyway' });
  if (await acknowledge.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await acknowledge.click();
  }
  const queuedResponse = await queued;
  expect(queuedResponse.status()).toBe(202);
  const jobId = (await queuedResponse.json()).job_id as string;

  // 4. The job finishes, and says what it did per row.
  await page.goto(`/system-management/import-jobs/${jobId}`);
  await expect(page.getByText(/finished|completed/i).first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/Missing required field/i).first()).toBeVisible();

  // One code, two debtor names: TWO rows, because the name is half the key.
  await page.goto('/order-management/customers');
  await page.getByPlaceholder(/search customers/i).fill('E2E Deluxe Home Center');
  await expect(page.getByText('E2E Deluxe Home Center (KTN)')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('E2E Deluxe Home Center AC (I)')).toBeVisible();

  // The nameless row was skipped, so its code never became a customer.
  await page.getByPlaceholder(/search customers/i).fill('E2E-302-S008');
  await expect(page.getByText('E2E-302-S008')).toHaveCount(0);
});
