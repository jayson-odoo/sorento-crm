import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

import { boundBackgroundUrls, stillStoredUrls } from './dealerKitCleanup';

/**
 * The builder shows the artwork, and it is the SAME artwork the reader gets.
 *
 * Run:
 *   set -a; . ./.env.local; set +a
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   npx playwright test e2e/dealer-kit-editor-background.spec.ts --reporter=line
 *
 * ## Why this is worth a spec rather than a component test
 *
 * The component tests already prove the builder canvas and the published
 * catalogue produce an identical surface for one `SectionStyle`. What they
 * cannot prove is that the builder is HANDED anything: the signed URLs are
 * resolved by the backend, on the editor's own endpoint, from the document it is
 * about to open. Four layers (seed -> page payload -> editor -> canvas) each
 * with its own way of dropping a key, and a jsdom test mocks whichever one
 * breaks. So this drives the real chain: read a real flyer, seed a draft, open
 * the builder, and compare the picture on the canvas with the picture on the
 * published page - by asset, not by eye.
 *
 * The person this protects is the reviewer. The extractor is known to misread
 * headings (fixture page 2 reads "Transforming Your" where the paper says
 * "BATHTUB COLLECTION"), so somebody has to sit in the builder and correct them
 * against the artwork. Until now they were the only person who could not see it.
 *
 * ## The database is a copy of production
 *
 * Everything created here is named with the reserved `zzt-` prefix and deleted
 * BY ID afterwards. Deleting the page cascades its versions, labels and
 * page-scoped collections. There is no unscoped DELETE anywhere in this file,
 * and nothing here writes to products or promotions.
 *
 * ## And so is the bucket
 *
 * Playwright drives the real backend, so `tests/_fake_storage.py` cannot reach
 * it: every upload here writes REAL banner objects to the live storage bucket.
 * Deleting the reading removes the assets, their attachments and their bytes,
 * and the teardown fetches the signed URLs it noted beforehand to prove it. A
 * surviving object fails the run rather than being logged - nothing else
 * notices one, which is how 1,356 unreachable objects accumulated unobserved.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;
const API_BASE = process.env.DEALER_KIT_E2E_API_BASE ?? 'http://localhost:8020';
const KIT = `${API_BASE}/api/v1/dealer-kit`;

const FIXTURE = path.join(__dirname, 'fixtures', 'dealer-kit', 'flyer_sample.pdf');
const SHOTS = path.join(__dirname, '..', 'test-results');

const RUN = Math.random().toString(36).slice(2, 8);
const BROCHURE_NAME = `zzt-bg-${RUN}`;

/** A 2x2 four-colour PNG. Four unmistakable quadrants once a `fit` stretches it. */
const SWATCH_PNG =
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGO4o6ammvyaQWyx16vNHAAj8AVE95m2kwAAAABJRU5ErkJggg==';

test.skip(
  !EMAIL || !PASSWORD,
  'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the editor background flow',
);

const createdPages: string[] = [];
const createdReadings: string[] = [];

/**
 * Click without Playwright's actionability auto-wait.
 *
 * The protected layout fires a dev-ingest fetch that never resolves in a test
 * environment, so the page never settles and a real `.click()` hangs past its
 * own timeout. Established in every other Dealer Kit spec.
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
    Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set?.call(field, next);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

/** Put the REAL fixture on a file input, bypassing the same actionability wait. */
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
  await page
    .locator('input[type="password"], input[name="password"]')
    .first()
    .fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), {
    timeout: 30_000,
  });
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
 * Reach Flyers the way a user does: the sidebar group, then the leaf.
 *
 * A deep link would pass even if the entry were missing, mis-gated behind a
 * moduleKey, or hidden inside a collapsed group.
 */
async function openFlyers(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });

  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({
    timeout: 20_000,
  });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }

  const link = page.getByRole('link', { name: /^flyers$/i }).first();
  await expect(link, 'Flyers leaf should render inside the Dealer Kit group').toBeVisible(
    {
      timeout: 15_000,
    },
  );
  await link.dispatchEvent('click');
  await page.waitForURL(/flyer-readings/, { timeout: 30_000 });
}

