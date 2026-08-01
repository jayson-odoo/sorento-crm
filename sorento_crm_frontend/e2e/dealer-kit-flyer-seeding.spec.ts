import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * Reading a printed flyer and seeding a draft brochure from it (S7.4), in a
 * real browser, against the real backend.
 *
 * Run:
 *   set -a; . ./.env.local; set +a
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   npx playwright test e2e/dealer-kit-flyer-seeding.spec.ts --reporter=line
 *
 * ## Why this needs an end-to-end test
 *
 * The chain is upload -> extract -> match against the master -> report ->
 * seed -> page + version + collections, across five layers, and every unit test
 * on either side of it mocks the layer that actually breaks. The specific thing
 * this spec pins is AC-E5's first half: the seed produces a DRAFT, and a draft
 * is a draft BY CONSTRUCTION - no label points at it, so no reader can reach it.
 * A regression that moved the published label on seed would leave every backend
 * test green and put an unreviewed catalogue in front of every dealer.
 *
 * ## The fixture is real
 *
 * `e2e/fixtures/dealer-kit/flyer_sample.pdf` is a 3 page cut of the actual
 * _SORENTO A3 FLYER 2025-2026_, the same bytes the backend suite reads. A
 * stubbed PDF would exercise the upload and nothing downstream of it: the
 * heading heuristic, the row baselines and the codes the master does not have
 * are all properties of the paper.
 *
 * ## The database is a copy of production
 *
 * Everything this run creates is named with the reserved `zzt-` prefix and
 * deleted by ID in `afterAll` - the brochure, its versions and the reading. The
 * page delete cascades its versions and collections. There is no unscoped
 * DELETE or UPDATE anywhere in this file, and nothing here writes to `products`
 * or to any promotion.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;
const API_BASE = process.env.DEALER_KIT_E2E_API_BASE ?? 'http://localhost:8020';
const KIT = `${API_BASE}/api/v1/dealer-kit`;

const FIXTURE = path.join(__dirname, 'fixtures', 'dealer-kit', 'flyer_sample.pdf');

/** One name per run, so a re-run never collides with a row a previous one left. */
const RUN = Math.random().toString(36).slice(2, 8);
const BROCHURE_NAME = `zzt-flyer-${RUN}`;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the flyer seeding flow');

/** Rows this run created, deleted by id in afterAll. */
const createdPages: string[] = [];
const createdReadings: string[] = [];

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

/** Type into a React-controlled input without actionability auto-wait. */
async function type(locator: ReturnType<Page['locator']>, value: string) {
  await locator.waitFor({ state: 'attached', timeout: 20_000 });
  await locator.evaluate((element, next) => {
    const field = element as HTMLInputElement;
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(
      field,
      next,
    );
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

/**
 * Put a real file on a file input without Playwright's actionability wait.
 *
 * `setInputFiles` waits for the element to be stable, and this layout never
 * reaches a settled state (the same never-resolving dev-ingest fetch the other
 * Dealer Kit specs work around with `dispatchEvent`), so it times out on an
 * input that is plainly there. The bytes are read in Node and handed to the
 * page, so the file is the REAL fixture and not a stub - the whole point is
 * that extraction runs against the actual paper.
 */
async function attachFile(page: Page, selector: string, filePath: string) {
  const base64 = fs.readFileSync(filePath).toString('base64');
  const name = path.basename(filePath);

  await page.locator(selector).waitFor({ state: 'attached', timeout: 20_000 });
  await page.locator(selector).evaluate(
    (element, payload) => {
      const bytes = Uint8Array.from(atob(payload.base64), (character) =>
        character.charCodeAt(0),
      );
      const file = new File([bytes], payload.name, { type: 'application/pdf' });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      (element as HTMLInputElement).files = transfer.files;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    },
    { base64, name },
  );
}

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

/** Reach the screen the way a user does: the sidebar group, then the leaf. */
async function openFlyers(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });

  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }

  // A deep link would say nothing about whether the entry exists at all, which
  // is exactly the defect the brochure image screen shipped with.
  const link = page.getByRole('link', { name: /^flyers$/i }).first();
  await expect(link, 'Flyers leaf should render inside the Dealer Kit group').toBeVisible({
    timeout: 15_000,
  });
  expect(await link.getAttribute('href')).toBe('/dealer-kit/flyer-readings');

  await link.dispatchEvent('click');
  await page.waitForURL(/flyer-readings/, { timeout: 30_000 });
}

