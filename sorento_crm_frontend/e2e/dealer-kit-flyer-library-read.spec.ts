import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * AC-A10: reading a flyer that is already in the file library, in a real
 * browser against the real stack.
 *
 * Run:
 *   set -a; . ./.env.local; set +a
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   npx playwright test e2e/dealer-kit-flyer-library-read.spec.ts --reporter=line
 *
 * Follows the conventions in e2e/dealer-kit-flyer-seeding.spec.ts: same
 * env-var-gated `test.skip`, same login/tap/type helpers, sidebar-only
 * navigation, real fixture bytes, and by-id cleanup naming the run.
 *
 * The one thing this spec exists to prove that no vitest can: the "Choose
 * from Files" tab drives the FE all the way to
 * `POST /flyer-readings/from-attachment`, never the multipart upload route -
 * both post to overlapping URL prefixes, so a network-request assertion is
 * the only thing that actually distinguishes them.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;
const API_BASE = process.env.DEALER_KIT_E2E_API_BASE ?? 'http://localhost:8020';
const KIT = `${API_BASE}/api/v1/dealer-kit`;
const ATTACHMENTS = `${API_BASE}/api/v1/resource-management/attachments`;

const FIXTURE = path.join(__dirname, 'fixtures', 'dealer-kit', 'flyer_sample.pdf');

/** One name per run, so a re-run never collides with a row a previous one left. */
const RUN = Math.random().toString(36).slice(2, 8);
const LIBRARY_FILENAME = `zzt-flyer-library-${RUN}.pdf`;

test.skip(
  !EMAIL || !PASSWORD,
  'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the flyer library-read flow',
);

/** Rows this run created, deleted by id in afterAll. */
let createdAttachmentId: string | null = null;
let createdReadingId: string | null = null;

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

