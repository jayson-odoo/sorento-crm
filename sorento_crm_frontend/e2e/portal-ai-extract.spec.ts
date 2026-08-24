/**
 * AI Extract end-to-end against the running stack.
 *
 * Prerequisites (driven by env vars):
 *   PORTAL_E2E_BASE_URL    base URL of the Next.js portal (default http://localhost:3000)
 *   PORTAL_E2E_TOKEN       a valid X-Portal-Token for an already-onboarded portal contact
 *
 * Backend prerequisites:
 * - sorento_crm_backend running with valid AIAssistantConfig.api_key_ciphertext
 *     (provider can be 'openai' or 'anthropic'; the spec runs identically for both).
 * - PyMuPDF installed in the backend venv.
 *
 * The fixtures committed in e2e/fixtures/ai-extract/ are:
 * - image-01.png … image-07.png  (defect photos / DO screenshots / message captures)
 * - PS202603-0071_WATER_CARE.pdf
 * - 20260415153447847.pdf
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';

const FIXTURES = path.resolve(__dirname, 'fixtures', 'ai-extract');
const FIXTURE_FILES = [
  'image-01.png',
  'image-02.png',
  'image-03.png',
  'image-04.png',
  'image-05.png',
  'image-06.png',
  'image-07.png',
  'PS202603-0071_WATER_CARE.pdf',
  '20260415153447847.pdf',
].map((f) => path.join(FIXTURES, f));

const TOKEN = process.env.PORTAL_E2E_TOKEN;

test.describe('Portal AI Extract', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(
      !TOKEN,
      'Set PORTAL_E2E_TOKEN to a valid portal token to run the AI Extract e2e.',
    );
    await seedPortalToken(page, TOKEN!);
  });

  test('drag samples → extract → review → confirm prefills the complaint form', async ({ page }) => {
    await page.goto('/portal/complaint/new');
    await expect(page.getByTestId('ai-extract-trigger')).toBeVisible();

    await page.getByTestId('ai-extract-trigger').click();
    await expect(page.getByTestId('ai-extract-dialog')).toBeVisible();

    await page.getByTestId('ai-extract-file-input').setInputFiles(FIXTURE_FILES);

    await page.getByTestId('ai-extract-run').click();

    await expect(page.getByTestId('ai-extract-review')).toBeVisible({
      timeout: 90_000,
    });

    // High-confidence assertions: at least one of the expected DO numbers
    // should appear in the extracted delivery_order_number row.
    const doRow = page.getByTestId('ai-extract-field-delivery_order_number');
    await expect(doRow).toBeVisible();
    const doText = (await doRow.textContent()) ?? '';
    expect(/PS202603-0071|PO2509-013/.test(doText)).toBeTruthy();

    // Customer name and address should be non-empty when the model picked them up.
    const optional = ['customer_name', 'customer_address', 'product_code', 'defect_description'] as const;
    for (const f of optional) {
      const row = page.getByTestId(`ai-extract-field-${f}`);
      if (await row.isVisible()) {
        const txt = ((await row.textContent()) ?? '').trim();
        expect(txt.length).toBeGreaterThan(0);
      }
    }

    // Drop salesperson if it was guessed (rarely correct from an arbitrary photo).
    const salesperson = page.getByTestId('ai-extract-field-salesperson');
    if (await salesperson.isVisible()) {
      await page.getByTestId('ai-extract-drop-salesperson').click();
      await expect(salesperson).toHaveCount(0);
    }

    await page.getByTestId('ai-extract-confirm').click();
    await expect(page.getByTestId('ai-extract-dialog')).toHaveCount(0);

    // After confirm, the live form should now have a non-empty defect description.
    const description = page.getByLabel(/Defect description/i);
    if (await description.isVisible()) {
      await expect(description).not.toHaveValue('');
    }
  });
});

async function seedPortalToken(page: Page, token: string) {
  await page.addInitScript((t: string) => {
    try {
      window.sessionStorage.setItem('sorento.portalToken', t);
    } catch {
      // Some browsers throw when sessionStorage is locked down; ignore in init.
    }
  }, token);
}
