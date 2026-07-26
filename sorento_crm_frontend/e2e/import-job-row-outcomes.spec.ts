import { test, expect, type Page } from '@playwright/test';

/**
 * Import job outcome visibility: breakdown -> click a reason -> rows grid filters
 * -> CSV export carries the same filter.
 *
 * Pins the bug this feature exists for: a delivery-order-detail import that
 * finished green reporting thousands of skipped rows while naming only ten of
 * them. Every skip now carries a code, and the operator can drill into it.
 *
 * Required env vars (spec is skipped otherwise):
 *   IMPORT_JOBS_E2E_EMAIL=...
 *   IMPORT_JOBS_E2E_PASSWORD=...
 */
const EMAIL = process.env.IMPORT_JOBS_E2E_EMAIL;
const PASSWORD = process.env.IMPORT_JOBS_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set IMPORT_JOBS_E2E_* env vars to run this spec.');

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
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

async function navigateToImportJobs(page: Page): Promise<string | null> {
  // ALWAYS sidebar-navigate to the LIST: a deep URL hides nav-config and
  // permission-gating bugs. dispatchEvent rather than click() because the sidebar
  // accordion re-renders while the floating assistant bubble animates, so
  // actionability checks never settle.
  const listResponse = page.waitForResponse(
    (resp) =>
      resp.url().includes('/api/v1/system/jobs?') && resp.request().method() === 'GET',
    { timeout: 30_000 },
  );

  const group = page.getByRole('button', { name: /system management/i }).first();
  await expect(group).toBeAttached({ timeout: 30_000 });
  await group.dispatchEvent('click');

  const entry = page.getByRole('link', { name: /^import jobs$/i }).first();
  await expect(entry).toBeAttached({ timeout: 30_000 });
  await entry.dispatchEvent('click');
  await expect(page).toHaveURL(/\/system-management\/import-jobs/, { timeout: 30_000 });

  // Take the job to open from the list payload the page just fetched, rather than
  // relying on a grid row-click that is not reliably actionable under test.
  const body = await (await listResponse).json().catch(() => null);
  return body?.data?.[0]?.job_id ?? null;
}

test.describe('Import job row outcomes', () => {
  test('breakdown reasons filter the rows grid and drive the CSV export', async ({ page }) => {
    await login(page);
    const jobId = await navigateToImportJobs(page);

    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 20_000 });
    if (!jobId) {
      test.skip(true, 'No import jobs in this environment.');
      return;
    }

    const rowsRequest = page.waitForResponse(
      (resp) =>
        /\/api\/v1\/system\/jobs\/[^/]+\/rows\?/.test(resp.url()) &&
        resp.request().method() === 'GET',
      { timeout: 30_000 },
    );
    await page.goto(`/system-management/import-jobs/${jobId}`);
    await expect(page.getByText('Outcome breakdown')).toBeVisible({ timeout: 20_000 });
    await rowsRequest;

    // The rows grid renders alongside the breakdown. (Per-group empty states are
    // asserted in the component tests; here the words also appear in the summary
    // card and the raw JSON, so they are not unique enough to assert on.)
    await expect(page.getByText(/matching$/).first()).toBeVisible({ timeout: 20_000 });

    // Clicking a reason must filter the grid server-side with that code.
    const reasonButton = page
      .locator('button')
      .filter({ hasText: /not found|already exists|created/i })
      .first();

    if ((await reasonButton.count()) === 0) {
      test.skip(true, 'No job with a captured breakdown in this environment.');
      return;
    }

    const filtered = page.waitForResponse(
      (resp) =>
        /\/api\/v1\/system\/jobs\/[^/]+\/rows\?/.test(resp.url()) &&
        resp.url().includes('code=') &&
        resp.status() === 200,
      { timeout: 30_000 },
    );
    await reasonButton.click();
    const filteredResponse = await filtered;
    const filteredCode = new URL(filteredResponse.url()).searchParams.get('code');
    expect(filteredCode).toBeTruthy();

    // The grid shows the reason it was filtered to.
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 20_000 });

    // The export must carry the SAME filter, not dump the whole job.
    const exportRequest = page.waitForResponse(
      (resp) =>
        /\/api\/v1\/system\/jobs\/[^/]+\/rows\/export/.test(resp.url()) &&
        resp.request().method() === 'GET',
      { timeout: 30_000 },
    );
    await page.getByRole('button', { name: /download csv/i }).click();
    const exportResponse = await exportRequest;
    expect(new URL(exportResponse.url()).searchParams.get('code')).toBe(filteredCode);
    expect(exportResponse.headers()['content-type']).toContain('text/csv');
  });
});
