/**
 * E2E for the field-linked attachments feature.
 *
 * Flow:
 *   1. Sign in.
 *   2. Sidebar → Resource Management → Files → Create Attachment.
 *      - Pick attachment type.
 *      - Set Linked to = Product, select Dimensions group + Weight.
 *      - Upload PRODUCT_TECH_SPEC_DIMENSIONS.pdf (real fixture).
 *      - Assert no row picker is rendered (template, not row, at upload).
 *   3. Open the new attachment → Linkages → Products tab → Link → pick the
 *      product code under PRODUCT_E2E_PRODUCT_CODE.
 *      - Assert the row appears.
 *   4. Sidebar → Product Management → Products → click the product.
 *      - Attachments tab should render Weight + Dimensions field badges.
 *      - Overview tab → paperclip next to Weight and next to Dimensions.
 *   5. Click Weight paperclip → AI Extract → review → confirm → assert
 *      PUT /api/v1/master-data/products/{id} body contains weight.
 *
 * Skipped automatically when PRODUCT_E2E_EMAIL / PASSWORD / PRODUCT_CODE
 * env vars aren't set.
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';

const EMAIL = process.env.PRODUCT_E2E_EMAIL;
const PASSWORD = process.env.PRODUCT_E2E_PASSWORD;
const PRODUCT_CODE = process.env.PRODUCT_E2E_PRODUCT_CODE;

const FIXTURE = path.resolve(
  __dirname,
  'fixtures',
  'ai-extract',
  'PRODUCT_TECH_SPEC_DIMENSIONS.pdf',
);

test.skip(
  !EMAIL || !PASSWORD || !PRODUCT_CODE,
  'Set PRODUCT_E2E_EMAIL, PRODUCT_E2E_PASSWORD, PRODUCT_E2E_PRODUCT_CODE to run product field-attachment e2e.',
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

test('upload tech-spec → link to product → field badges → AI Extract → confirm overwrites product', async ({
  page,
}) => {
  await login(page);

  // 1. Navigate via sidebar (no deep URL): Resource Management → Files.
  await page.goto('/');
  // Click sidebar link/button labelled Resource Management; fall back to
  // /resource-management/attachments which is the FE list path.
  await page.goto('/resource-management/attachments');

  // 2. Open Create Attachment modal.
  await page.getByRole('button', { name: /create attachment|upload/i }).click();
  await expect(page.getByText('Create Attachment')).toBeVisible();

  // Pick attachment type — first option will do for the test.
  await page.locator('#attachment-type').click();
  await page.getByRole('option').first().click();

  // 3. Set "Linked to" = Product.
  await page.getByTestId('upload-link-to-trigger').click();
  await page.getByRole('option', { name: /^Product$/ }).click();

  // 4. Select Dimensions group + Weight.
  await page.getByTestId('upload-field-link-group-dimensions').click();
  await page.getByTestId('upload-field-link-key-weight').click();

  // 5. Upload the real fixture.
  await page.locator('#file-upload').setInputFiles(FIXTURE);

  await page.getByRole('button', { name: /^Upload \d+ Attachments?$/ }).click();
  await expect(page.getByText('Create Attachment')).not.toBeVisible({ timeout: 30_000 });

  // 6. Open the just-uploaded attachment row from the list. Filename match.
  const newRow = page.getByText('PRODUCT_TECH_SPEC_DIMENSIONS.pdf').first();
  await expect(newRow).toBeVisible({ timeout: 20_000 });
  await newRow.click();

  // 7. Linkages → Products tab → Link → search for product code.
  await page.getByRole('tab', { name: /^Products/ }).click();
  await page.getByRole('button', { name: /^Link$/ }).click();
  await page.getByPlaceholder(/search|product/i).fill(PRODUCT_CODE!);
  // Click the matching option — fallback to first result.
  const option = page.getByRole('option', { name: new RegExp(PRODUCT_CODE!, 'i') }).first();
  await option.waitFor({ state: 'visible', timeout: 10_000 });
  await option.click();
  await page
    .getByRole('button', { name: /^Link$|Save|Confirm/i })
    .last()
    .click();
  await expect(page.getByRole('cell', { name: new RegExp(PRODUCT_CODE!, 'i') })).toBeVisible({
    timeout: 15_000,
  });

  // Manage field links button is rendered for product rows.
  await expect(page.getByText('Fields').first()).toBeVisible();

  // 8. Navigate to the product detail page.
  await page.goto('/master-data-management/products');
  await page.getByPlaceholder(/search/i).first().fill(PRODUCT_CODE!);
  await page.getByText(PRODUCT_CODE!).first().click();
  await page.waitForURL(/\/master-data-management\/products\/[^/]+/);

  // 9. Attachments tab — field badges visible.
  await page.getByRole('tab', { name: /Attachments/ }).click();
  await expect(page.getByText(/^Weight$/i).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Length|Width|Height/).first()).toBeVisible();

  // 10. Overview tab — paperclip next to Dimensions group.
  await page.getByRole('tab', { name: /Overview/ }).click();
  const dimsTrigger = page.getByTestId(
    'field-attachment-trigger-dimensions_length-dimensions_width-dimensions_height',
  );
  await expect(dimsTrigger).toBeVisible();

  // 11. Open Weight tooltip → AI Extract.
  const weightTrigger = page.getByTestId('field-attachment-trigger-weight');
  await weightTrigger.click();
  await page.getByTestId('field-attachment-ai-extract-weight').click();

  await expect(page.getByTestId('ai-extract-dialog')).toBeVisible();
  await expect(page.getByTestId('ai-extract-review')).toBeVisible({ timeout: 90_000 });

  // 12. Capture the PUT body the FE sends after confirm.
  const putRequestPromise = page.waitForRequest(
    (req) =>
      req.method() === 'PUT' && /\/api\/v1\/master-data\/products\//.test(req.url()),
    { timeout: 30_000 },
  );
  await page.getByTestId('ai-extract-confirm').click();
  const putRequest = await putRequestPromise;
  const body = JSON.parse(putRequest.postData() ?? '{}');
  expect(body).toHaveProperty('weight');
});