/** Upload the fixture and land on its review screen. Returns the reading id. */
async function readTheFlyer(page: Page): Promise<string> {
  await tap(page.getByRole('button', { name: /read a flyer/i }).first());
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 15_000 });

  await attachFile(page, '#dk-fr-file', FIXTURE);
  await expect(page.getByTestId('dk-fr-upload-submit')).toBeEnabled({ timeout: 15_000 });

  const uploaded = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      /\/api\/v1\/dealer-kit\/flyer-readings(\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await tap(page.getByTestId('dk-fr-upload-submit'));

  const response = await uploaded;
  // Extraction runs inside the request: 201 with the report, not 202 with a job.
  expect(response.status(), await response.text()).toBe(201);
  const body = (await response.json()) as { id: string; pageCount: number; codeCount: number };
  createdReadings.push(body.id);

  // The fixture is a 3 page cut of the real A3 flyer.
  expect(body.pageCount).toBe(3);
  expect(body.codeCount).toBeGreaterThan(0);

  await page.waitForURL(new RegExp(`flyer-readings/${body.id}`), { timeout: 30_000 });
  await expect(page.getByTestId('dk-fr-filename')).toBeVisible({ timeout: 30_000 });
  return body.id;
}

test.describe('Dealer Kit flyer seeding', () => {
  // Real uploads, real extraction, real matching against the live master.
  test.describe.configure({ timeout: 240_000 });

  test.afterAll(async ({ browser }, testInfo) => {
    if (!EMAIL || !PASSWORD) return;
    if (createdPages.length === 0 && createdReadings.length === 0) return;

    const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
    const page = await context.newPage();
    try {
      await login(page);
      const token = await apiToken(context.request);

      // By id, never by pattern. Deleting a page cascades its versions and the
      // page-scoped collections the seed created with it.
      for (const id of new Set(createdPages)) {
        const response = await context.request.delete(`${KIT}/pages/${id}`, {
          headers: auth(token),
        });
        if (!response.ok()) console.warn(`[cleanup] page ${id} survived: ${response.status()}`);
      }
      for (const id of new Set(createdReadings)) {
        const response = await context.request.delete(`${KIT}/flyer-readings/${id}`, {
          headers: auth(token),
        });
        if (!response.ok()) console.warn(`[cleanup] reading ${id} survived: ${response.status()}`);
      }
    } catch (error) {
      console.warn(`[cleanup] skipped: ${String(error).slice(0, 200)}`);
    } finally {
      await context.close();
    }
  });

  test('reads a flyer, reports what it found, and seeds a draft no reader can reach', async ({
    page,
  }) => {
    await login(page);
    await openFlyers(page);

    // ---- step 1: upload -------------------------------------------------
    await readTheFlyer(page);

    // ---- step 2: review -------------------------------------------------
    // Every section renders, including the ones that are empty for this flyer.
    for (const section of ['unmatched', 'not-promoted', 'dimensions', 'duplicates', 'known-gaps']) {
      await expect(
        page.locator(`[data-dk-fr-section="${section}"]`),
        `the ${section} section should render even when empty`,
      ).toBeVisible({ timeout: 20_000 });
    }

    const printed = Number(await page.getByTestId('dk-fr-figure-printed').innerText());
    const matched = Number(await page.getByTestId('dk-fr-figure-matched').innerText());
    const unmatched = Number(await page.getByTestId('dk-fr-figure-unmatched').innerText());
    expect(printed).toBeGreaterThan(0);
    expect(matched + unmatched).toBe(printed);

    // The honesty the whole slice exists for: if the master is missing codes
    // this flyer prints, the screen says so BEFORE the seed, not after.
    if (unmatched > 0) {
      const warning = page.getByTestId('dk-fr-unmatched-warning');
      await expect(warning).toBeVisible();
      await expect(warning).toContainText(/will\s+not\s+be in the brochure/i);
      await expect(page.getByTestId('dk-fr-seed-skip-warning')).toBeVisible();
    } else {
      await expect(page.getByText(/every printed code resolved to a product/i)).toBeVisible();
    }

    // Sizes are a report. Nothing on this screen may offer to write one.
    const dimensions = page.locator('[data-dk-fr-section="dimensions"]');
    await expect(dimensions).toContainText(/nothing here is written to the product master/i);

    // And the headings are guessed. The fixture's page 2 reads "Transforming
    // Your" where the paper says "BATHTUB COLLECTION", so the expectation is set
    // here rather than discovered in the builder.
    await expect(page.getByTestId('dk-fr-known-gaps')).toContainText(/headings are guessed/i);
    await expect(page.getByTestId('dk-fr-known-gaps')).toContainText(/product photos are blank/i);

    // No uuid anywhere on the review screen.
    const reviewText = await page.locator('main, body').first().innerText();
    expect(reviewText).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);

    // ---- step 3: seed ---------------------------------------------------
    await type(page.locator('#dk-fr-name'), BROCHURE_NAME);
    await expect(page.locator('#dk-fr-slug')).toHaveValue(BROCHURE_NAME);

    const seeded = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && /\/flyer-readings\/.+\/seed$/.test(response.url()),
      { timeout: 120_000 },
    );
    await tap(page.getByTestId('dk-fr-seed-button'));

    const seedResponse = await seeded;
    expect(seedResponse.status(), await seedResponse.text()).toBe(201);
    const result = (await seedResponse.json()) as {
      pageId: string;
      versionId: string;
      version: number;
      sectionCount: number;
      collectionCount: number;
      seededProductCount: number;
      skipped: Array<{ code: string }>;
      publicPath: string | null;
    };
    createdPages.push(result.pageId);

    // One section per flyer page (AC-E1).
    expect(result.sectionCount).toBe(3);
    expect(result.collectionCount).toBeGreaterThan(0);
    expect(result.seededProductCount).toBe(matched);
    expect(result.skipped).toHaveLength(unmatched);

    // The result names what did NOT make it, again.
    await expect(page.getByTestId('dk-fr-seed-result')).toBeVisible({ timeout: 30_000 });
    if (unmatched > 0) {
      await expect(page.getByTestId('dk-fr-result-skipped')).toContainText(
        result.skipped[0].code,
      );
    } else {
      await expect(page.getByTestId('dk-fr-result-nothing-skipped')).toBeVisible();
    }
    // Scoped to the result card: the success toast says "Draft v1 created" too.
    await expect(
      page.getByTestId('dk-fr-seed-result').getByText(`Draft v${result.version}`),
    ).toBeVisible();

    // ---- the payoff: it is a DRAFT (AC-E2) ------------------------------
    const token = await apiToken(page.context().request);

    const versions = await page.context().request.get(`${KIT}/pages/${result.pageId}/versions`, {
      headers: auth(token),
    });
    expect(versions.ok()).toBeTruthy();
    const rows = (await versions.json()) as Array<{ id: string; labels: string[] }>;
    const seededVersion = rows.find((row) => row.id === result.versionId);
    expect(seededVersion, 'the seeded version should exist').toBeTruthy();
    // No label points at it, and that IS the draft. A flag would be a second
    // way to say the same thing and the two would eventually disagree.
    expect(seededVersion!.labels ?? []).toHaveLength(0);
    expect(rows.every((row) => !(row.labels ?? []).includes('published'))).toBeTruthy();

    // And the public catalogue refuses it rather than falling back to the
    // newest version. This is the assertion that would catch a seed that
    // published, which every backend test would still pass.
    expect(result.publicPath, 'the seeded page should resolve a public address').toBeTruthy();
    // `publicPath` is `/c/{company}/{slug}`, which the public router serves at
    // `/api/v1/public/c/{company}/{slug}`.
    const publicResponse = await page
      .context()
      .request.get(`${API_BASE}/api/v1/public${result.publicPath}`);
    expect(
      publicResponse.status(),
      'an unpublished draft must not be publicly readable',
    ).toBeGreaterThanOrEqual(400);

    // The way into the builder, which is where the misread headings get fixed.
    const open = page.getByRole('link', { name: /open the draft/i });
    await expect(open).toHaveAttribute('href', `/dealer-kit/pages/${result.pageId}`);
    await open.dispatchEvent('click');
    await page.waitForURL(new RegExp(`pages/${result.pageId}`), { timeout: 30_000 });
  });

  test('re-seeding the same flyer makes a new version and leaves the old one alone', async ({
    page,
  }) => {
    test.skip(createdPages.length === 0, 'the first test creates the brochure this one re-seeds');

    await login(page);
    const token = await apiToken(page.context().request);
    const pageId = createdPages[0];
    const readingId = createdReadings[0];

    const before = await page.context().request.get(`${KIT}/pages/${pageId}/versions`, {
      headers: auth(token),
    });
    const beforeRows = (await before.json()) as Array<{ id: string; version: number }>;

    await openFlyers(page);
    await tap(page.getByText(new RegExp('flyer_sample\\.pdf', 'i')).first());
    await page.waitForURL(new RegExp(`flyer-readings/${readingId}`), { timeout: 30_000 });

    await tap(page.getByLabel('An existing brochure'));
    await tap(page.locator('#dk-fr-page'));
    await tap(page.getByText(BROCHURE_NAME, { exact: false }).last());

    // The screen states what it is about to do, because "seed into an existing
    // brochure" otherwise reads as an overwrite.
    const note = page.getByTestId('dk-fr-reseed-note');
    await expect(note).toBeVisible({ timeout: 15_000 });
    await expect(note).toContainText(
      `Creates version ${Math.max(...beforeRows.map((row) => row.version)) + 1}`,
    );

    const seeded = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && /\/flyer-readings\/.+\/seed$/.test(response.url()),
      { timeout: 120_000 },
    );
    await tap(page.getByTestId('dk-fr-seed-button'));
    const result = (await (await seeded).json()) as { versionId: string; version: number };

    const after = await page.context().request.get(`${KIT}/pages/${pageId}/versions`, {
      headers: auth(token),
    });
    const afterRows = (await after.json()) as Array<{ id: string; version: number; labels: string[] }>;

    // A NEW version, never an update in place (AC-E4).
    expect(afterRows).toHaveLength(beforeRows.length + 1);
    expect(afterRows.some((row) => row.id === result.versionId)).toBeTruthy();
    for (const row of beforeRows) {
      expect(afterRows.some((candidate) => candidate.id === row.id)).toBeTruthy();
    }
    // Still nothing published.
    expect(afterRows.every((row) => !(row.labels ?? []).includes('published'))).toBeTruthy();
  });
});