async function apiToken(request: APIRequestContext): Promise<string> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const response = await request.get('/api/auth/token');
    if (response.ok()) {
      const body = (await response.json()) as { token?: string };
      if (body.token) return body.token;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error('no backend session token; the suite cannot verify or clean up');
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` };
}

/**
 * Click without Playwright's actionability auto-wait.
 *
 * The protected layout fires a dev-ingest fetch that never resolves in a test
 * environment, so the page never settles and a real `.click()` hangs past its
 * own timeout. Established in the other Dealer Kit specs.
 */
async function tap(locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  await locator.dispatchEvent('click');
}

/** Reach the Flyers screen the way a user does: the sidebar group, then the leaf. */
async function openFlyers(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });

  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }

  const link = page.getByRole('link', { name: /^flyers$/i }).first();
  await expect(link, 'Flyers leaf should render inside the Dealer Kit group').toBeVisible({
    timeout: 15_000,
  });
  expect(await link.getAttribute('href')).toBe('/dealer-kit/flyer-readings');

  await link.dispatchEvent('click');
  await page.waitForURL(/flyer-readings/, { timeout: 30_000 });
}

/**
 * Put the flyer PDF into the file library the way a designer does BEFORE this
 * spec's flow even starts: sidebar -> Resource Management -> Files -> Upload.
 * Not the API, because the whole point of AC-A10's journey is that marketing
 * already filed this months ago through the ordinary drive screen.
 */
async function seedLibraryAttachment(page: Page): Promise<string> {
  await page.goto('/', { waitUntil: 'commit' });

  const rm = page.getByRole('button', { name: /resource management/i }).first();
  await expect(rm, 'Resource Management sidebar group should render').toBeVisible({
    timeout: 20_000,
  });
  if ((await rm.getAttribute('aria-expanded')) !== 'true') {
    await rm.dispatchEvent('click');
  }
  const filesLink = page.getByRole('link', { name: /^files$/i }).first();
  await expect(filesLink).toBeVisible({ timeout: 15_000 });
  await filesLink.dispatchEvent('click');
  await page.waitForURL(/attachments/, { timeout: 30_000 });

  await tap(page.getByRole('button', { name: /^upload$/i }).first());
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout: 15_000 });

  // First attachment type accepts pdf on every environment this suite runs
  // against (established by e2e/documents-drive.spec.ts).
  await dialog.getByRole('combobox').first().click();
  await page.getByRole('option').first().click();

  const bytes = fs.readFileSync(FIXTURE);
  await dialog
    .locator('input[type="file"]')
    .first()
    .setInputFiles({ name: LIBRARY_FILENAME, mimeType: 'application/pdf', buffer: bytes });

  const uploaded = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      /\/api\/v1\/resource-management\/attachments\/?($|\?)/.test(response.url()),
    { timeout: 40_000 },
  );
  await dialog.getByRole('button', { name: /^upload\b/i }).first().click();
  const response = await uploaded;
  expect(response.status(), await response.text()).toBe(201);
  const body = (await response.json()) as { id: string };

  await page.keyboard.press('Escape').catch(() => {});
  await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 10_000 }).catch(() => {});

  return body.id;
}

test.describe('Dealer Kit flyer library read', () => {
  test.describe.configure({ timeout: 180_000 });

  test.afterAll(async ({ browser }) => {
    if (!EMAIL || !PASSWORD) return;
    if (!createdReadingId && !createdAttachmentId) return;

    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await login(page);
      const token = await apiToken(context.request);

      if (createdReadingId) {
        const response = await context.request.delete(`${KIT}/flyer-readings/${createdReadingId}`, {
          headers: auth(token),
        });
        if (!response.ok()) {
          console.warn(`[cleanup] reading ${createdReadingId} survived: ${response.status()}`);
        }
      }
      if (createdAttachmentId) {
        const response = await context.request.delete(`${ATTACHMENTS}/${createdAttachmentId}`, {
          headers: auth(token),
        });
        if (!response.ok()) {
          console.warn(`[cleanup] attachment ${createdAttachmentId} survived: ${response.status()}`);
        }
      }
    } catch (error) {
      console.warn(`[cleanup] skipped: ${String(error).slice(0, 200)}`);
    } finally {
      await context.close();
    }
  });

  test('picking the library file reaches the review screen via the from-attachment call, not an upload', async ({
    page,
  }) => {
    await login(page);

    createdAttachmentId = await seedLibraryAttachment(page);

    await openFlyers(page);

    // ---- step 1: open the dialog, choose the library source -------------
    await tap(page.getByRole('button', { name: /read a flyer/i }).first());
    const readDialog = page.getByRole('dialog', { name: /read a flyer/i });
    await expect(readDialog).toBeVisible({ timeout: 15_000 });

    await tap(readDialog.getByTestId('dk-fr-source-library'));
    await expect(readDialog.getByTestId('dk-fr-source-library')).toHaveAttribute(
      'data-state',
      'active',
    );

    // ---- step 2: pick the file from the shared browser -------------------
    await tap(readDialog.getByTestId('dk-fr-library-browse'));
    const pickerDialog = page.getByRole('dialog', { name: /choose a flyer/i });
    await expect(pickerDialog).toBeVisible({ timeout: 15_000 });

    // Narrow to our uniquely-named seeded file - the library is a copy of
    // production and can hold thousands of PDFs.
    await pickerDialog.getByPlaceholder(/search attachments/i).fill(LIBRARY_FILENAME);
    const row = pickerDialog.getByText(LIBRARY_FILENAME, { exact: false }).first();
    await expect(row, 'the seeded PDF should be listed (PDF-only filter)').toBeVisible({
      timeout: 20_000,
    });
    await tap(row);
    await tap(pickerDialog.getByRole('button', { name: /use this file/i }));
    await expect(pickerDialog).toBeHidden({ timeout: 10_000 });

    // Picking closed the browser and handed the file back - the read dialog
    // shows it selected, nothing linked yet.
    await expect(readDialog.getByTestId('dk-fr-library-selection')).toContainText(
      LIBRARY_FILENAME,
    );

    // ---- step 3: submit, and watch which endpoint gets hit ---------------
    const requestLog: Array<{ url: string; method: string; contentType: string | null }> = [];
    page.on('request', (request) => {
      if (/\/api\/v1\/dealer-kit\/flyer-readings/.test(request.url())) {
        requestLog.push({
          url: request.url(),
          method: request.method(),
          contentType: request.headers()['content-type'] ?? null,
        });
      }
    });

    const created = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        /\/flyer-readings\/from-attachment$/.test(response.url()),
      { timeout: 60_000 },
    );
    await tap(readDialog.getByTestId('dk-fr-upload-submit'));

    const response = await created;
    expect(response.status(), await response.text()).toBe(201);
    const body = (await response.json()) as { id: string; pageCount: number };
    createdReadingId = body.id;
    expect(body.pageCount).toBe(3); // the fixture is a 3 page cut of the real flyer

    // ---- the payoff: the network log names the from-attachment call, and
    // ---- ONLY that call - never a multipart upload to the bare route ------
    const postsToKit = requestLog.filter((entry) => entry.method === 'POST');
    expect(postsToKit).toHaveLength(1);
    expect(postsToKit[0].url).toMatch(/\/flyer-readings\/from-attachment$/);
    expect(postsToKit[0].contentType ?? '').toContain('application/json');
    expect(postsToKit.some((entry) => (entry.contentType ?? '').includes('multipart'))).toBe(
      false,
    );

    // ---- step 4: landed on the review screen for the new reading ---------
    await page.waitForURL(new RegExp(`flyer-readings/${body.id}`), { timeout: 30_000 });
    await expect(page.getByTestId('dk-fr-filename')).toBeVisible({ timeout: 30_000 });
  });
});
