/**
 * S3 - a consumer lodging a report, end to end through the real stack.
 *
 * The two halves of this spec are deliberately different in what they need.
 *
 * **The prototype route** (`/portal/lodge?scenario=`) needs nothing but a running frontend.
 * It walks the four extraction outcomes on mocks, and three of the four are ordinary traffic
 * rather than error paths: 68% of receipts resolve, 8% land mid-band, 24% print no usable
 * shop name. A flow that only demonstrates the first would look finished while failing a
 * quarter of real reports, so the unmatched path is exercised as a first-class case.
 *
 * **The live route** (`/portal/c/{slug}/lodge`) needs a real portal token and the backend,
 * and it is what proves the FE -> BE -> DB round trip: a real dealer match against the real
 * customer table, and a complaint number handed back.
 *
 * Prerequisites:
 *   PORTAL_E2E_BASE_URL   default http://localhost:3000
 *   PORTAL_E2E_TOKEN      a valid X-Portal-Token for an onboarded contact (live half only)
 *   PORTAL_E2E_SLUG       that contact's portal slug (live half only)
 *
 * The live half SKIPS rather than fails without those, matching the other portal specs:
 * a spec that cannot run is not a spec that found a bug.
 */
import { test, expect, Page } from '@playwright/test';
import path from 'path';

const TOKEN = process.env.PORTAL_E2E_TOKEN;
const SLUG = process.env.PORTAL_E2E_SLUG;

// A real committed sample, per the project rule that AI/file features are tested against
// real fixtures rather than stubs. Any receipt-ish image exercises the same path; what
// matters is that a genuine file reaches the extractor.
const RECEIPT = path.resolve(__dirname, 'fixtures', 'ai-extract', 'image-01.png');

async function seedPortalToken(page: Page, token: string) {
  await page.addInitScript((t: string) => {
    try {
      window.sessionStorage.setItem('sorento.portalToken', t);
    } catch {
      // Some browsers throw when sessionStorage is locked down; ignore in init.
    }
  }, token);
}

/** Photo, then continue. The flow will not leave step 1 without one. */
async function addMockPhotoAndContinue(page: Page) {
  await page.getByRole('button', { name: /add a photo/i }).click();
  await page.getByRole('button', { name: /^continue$/i }).click();
}

test.describe('Consumer lodge - the prototype, on mocks', () => {
  test('a resolved receipt reads back what we understood', async ({ page }) => {
    await page.goto('/portal/lodge?scenario=resolved');
    await addMockPhotoAndContinue(page);

    // "Did we get this right?" is only asked when there IS something to confirm.
    await expect(page.getByText(/did we get this right/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/TOTAL HOME DIY/i).first()).toBeVisible();
  });

  test('a receipt with no shop name says so instead of asking about an empty sentence', async ({
    page,
  }) => {
    // 24% of receipts. Asking a consumer to confirm a blank sentence reads as a broken
    // screen, and this copy branch is the fix that came out of walking the prototype.
    await page.goto('/portal/lodge?scenario=unmatched');
    await addMockPhotoAndContinue(page);

    await expect(page.getByText(/could not read much from that photo/i)).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/did we get this right/i)).toHaveCount(0);
  });

  test('a candidate dealer is never shown to the consumer as a fact', async ({ page }) => {
    // The spike's three real-but-WRONG neighbours, as a UI assertion. A candidate carries
    // no customer name, so the consumer only ever sees the shop THEY typed.
    await page.goto('/portal/lodge?scenario=candidate');
    await addMockPhotoAndContinue(page);

    await expect(page.getByText(/SENG HUAT/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/we found them/i)).toHaveCount(0);
  });

  test('the whole journey reaches a reference number and a warranty answer', async ({ page }) => {
    await page.goto('/portal/lodge?scenario=resolved');
    await addMockPhotoAndContinue(page);

    // confirm -> kind
    await page.getByRole('button', { name: /yes, that is right|^continue$/i }).click();

    // The tiled chooser. Text tiles, accepted deliberately: no Kind carries artwork, and
    // the first draft's initial-letter circle rendered "K" on four different taps.
    const tile = page.getByRole('button', { name: 'Water Closet' });
    await expect(tile).toBeVisible();
    await tile.click();
    await page.getByRole('button', { name: /^continue$/i }).click();

    // fault + photos -> site
    await page.getByRole('button', { name: /^continue$/i }).click();

    // Nothing on the site step is compulsory: a consumer who refuses location permission
    // must still be able to send the report (AC-M38).
    await page.getByRole('button', { name: /^submit$/i }).click();

    await expect(page.getByText(/we have your report/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/CMP/)).toBeVisible();
  });

  test('the flow fits a phone', async ({ page }) => {
    // Every one of these arrives on a handset. A header that cannot wrap overlaps its own
    // buttons AND forces page-wide horizontal overflow, cutting the form off.
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/portal/lodge?scenario=resolved');
    await addMockPhotoAndContinue(page);
    await expect(page.getByText(/did we get this right/i)).toBeVisible({ timeout: 15_000 });

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});

test.describe('Consumer lodge - live, through the real stack', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(
      !TOKEN || !SLUG,
      'Set PORTAL_E2E_TOKEN and PORTAL_E2E_SLUG to run the live consumer lodge e2e.',
    );
    await seedPortalToken(page, TOKEN!);
  });

  test('a real receipt lodges and comes back with a number', async ({ page }) => {
    const calls: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v1/public/portal/lodge')) {
        calls.push(`${req.method()} ${new URL(req.url()).pathname}`);
      }
    });

    await page.goto(`/portal/c/${SLUG}/lodge`);

    // The upload step opens the camera on a phone; here we hand it the fixture directly.
    await page.locator('input[type="file"]').setInputFiles(RECEIPT);
    await page.getByRole('button', { name: /^continue$/i }).click();

    // Extraction may read nothing, which is a normal outcome and lands on the same
    // editable form. Either copy branch means the step rendered.
    await expect(
      page.getByText(/did we get this right|could not read much from that photo/i),
    ).toBeVisible({ timeout: 90_000 });

    // Correcting the shop name must re-run the dealer match - that is the whole point of
    // pre-filling an editable form rather than a read-only confirmation.
    const shop = page.getByPlaceholder(/shop name on your receipt/i);
    await shop.fill('TOTAL HOME DIY SDN BHD');
    await shop.blur();
    await expect(async () => {
      expect(calls.some((c) => c.includes('/lodge/resolve'))).toBe(true);
    }).toPass({ timeout: 15_000 });

    await page.getByRole('button', { name: /yes, that is right|^continue$/i }).click();

    // The chooser is served by the real endpoint here, so an empty grid would mean the
    // Kinds never seeded.
    const tile = page.getByRole('button', { name: 'Water Closet' });
    await expect(tile).toBeVisible({ timeout: 15_000 });
    await tile.click();
    await page.getByRole('button', { name: /^continue$/i }).click();
    await page.getByRole('button', { name: /^continue$/i }).click();
    await page.getByRole('button', { name: /^submit$/i }).click();

    await expect(page.getByText(/we have your report/i)).toBeVisible({ timeout: 60_000 });
    expect(calls.some((c) => c === 'POST /api/v1/public/portal/lodge')).toBe(true);
  });
});