/** The full signed URL a rendered surface is painting, if any. */
async function paintedUrl(locator: ReturnType<Page['locator']>): Promise<string | null> {
  return locator.evaluate((element) => {
    const image = getComputedStyle(element as HTMLElement).backgroundImage;
    const match = /url\(["']?(.+?)["']?\)/.exec(image);
    return match ? match[1] : null;
  });
}

/**
 * The same URL reduced to the asset KEY it points at.
 *
 * The editor and the reader are signed separately, so the query strings differ
 * by design. What must match is the object: `dealer_kit_asset/{id}/{file}`.
 */
function assetKey(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}

test.describe('Dealer Kit builder backgrounds', () => {
  // Real upload, real extraction, real matching against the live master.
  test.describe.configure({ timeout: 300_000 });

  test.afterAll(async ({ browser }, testInfo) => {
    if (!EMAIL || !PASSWORD) return;
    if (createdPages.length === 0 && createdReadings.length === 0) return;

    const context = await browser.newContext({
      baseURL: testInfo.project.use.baseURL,
    });
    const page = await context.newPage();
    let leaked: string[] = [];
    try {
      await login(page);
      const token = await apiToken(context.request);

      // The artwork this run put in the library, noted while its brochure can
      // still name it. This spec exists to prove the banner reaches a reader,
      // so it is also the spec that writes the most real objects into the live
      // bucket - and until the delete sweep landed, none of them ever left.
      const backgrounds = await boundBackgroundUrls(context.request, token, createdPages);

      // By id, never by pattern. The page delete cascades its versions,
      // labels and the page-scoped collections the seed created with it, and
      // takes any background nothing else names. The reading still claims its
      // banners here, so they go on the next step.
      for (const id of new Set(createdPages)) {
        const response = await context.request.delete(`${KIT}/pages/${id}`, {
          headers: auth(token),
        });
        if (!response.ok())
          console.warn(`[cleanup] page ${id} survived: ${response.status()}`);
      }
      // Last claim gone: this is what removes the assets, their attachments and
      // their stored objects, through the product's own delete rather than a
      // side channel written for a test.
      for (const id of new Set(createdReadings)) {
        const response = await context.request.delete(`${KIT}/flyer-readings/${id}`, {
          headers: auth(token),
        });
        if (!response.ok())
          console.warn(`[cleanup] reading ${id} survived: ${response.status()}`);
      }

      leaked = await stillStoredUrls(context.request, backgrounds);
    } catch (error) {
      console.warn(`[cleanup] skipped: ${String(error).slice(0, 200)}`);
    } finally {
      await context.close();
    }

    // Outside the catch on purpose: a leak is a REGRESSION, not a hiccup to log.
    expect(leaked, 'the run left storage objects behind that no row can reach').toEqual([]);
  });

  test("the seeded flyer artwork is on the builder canvas, and it is the reader's artwork", async ({
    page,
  }) => {
    /**
     * Anything the browser complained about, kept for the assertion at the end.
     *
     * A background is a CSS declaration, so a URL the CDN refuses fails
     * SILENTLY: no broken-image icon, no exception, just a section that looks
     * plain. The console is where that shows up, which makes it evidence rather
     * than noise.
     */
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => pageErrors.push(String(error)));

    await login(page);
    await openFlyers(page);

    // ---- read the flyer -------------------------------------------------
    await tap(page.getByRole('button', { name: /read a flyer/i }).first());
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 15_000 });
    await attachFile(page, '#dk-fr-file', FIXTURE);
    await expect(page.getByTestId('dk-fr-upload-submit')).toBeEnabled({
      timeout: 15_000,
    });

    const uploaded = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        /\/api\/v1\/dealer-kit\/flyer-readings(\?|$)/.test(response.url()),
      { timeout: 180_000 },
    );
    await tap(page.getByTestId('dk-fr-upload-submit'));
    const readingResponse = await uploaded;
    // The read is queued: 202 with a `processing` row, and the dialog closes
    // without navigating. The report arrives on the row, not in this response.
    expect(readingResponse.status(), await readingResponse.text()).toBe(202);
    const reading = (await readingResponse.json()) as { id: string; status: string };
    createdReadings.push(reading.id);
    expect(reading.status).toBe('processing');

    await expect(page.getByRole('dialog', { name: /read a flyer/i })).toBeHidden({
      timeout: 15_000,
    });

    // The Flyers list polls until the job finishes, then the row opens the
    // review screen the seed is driven from.
    const pill = page.getByTestId('dk-fr-status-pill').first();
    await expect(pill).toBeVisible({ timeout: 30_000 });
    await expect(pill, 'the queued read should reach Done on its own').toHaveText(/done/i, {
      timeout: 180_000,
    });

    await tap(
      page.getByRole('row').filter({ has: page.getByTestId('dk-fr-status-pill') }).first(),
    );
    await page.waitForURL(new RegExp(`flyer-readings/${reading.id}`), {
      timeout: 30_000,
    });

    // ---- seed a draft ---------------------------------------------------
    await type(page.locator('#dk-fr-name'), BROCHURE_NAME);
    const seeded = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        /\/flyer-readings\/.+\/seed$/.test(response.url()),
      { timeout: 180_000 },
    );
    await tap(page.getByTestId('dk-fr-seed-button'));
    const seedResponse = await seeded;
    expect(seedResponse.status(), await seedResponse.text()).toBe(201);
    const result = (await seedResponse.json()) as {
      pageId: string;
      sectionCount: number;
    };
    createdPages.push(result.pageId);

    // ---- open the draft in the builder ----------------------------------
    const open = page.getByRole('link', { name: /open the draft/i });
    await tap(open);
    await page.waitForURL(new RegExp(`pages/${result.pageId}`), {
      timeout: 30_000,
    });
    await expect(page.getByRole('heading', { name: /page builder/i })).toBeVisible({
      timeout: 30_000,
    });

    // The payload the canvas paints from. Asserted on the wire as well as on
    // screen, because "the editor shows nothing" and "the server sent nothing"
    // look identical from a screenshot.
    const token = await apiToken(page.context().request);
    const detail = await page.context().request.get(`${KIT}/pages/${result.pageId}`, {
      headers: auth(token),
    });
    expect(detail.ok()).toBeTruthy();
    const payload = (await detail.json()) as {
      assets?: Record<string, string>;
      doc: {
        sections: Array<{
          name: string;
          style: { backgroundAssetId?: string };
        }>;
      };
    };
    expect(
      Object.keys(payload.assets ?? {}).length,
      'the editor payload should carry a signed URL per bound background',
    ).toBeGreaterThan(0);

    // ---- the canvas paints it -------------------------------------------
    // Which flyer page has a banner is the heuristic's decision, not this
    // spec's, so the section is chosen from the document rather than assumed.
    const withArtwork = payload.doc.sections.find(
      (section) =>
        section.style.backgroundAssetId &&
        (payload.assets ?? {})[section.style.backgroundAssetId],
    );
    expect(withArtwork, 'the seed should bind at least one banner').toBeTruthy();

    // Selected the way a designer does: the section list on the left. Matched
    // as a substring, because a section that starts a new page carries a
    // "break" badge INSIDE the button and that badge is part of its
    // accessible name.
    await tap(page.getByRole('button', { name: withArtwork!.name }).first());

    const canvas = page.locator('[data-testid="dk-builder-canvas"]');
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    const editorUrl = await paintedUrl(canvas);

    expect(
      editorUrl,
      'the selected section should paint its flyer banner on the builder canvas',
    ).toBeTruthy();

    // Painted AND fetchable. "Absent rather than broken" is only half the
    // promise; the other half is that what IS present resolves, and a URL the
    // CDN answers 403 to would still satisfy every assertion above.
    const artwork = await page.context().request.get(editorUrl!);
    expect(artwork.status(), 'the signed background URL should resolve').toBe(200);

    // The control that makes a wrong guess fixable, offered exactly when there
    // is something to remove.
    await expect(page.getByRole('button', { name: /remove background/i })).toBeVisible();

    fs.mkdirSync(SHOTS, { recursive: true });
    await canvas.screenshot({
      path: path.join(SHOTS, 'dk-editor-background.png'),
    });
    await page.screenshot({
      path: path.join(SHOTS, 'dk-editor-background-full.png'),
      fullPage: true,
    });

    // ---- and it is visibly PAINTED, not merely declared -----------------
    // The committed fixture's own banners are near-blank white (it is a cut of
    // the real A3 flyer), so a screenshot of them proves the declaration and
    // nothing about the paint. Substituting the BYTES at the same URL - the URL
    // the server signed, fetched by the browser exactly as before - is what
    // shows the artwork reaching the canvas and being laid out by `fit`.
    // Matched on the PATH, not the exact URL: a reload asks the server for the
    // page again and gets a freshly signed link, so an exact-URL route would
    // silently stop matching and the substitution would look like a paint that
    // never happened.
    const editorKey = assetKey(editorUrl!);
    await page.route(
      (url) => url.pathname === editorKey,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'image/png',
          body: Buffer.from(SWATCH_PNG, 'base64'),
        }),
    );
    await page.reload({ waitUntil: 'commit' });
    await expect(canvas).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: /remove background/i })).toBeVisible({
      timeout: 20_000,
    });
    await canvas.screenshot({
      path: path.join(SHOTS, 'dk-editor-background-visible.png'),
    });
    await page.unrouteAll();

    // ---- publish, then compare against what a reader receives ------------
    await tap(page.getByRole('button', { name: /^publish$/i }));
    await expect(page.getByText(/is now live/i)).toBeVisible({
      timeout: 30_000,
    });

    const live = page.getByRole('link', { name: /view live/i });
    await expect(live).toBeVisible({ timeout: 15_000 });
    const href = await live.getAttribute('href');
    expect(href).toBeTruthy();

    await page.goto(href!, { waitUntil: 'commit' });
    const publicSections = page.locator('[data-dk-section-id]');
    await expect(publicSections.first()).toBeVisible({ timeout: 30_000 });

    const readerAssets: string[] = [];
    for (let index = 0; index < (await publicSections.count()); index += 1) {
      const painted = await paintedUrl(publicSections.nth(index));
      if (painted) readerAssets.push(assetKey(painted));
    }

    // The point of the whole slice: the same object, not merely "a picture".
    expect(
      readerAssets,
      'the builder painted an asset the published catalogue does not carry',
    ).toContain(assetKey(editorUrl!));

    await page.screenshot({
      path: path.join(SHOTS, 'dk-public-background.png'),
      fullPage: true,
    });

    // ---- nothing broke on the way -----------------------------------------
    // The dev-ingest probe at localhost:7242 is absent outside the author's
    // machine and its failure is expected here; everything else is a
    // regression, especially an image the CDN refused.
    const noise = /7242|ERR_CONNECTION_REFUSED|Download the React DevTools/i;
    expect(pageErrors, 'no uncaught exceptions during the flow').toEqual([]);
    expect(consoleErrors.filter((line) => !noise.test(line))).toEqual([]);
  });

  // NESTED on purpose: the outer describe owns the afterAll that deletes the
  // brochure, and a sibling describe would run after that cleanup had already
  // taken the page away.
  test.describe('Removing a seeded background at 375px', () => {
    test.use({ viewport: { width: 375, height: 800 } });

    /**
     * The escape hatch from a wrong guess, on the smallest screen it has to work on.
     *
     * AC-F4 picks the largest image near the top of a flyer page, and it will
     * sometimes pick the wrong one. A background that cannot be removed would
     * leave a reviewer with nothing to do but abandon the seeded draft, so the
     * control has to be reachable - and it has to ask first, because nothing
     * restores the artwork afterwards.
     */
    test('asks before it detaches, and removes the artwork when told to', async ({
      page,
    }) => {
      test.skip(
        createdPages.length === 0,
        'the first test seeds the brochure this one edits',
      );

      await login(page);

      // The drawer, not a deep link: on a phone the sidebar is behind the
      // header's menu button and that is the only way in.
      await page.goto('/', { waitUntil: 'commit' });
      const menu = page.locator('header button[aria-haspopup="dialog"]').first();
      await expect(menu, 'the phone header should offer a navigation drawer').toBeVisible(
        {
          timeout: 20_000,
        },
      );
      await menu.dispatchEvent('pointerdown', {
        button: 0,
        isPrimary: true,
        bubbles: true,
      });
      await menu.dispatchEvent('click', { button: 0, bubbles: true });

      const group = page.getByRole('button', { name: /dealer kit/i }).first();
      await expect(group).toBeVisible({ timeout: 20_000 });
      if ((await group.getAttribute('aria-expanded')) !== 'true')
        await group.dispatchEvent('click');
      const link = page.getByRole('link', { name: /catalogue pages/i }).first();
      await expect(link).toBeVisible({ timeout: 15_000 });
      await link.dispatchEvent('click');
      await page.waitForURL(/dealer-kit/, { timeout: 30_000 });

      await tap(page.getByText(BROCHURE_NAME).first());
      await page.waitForURL(new RegExp(`pages/${createdPages[0]}`), {
        timeout: 30_000,
      });

      const remove = page.getByRole('button', { name: /remove background/i });
      await expect(
        remove,
        'the control should be offered for a section that has artwork',
      ).toBeVisible({ timeout: 30_000 });

      // Laid out inside the phone, not off the side of it.
      const box = await remove.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x + box!.width).toBeLessThanOrEqual(376);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);

      // A confirm, never a bare click.
      await remove.dispatchEvent('click');
      const confirm = page.getByRole('alertdialog');
      await expect(confirm).toBeVisible({ timeout: 15_000 });
      await expect(confirm).toContainText(/cannot be undone/i);

      await confirm.getByRole('button', { name: /^remove$/i }).dispatchEvent('click');

      // Gone from the canvas, and the document says it has changed - the removal
      // is an edit the designer made, not a reflow the editor performed.
      const canvas = page.locator('[data-testid="dk-builder-canvas"]');
      await expect(canvas).toBeVisible({ timeout: 20_000 });
      expect(await paintedUrl(canvas)).toBeNull();
      await expect(page.getByText(/unsaved changes/i)).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByRole('button', { name: /remove background/i })).toHaveCount(
        0,
      );
    });
  });
});