test.describe('Dealer Kit flyer review at 375px', () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test('reaches the screen from the drawer and does not scroll sideways', async ({ page }) => {
    await login(page);

    // On a phone the sidebar is a drawer behind the header's menu button, and
    // reaching the screen has to go through it.
    await page.goto('/', { waitUntil: 'commit' });
    const menu = page.locator('header button[aria-haspopup="dialog"]').first();
    await expect(menu, 'the phone header should offer a navigation drawer').toBeVisible({
      timeout: 20_000,
    });
    await menu.dispatchEvent('pointerdown', { button: 0, isPrimary: true, bubbles: true });
    await menu.dispatchEvent('click', { button: 0, bubbles: true });

    const group = page.getByRole('button', { name: /dealer kit/i }).first();
    await expect(group).toBeVisible({ timeout: 20_000 });
    if ((await group.getAttribute('aria-expanded')) !== 'true') await group.dispatchEvent('click');
    const link = page.getByRole('link', { name: /^flyers$/i }).first();
    await expect(link).toBeVisible({ timeout: 15_000 });
    await link.dispatchEvent('click');
    await page.waitForURL(/flyer-readings/, { timeout: 30_000 });

    await expect(page.locator('#dk-fr-search')).toBeVisible({ timeout: 30_000 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // The upload modal has to be usable on a phone, submit button included.
    await tap(page.getByRole('button', { name: /read a flyer/i }).first());
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    const box = await page.getByTestId('dk-fr-upload-submit').boundingBox();
    expect(box, 'the submit button should be laid out').not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(376);
  });
});
