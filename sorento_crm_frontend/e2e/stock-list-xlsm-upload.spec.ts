/**
 * Stock List `.xlsm` macro upload e2e
 * (docs/plans/PLAN-stock-list-xlsm-macro-upload.md).
 *
 * Exercises the FE→BE→storage round-trip with the real macro workbook fixture
 * (3 sheets: "Active Loc", "Master", "Template"):
 *   1. Inventory Management → Stock (sidebar-navigated, never deep-linked)
 *   2. Import the .xlsm - the dialog must parse the "Template" sheet (not
 *      sheet 0) and POST /api/v1/inventory/stock/bulk-import +
 *      /api/v1/resource-management/attachments/replace-latest-stock-list.
 *   3. The "Stock List" button links to the new attachment; the detail page
 *      shows the converted `.xlsx` name.
 *   4. Download the attachment and assert the workbook is macro-free and
 *      contains ONLY the Template sheet with the expected headers.
 *
 * Run against a local stack:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   STOCK_E2E_EMAIL=admin@example.com \
 *   STOCK_E2E_PASSWORD='...' \
 *   npx playwright test e2e/stock-list-xlsm-upload.spec.ts
 *
 * Skipped automatically when credentials env vars aren't set.
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const EMAIL = process.env.STOCK_E2E_EMAIL ?? process.env.TICKETS_E2E_EMAIL;
const PASSWORD = process.env.STOCK_E2E_PASSWORD ?? process.env.TICKETS_E2E_PASSWORD;

const FIXTURE = path.join(__dirname, 'fixtures', 'stock balance - Macro Version.xlsm');

test.skip(
  !EMAIL || !PASSWORD,
  'Set STOCK_E2E_EMAIL and STOCK_E2E_PASSWORD (or TICKETS_E2E_* fallback) to run',
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

test('macro stock upload converts to Template-only xlsx attachment', async ({ page }) => {
  test.setTimeout(180_000);
  await login(page);

  // Sidebar → Inventory Management → Stock
  const group = page.getByRole('button', { name: /inventory management/i }).first();
  await group.scrollIntoViewIfNeeded();
  await group.click();
  await page.getByRole('link', { name: 'Stock', exact: true }).click();
  await page.waitForURL(/\/inventory-management\/stock/, { timeout: 30_000 });

  // Import the macro workbook.
  await page.getByRole('button', { name: 'Import', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: /upload excel file/i });
  await expect(dialog).toBeVisible();

  const chooserPromise = page.waitForEvent('filechooser');
  await dialog.getByText(/choose file/i).click();
  const chooser = await chooserPromise;
  await chooser.setFiles(FIXTURE);

  const bulkImport = page.waitForResponse(
    (r) => r.url().includes('/api/v1/inventory/stock/bulk-import') && r.request().method() === 'POST',
    { timeout: 60_000 },
  );
  const replaceLatest = page.waitForResponse(
    (r) =>
      r.url().includes('/api/v1/resource-management/attachments/replace-latest-stock-list') &&
      r.request().method() === 'POST',
    { timeout: 60_000 },
  );
  await dialog.getByRole('button', { name: 'Upload', exact: true }).click();

  // Bulk import queues (202) - proves the dialog parsed the Template sheet,
  // since sheet 0 ("Active Loc") has no importable stock columns.
  expect((await bulkImport).status()).toBeLessThan(300);

  // Stock List attachment replaced with the converted workbook.
  const replaceResp = await replaceLatest;
  expect(replaceResp.status()).toBe(201);
  const attachment = await replaceResp.json();
  expect(attachment.original_filename).toBe('stock balance - Macro Version.xlsx');
  expect(attachment.mime_type).toContain('spreadsheetml.sheet');

  // Stock List button now links to the new attachment's detail page.
  const stockListLink = page.getByRole('link', { name: 'Stock List' });
  await expect(stockListLink).toHaveAttribute(
    'href',
    new RegExp(`/resource-management/attachments/${attachment.id}`),
    { timeout: 30_000 },
  );
  await stockListLink.click();
  await page.waitForURL(/\/resource-management\/attachments\//, { timeout: 30_000 });
  await expect(
    page.getByRole('heading', { name: 'stock balance - Macro Version.xlsx' }),
  ).toBeVisible({ timeout: 30_000 });

  // Download and verify: macro-free, Template sheet only, headers intact.
  const downloadPromise = page.waitForEvent('download', { timeout: 60_000 });
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  const download = await downloadPromise;
  const downloadedPath = await download.path();
  expect(downloadedPath).toBeTruthy();

  const xlsx = await import('xlsx');
  const wb = xlsx.read(fs.readFileSync(downloadedPath!), { type: 'buffer' });
  expect(wb.SheetNames).toEqual(['Template']);
  const rows = xlsx.utils.sheet_to_json<Record<string, unknown>>(wb.Sheets.Template);
  expect(rows.length).toBeGreaterThan(1000);
  expect(Object.keys(rows[0])).toEqual([
    'Item Code',
    'Item Description',
    'Location',
    'On Hand Qty',
  ]);
  // Raw zip must not carry a VBA project part.
  expect(fs.readFileSync(downloadedPath!).includes('vbaProject')).toBe(false);
});
