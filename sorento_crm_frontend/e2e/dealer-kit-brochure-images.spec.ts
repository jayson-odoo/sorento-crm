import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

/**
 * Choosing which photo of a product a brochure shows (S7.0), in a real browser.
 *
 * Run:
 *   set -a; . ./.env.local; set +a
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   npx playwright test e2e/dealer-kit-brochure-images.spec.ts --reporter=line
 *
 * ## Why the flow needs an end-to-end test at all
 *
 * `product_attachments.is_primary` decides a catalogue tile's photo, and it is
 * false on every photo row in the live data, so a tile shows whichever row was
 * linked first. `SRTWC286-SH` has 39 linked images including a blank page and
 * several other products' photographs. The whole point of the screen is that a
 * human choice reaches the tile - which is a chain across four layers (picker ->
 * PUT -> is_primary -> `product_images.primary_image_urls` -> tile), and no unit
 * test on either side can see the chain break in the middle.
 *
 * ## The database is a copy of production
 *
 * Setting a brochure image is a real change to a real product. Every test here
 * either asserts on read-only behaviour, or records the product's previous
 * choice first and puts it back in `afterAll` - restoring "nothing was chosen"
 * with a DELETE, which is the state every row in the live data is in. The one
 * collection the payoff test needs is created with the reserved `zzt-` prefix
 * and deleted again. There is no unscoped write anywhere in this file.
 *
 * ## Company scoping
 *
 * Products, their attachments and the picker are all scoped to the active
 * company, and only one company's products carry photos. The suite therefore
 * finds a company that HAS candidates, switches to it through the topbar
 * switcher a user would use, and switches back at the end - `last_active_company_id`
 * is user state and leaving it moved would be a change too.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;
const API_BASE = process.env.DEALER_KIT_E2E_API_BASE ?? 'http://localhost:8020';
const BROCHURE = `${API_BASE}/api/v1/master-data/product-attachments/brochure-images`;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the brochure image flow');

/**
 * Click without Playwright's actionability auto-wait.
 *
 * The protected layout fires a dev-ingest fetch that never resolves in a test
 * environment, so the page never reaches a settled state and a real `.click()`
 * hangs past its own timeout. Established in the other Dealer Kit specs.
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
 * Open a Radix trigger.
 *
 * Radix opens on POINTER events, so a synthetic `click` alone leaves the popover
 * shut, and the real mouse path waits on actionability this layout never reaches.
 */
async function openTrigger(locator: ReturnType<Page['locator']>) {
  await locator.waitFor({ state: 'attached', timeout: 20_000 });
  await locator.dispatchEvent('pointerdown', { button: 0, isPrimary: true, bubbles: true });
  await locator.dispatchEvent('mousedown', { button: 0, bubbles: true });
  await locator.dispatchEvent('click', { button: 0, bubbles: true });
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

interface Candidate {
  attachmentId: string;
  filename: string;
  url: string | null;
}
interface Row {
  productId: string;
  productCode: string;
  chosenAttachmentId: string | null;
  candidates: Candidate[];
}

/** The label the topbar switcher showed when the run started, so it can go back. */
let originalCompany: string | null = null;
/** Products this run wrote to, with whatever they held beforehand. */
const previousChoice = new Map<string, string | null>();
/** Collections this run created, by id. */
const createdCollections: string[] = [];
/**
 * The product the writing tests work on, found once.
 *
 * Cached because finding it costs several paged reads and every test needs it;
 * re-running the hunt per test turned a 40s suite into a four-minute one.
 */
let cachedRow: Row | null = null;

/**
 * The candidates of a row a test can actually click on and then assert about.
 *
 * Tiles are addressed by filename, and the live data links the SAME filename to
 * one product twice (`ACC-SRT1011` has two rows both called `SRT101.jpg`).
 * Clicking "the tile called X" when two tiles are called X means asserting about
 * a different photo than the one that was clicked, so those are left alone.
 */
function addressable(row: Row): Candidate[] {
  const seen = new Map<string, number>();
  for (const candidate of row.candidates) {
    seen.set(candidate.filename, (seen.get(candidate.filename) ?? 0) + 1);
  }
  return row.candidates.filter(
    (candidate) => candidate.url && seen.get(candidate.filename) === 1,
  );
}

/**
 * Switch the active company through the topbar control a user would use.
 *
 * Not the API: a user cannot reach another company any other way, and if the
 * switcher were broken the picker would silently list a company with nothing in
 * it. Returns false when there is no such company to move to.
 */
async function switchCompanyTo(page: Page, label: RegExp): Promise<boolean> {
  const switcher = page.locator('button[title="Switch active company"]').first();
  // The header mounts after the session resolves, so a bare `count()` here is 0
  // and the switch is skipped without anything failing - which is how a suite
  // reports green while never leaving an empty company.
  try {
    await switcher.waitFor({ state: 'attached', timeout: 20_000 });
  } catch {
    return false; // single-company user: the control is not rendered at all
  }

  await openTrigger(switcher);
  const options = page.getByRole('menuitem');
  // The menu is a portal that mounts a frame later; reading its items straight
  // after the trigger gives an empty list and nothing ever happens.
  await expect(options.first()).toBeVisible({ timeout: 15_000 });
  const wanted = options.filter({ hasText: label }).first();
  if ((await wanted.count()) === 0) {
    await page.keyboard.press('Escape');
    return false;
  }
  await wanted.dispatchEvent('click');
  return true;
}

/**
 * Make sure the active company is one whose products actually have photos.
 *
 * Only one company's products carry images, and which one is not something a
 * spec should hard-code, so this looks. If no company has any, it puts the
 * ORIGINAL company back before giving up - a probe that wanders off and leaves
 * the session somewhere else makes every later test assert against the wrong
 * data, which is worse than the skip it was trying to avoid.
 */
async function useCompanyWithCandidates(page: Page): Promise<Row | null> {
  if (cachedRow) return cachedRow;

  // The token is re-read on EVERY probe. Switching company re-mints the session,
  // and a token captured beforehand keeps answering for the company the run
  // started in - which looks exactly like "the new company has no photos".
  //
  // Paged, and deep: products are listed by code, and in the live data the first
  // product with two differently-named photos sits at position 2,488 and the
  // first that ALSO has a PDF at 4,247. A one-page probe reports the company as
  // having nothing to choose. Runs once per suite and is cached.
  const probe = async (): Promise<Row | null> => {
    const token = await apiToken(page.context().request);
    let fallback: Row | null = null;

    for (let index = 1; index <= 60; index += 1) {
      const response = await page.context().request.get(
        `${BROCHURE}?only_unset=false&limit=100&page=${index}`,
        { headers: auth(token) },
      );
      if (!response.ok()) return null;
      const body = (await response.json()) as { items?: Row[] };
      const items = body.items ?? [];

      for (const row of items.filter((candidate) => addressable(candidate).length >= 2)) {
        fallback = fallback ?? row;
        // Preferred: a product that ALSO has a PDF attached, so the "a spec
        // sheet is never offered as a photo" rule is exercised against a real
        // PDF rather than skipped with a warning.
        const attachments = await page.context().request.get(
          `${API_BASE}/api/v1/master-data/product-attachments/product/${row.productId}`,
          { headers: auth(token) },
        );
        if (!attachments.ok()) continue;
        const linked = (await attachments.json()) as Array<{
          attachment?: { mime_type?: string | null; original_filename?: string | null };
        }>;
        const hasPdf = (Array.isArray(linked) ? linked : []).some((link) =>
          /pdf/i.test(`${link.attachment?.mime_type ?? ''} ${link.attachment?.original_filename ?? ''}`),
        );
        if (hasPdf) {
          cachedRow = row;
          return row;
        }
      }

      if (items.length === 0) break;
    }

    cachedRow = fallback;
    return fallback;
  };

  const here = await probe();
  if (here) return here;

  const switcher = page.locator('button[title="Switch active company"]').first();
  try {
    await switcher.waitFor({ state: 'attached', timeout: 20_000 });
  } catch {
    return null;
  }
  originalCompany = originalCompany ?? (await switcher.innerText()).split('\n')[0].trim();

  await openTrigger(switcher);
  const options = page.getByRole('menuitem');
  await expect(options.first()).toBeVisible({ timeout: 15_000 });
  const labels = (await options.allTextContents()).map((text) => text.split('\n')[0].trim());
  await page.keyboard.press('Escape');

  for (const label of labels) {
    if (!label || label === originalCompany) continue;
    if (!(await switchCompanyTo(page, new RegExp(label, 'i')))) continue;
    // The switch persists server-side and re-mints the session, so poll: a
    // scoped call issued too early still answers for the previous company.
    for (let attempt = 0; attempt < 10; attempt += 1) {
      const row = await probe();
      if (row) return row;
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
  }

  // Nothing anywhere. Put the session back where it was found.
  if (originalCompany) await switchCompanyTo(page, new RegExp(originalCompany, 'i'));
  return null;
}

/** Reach the picker the way a user does: sidebar group, then the leaf. */
async function openPicker(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });

  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }

  const link = page.getByRole('link', { name: /brochure images/i }).first();
  await expect(link, 'Brochure Images leaf should render inside the group').toBeVisible({
    timeout: 15_000,
  });
  expect(await link.getAttribute('href')).toBe('/dealer-kit/brochure-images');

  await link.dispatchEvent('click');
  await page.waitForURL(/brochure-images/, { timeout: 30_000 });
  await settled(page);
}

/**
 * Wait for the list to have ANSWERED.
 *
 * The counter renders from `?? 0` while the query is in flight, so it reads
 * "0 of 0 still to choose" during loading and is indistinguishable from a real
 * empty result. Asserting on it without waiting for a row or the empty card is
 * how a test passes against a screen that never loaded.
 */
async function settled(page: Page) {
  await expect(page.locator('[data-dk-bi-remaining]')).toBeVisible({ timeout: 40_000 });
  await expect(page.locator('[data-dk-bi-loading]')).toHaveCount(0, { timeout: 60_000 });
  await expect(
    page.locator('[data-dk-bi-row], [data-dk-bi-empty], [data-dk-bi-error]').first(),
  ).toBeVisible({ timeout: 60_000 });
}

/** Search the picker for one product code and wait for the debounced refetch. */
async function search(page: Page, code: string) {
  const request = page.waitForRequest(
    (candidate) => candidate.url().includes('brochure-images') && candidate.url().includes('query='),
    { timeout: 30_000 },
  );
  await type(page.locator('#dk-bi-search'), code);
  await request;
  await expect(page.locator(`[data-dk-bi-row="${code}"]`)).toBeVisible({ timeout: 30_000 });
}

/** Remember what a product held before this run touches it, so it can go back. */
function remember(row: Row) {
  if (previousChoice.has(row.productId)) return;
  previousChoice.set(row.productId, row.chosenAttachmentId);
}

/**
 * A product with photos to choose between, in the company this test is in.
 *
 * Set in `beforeEach` so the READ-ONLY tests run against the same company as
 * the writing ones: a promotion's products, and every photo, belong to one
 * company, and a suite that half-switched would assert against an empty list.
 */
let workingRow: Row | null = null;

test.describe('Dealer Kit brochure images', () => {
  // Each test logs in fresh, may switch company and does real server round trips.
  test.describe.configure({ timeout: 180_000 });

  test.beforeEach(async ({ page }) => {
    await login(page);
    workingRow = await useCompanyWithCandidates(page);
  });

  test.afterAll(async ({ browser }, testInfo) => {
    if (!EMAIL || !PASSWORD) return;
    if (previousChoice.size === 0 && createdCollections.length === 0 && !originalCompany) return;

    const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
    const page = await context.newPage();
    try {
      await login(page);
      const token = await apiToken(context.request);

      // Put every product back exactly as it was found. Restoring "nothing
      // chosen" is a DELETE, which is the state the live rows are all in.
      for (const [productId, before] of previousChoice) {
        const response = before
          ? await context.request.put(`${BROCHURE}/${productId}`, {
              headers: auth(token),
              data: { attachment_id: before },
            })
          : await context.request.delete(`${BROCHURE}/${productId}`, { headers: auth(token) });
        if (!response.ok()) {
          console.warn(`[cleanup] product ${productId} not restored: ${response.status()}`);
        }
      }

      for (const id of createdCollections) {
        const response = await context.request.delete(
          `${API_BASE}/api/v1/dealer-kit/collections/${id}`,
          { headers: auth(token) },
        );
        if (!response.ok()) console.warn(`[cleanup] collection ${id} survived: ${response.status()}`);
      }

      // `last_active_company_id` is user state, so a run that moved it puts it
      // back - otherwise the next person to log in lands in a company they did
      // not choose.
      if (originalCompany) {
        const restored = await switchCompanyTo(page, new RegExp(originalCompany, 'i'));
        if (!restored) console.warn(`[cleanup] active company left at something other than ${originalCompany}`);
        // Give the switch time to persist before the context closes under it.
        await page.waitForTimeout(3_000);
      }
    } catch (error) {
      console.warn(`[cleanup] skipped: ${String(error).slice(0, 200)}`);
    } finally {
      await context.close();
    }
  });

  test('opens from the sidebar and lists real products', async ({ page }) => {
    const listed = page.waitForRequest(
      (request) =>
        request.url().includes('/api/v1/master-data/product-attachments/brochure-images') &&
        request.method() === 'GET',
      { timeout: 40_000 },
    );

    await openPicker(page);

    // The hook -> service -> api-client chain, asserted on the wire rather than
    // on rendered text: a list that renders from a cache would pass otherwise.
    const url = new URL((await listed).url());
    expect(url.searchParams.get('only_unset')).toBe('true');
    expect(url.searchParams.get('page')).toBe('1');
    expect(url.searchParams.get('limit')).toBe('25');

    // Real rows, from the server. `settled` inside openPicker has already
    // waited out the loading state, whose counter also reads "0 of 0".
    expect(await page.locator('[data-dk-bi-row]').count()).toBeGreaterThan(0);
    // The counter is the screen's whole point - how much work is left - and it
    // has to be a real figure rather than the zero it renders while loading.
    const counter = await page.locator('[data-dk-bi-remaining]').innerText();
    expect(counter).toMatch(/\d+ of \d+ still to choose/);
    expect(Number(counter.split(' of ')[1].split(' ')[0])).toBeGreaterThan(0);
  });

  test('a product with no photo says so instead of being hidden', async ({ page }) => {
    await openPicker(page);

    // 465 of the flyer's codes have no photo at all, and the answer there is a
    // photo shoot rather than a click. Dropping them would hide the work.
    const withoutCandidates = page
      .locator('[data-dk-bi-row]')
      .filter({ hasText: /No photo is linked to this product yet/i });

    if ((await withoutCandidates.count()) === 0) {
      test.skip(true, 'this company has a photo linked to every product on page 1');
    }
    await expect(withoutCandidates.first()).toBeVisible();
    // And the page says how many, so the size of the gap is visible.
    await expect(page.getByText(/no photo to choose from/i)).toBeVisible();
  });

  test('the promotion filter narrows the list and names the promotion', async ({ page }) => {
    await openPicker(page);
    const everything = Number(
      (await page.locator('[data-dk-bi-remaining]').innerText()).split(' of ')[1].split(' ')[0],
    );
    expect(everything, 'the unfiltered list should hold products').toBeGreaterThan(0);

    await openTrigger(page.locator('#dk-bi-promotion'));
    const options = page.getByRole('option');
    await expect(options.first(), 'the promotion filter should offer promotions').toBeVisible({
      timeout: 30_000,
    });

    // A promotion that actually holds products, so "the list narrows" is a real
    // narrowing rather than an empty promotion emptying the screen. The option
    // states its product count for exactly this reason.
    const texts = await options.allTextContents();
    const index = texts.findIndex((text) => /[1-9]\d* products?/.test(text));
    expect(index, 'at least one promotion should hold products').toBeGreaterThanOrEqual(0);
    const option = options.nth(index);
    const label = ((await option.textContent()) ?? '').trim();
    // Never a uuid: the label is the promotion's description, or "Untitled
    // promotion" when it has none.
    expect(label).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-/i);

    const filtered = page.waitForResponse(
      (response) =>
        response.url().includes('brochure-images') && response.url().includes('promotion_id='),
      { timeout: 30_000 },
    );
    await option.dispatchEvent('click');
    const body = (await (await filtered).json()) as { total?: number };

    // A promotion is a SUBSET of the catalogue, asserted on the payload rather
    // than on rendered text so a stale render cannot pass it.
    expect(body.total ?? 0).toBeLessThan(everything);

    // And the trigger names the promotion, never its id.
    const trigger = page.locator('#dk-bi-promotion');
    await expect(trigger).toContainText(label.split('\n')[0].trim().slice(0, 15));
    await expect(trigger).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-/i);
  });

  test('choosing a photo marks it, drops the counter, and the tile follows', async ({ page }) => {
    const target = workingRow;
    test.skip(!target, 'no company reachable by this user has a product with two photos to choose between');

    const request = page.context().request;
    const token = await apiToken(request);
    remember(target!);

    // A catalogue collection holding exactly this product, so the payoff can be
    // read off the very payload TileGrid renders from. Named with the reserved
    // prefix and deleted in afterAll.
    const created = await request.post(`${API_BASE}/api/v1/dealer-kit/collections`, {
      headers: auth(token),
      data: {
        scope: 'library',
        name: `zzt-brochure-${Math.random().toString(36).slice(2, 8)}`,
        pinned_product_ids: [target!.productId],
        excluded_product_ids: [],
        manual_order: [],
      },
    });
    expect(created.ok(), 'the payoff needs a collection to look at').toBeTruthy();
    const collection = (await created.json()) as { id: string };
    createdCollections.push(collection.id);

    const tileImage = async (): Promise<string> => {
      const response = await request.get(
        `${API_BASE}/api/v1/dealer-kit/collections/${collection.id}/resolve`,
        { headers: auth(token) },
      );
      const body = (await response.json()) as { tiles?: Array<{ imageUrl?: string | null }> };
      return decodeURIComponent(String(body.tiles?.[0]?.imageUrl ?? '')).split('?')[0];
    };

    // Nothing chosen: the tile falls back to whichever row was linked first.
    await request.delete(`${BROCHURE}/${target!.productId}`, { headers: auth(token) });
    const fallback = await tileImage();
    expect(fallback, 'this product should have a photo to fall back to').not.toBe('');

    // A candidate that is NOT the fallback, so the assertion cannot pass by
    // luck, and whose FILENAME is unique in the row - the tiles are addressed by
    // filename and the live data links the same name twice to one product, so a
    // duplicate would have the test click one tile and assert about another.
    const pick = addressable(target!).find(
      (candidate) => !fallback.includes(candidate.attachmentId),
    );
    expect(pick, 'the probe only accepts products with two addressable photos').toBeTruthy();

    await openPicker(page);
    await search(page, target!.productCode);

    const row = page.locator(`[data-dk-bi-row="${target!.productCode}"]`);
    const before = await page.locator('[data-dk-bi-remaining]').innerText();
    const tile = row.locator(`[data-dk-bi-candidate="${pick!.filename}"]`).first();
    await expect(tile, 'the candidate should be offered in the picker').toBeVisible({
      timeout: 30_000,
    });

    const saved = page.waitForResponse(
      (response) => response.request().method() === 'PUT' && /brochure-images/.test(response.url()),
      { timeout: 30_000 },
    );
    await tile.dispatchEvent('click');
    const response = await saved;

    // The right product, the right payload, and the server agreeing.
    expect(response.status()).toBe(200);
    expect(response.url()).toContain(`/brochure-images/${target!.productId}`);
    expect(JSON.parse(response.request().postData() ?? '{}')).toEqual({
      attachment_id: pick!.attachmentId,
    });
    expect(await response.json()).toMatchObject({
      productId: target!.productId,
      chosenAttachmentId: pick!.attachmentId,
    });

    // The mark lands on the clicked tile, and on exactly one tile.
    await expect(tile).toHaveAttribute('aria-pressed', 'true');
    // One less thing to do. The default filter is "still without an image", so
    // the answered product leaves the worklist and the counter drops with it.
    await expect(page.locator('[data-dk-bi-remaining]')).not.toHaveText(before, { timeout: 30_000 });

    // THE PAYOFF. `product_images.py` orders by `is_primary`, so the catalogue
    // tile has to show the photo somebody just chose, with no renderer change.
    await expect
      .poll(tileImage, { timeout: 30_000 })
      .toContain(pick!.attachmentId);
    expect(await tileImage()).not.toBe(fallback);
  });

  test('choosing again moves the mark rather than adding a second', async ({ page }) => {
    const target = workingRow;
    test.skip(!target, 'no company reachable by this user has a product with two photos to choose between');

    const request = page.context().request;
    const token = await apiToken(request);
    remember(target!);

    // Two tiles addressed by name, not by position: the list re-sorts the chosen
    // image to the front on every refetch, so an index would point at a
    // different photo after the first click.
    const unique = addressable(target!);
    expect(unique.length, 'the probe only accepts products with two addressable photos')
      .toBeGreaterThanOrEqual(2);

    await openPicker(page);
    // Reviewing an answered product means turning the worklist filter off; with
    // it on the row leaves the list the moment it is answered.
    await tap(page.locator('#dk-bi-only-unset'));
    await search(page, target!.productCode);

    const row = page.locator(`[data-dk-bi-row="${target!.productCode}"]`);
    const tileFor = (filename: string) =>
      row.locator(`[data-dk-bi-candidate="${filename}"]`).first();

    for (const candidate of unique.slice(0, 2)) {
      const saved = page.waitForResponse(
        (response) => response.request().method() === 'PUT' && /brochure-images/.test(response.url()),
        { timeout: 30_000 },
      );
      await tileFor(candidate.filename).dispatchEvent('click');
      const response = await saved;
      expect(response.status()).toBe(200);
      expect(await response.json()).toMatchObject({ chosenAttachmentId: candidate.attachmentId });
      await expect(tileFor(candidate.filename)).toHaveAttribute('aria-pressed', 'true');
      // Exactly one chosen image per product. Two at once and the tile's photo
      // is back at the mercy of row order, which is the defect this removes.
      await expect(row.locator('[data-dk-bi-candidate][aria-pressed="true"]')).toHaveCount(1);
    }

    // Clicking the chosen one again is idempotent, not a toggle: a double click
    // must never leave a product with no brochure image at all.
    await tileFor(unique[1].filename).dispatchEvent('click');
    await expect(row.locator('[data-dk-bi-candidate][aria-pressed="true"]')).toHaveCount(1);
    await expect(row.getByText('chosen', { exact: true })).toBeVisible();
  });

  test('the mark, and the way to clear it, are on the product too', async ({ page }) => {
    const target = workingRow;
    test.skip(!target, 'no company reachable by this user has a product with two photos to choose between');

    const request = page.context().request;
    const token = await apiToken(request);
    remember(target!);

    const pick = target!.candidates[0];
    const set = await request.put(`${BROCHURE}/${target!.productId}`, {
      headers: auth(token),
      data: { attachment_id: pick.attachmentId },
    });
    expect(set.ok()).toBeTruthy();

    // Via the sidebar, because a deep link would hide a mis-gated menu entry.
    await page.goto('/', { waitUntil: 'commit' });
    // Product Management -> Products -> All Products, each one expanded rather
    // than jumped over: a leaf hidden behind a collapsed group is a real bug and
    // a deep link would never see it.
    for (const label of [/product management/i, /^products$/i]) {
      const parent = page.getByRole('button', { name: label }).first();
      await expect(parent, `sidebar group ${label} should render`).toBeVisible({ timeout: 20_000 });
      if ((await parent.getAttribute('aria-expanded')) !== 'true') {
        await parent.dispatchEvent('click');
      }
    }
    const products = page.getByRole('link', { name: /all products/i }).first();
    await expect(products).toBeVisible({ timeout: 15_000 });
    const href = await products.getAttribute('href');
    // The tab only offers the control in edit mode, which is its own route.
    await page.goto(`${href}/${target!.productId}/edit`, { waitUntil: 'commit' });

    const tab = page.getByRole('tab', { name: /attachments/i }).first();
    await expect(tab).toBeVisible({ timeout: 30_000 });
    const box = await tab.boundingBox();
    // Radix tabs key off pointer events, so a synthetic click does not move them.
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);

    // Exactly one row carries the badge, however many images are attached.
    await expect(page.getByText('Brochure image').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Brochure image')).toHaveCount(1);

    // A spec sheet rendered as the product photo is worse than no photo, so a
    // PDF row is never offered the control - asserted per PDF row rather than on
    // a total, which passes for the wrong reason whenever an image is chosen.
    const rows = page.locator('[data-testid^="product-attachment-row-"]');
    let pdfRows = 0;
    for (let index = 0; index < (await rows.count()); index += 1) {
      const row = rows.nth(index);
      if (!/\.pdf\b/i.test((await row.innerText()) ?? '')) continue;
      pdfRows += 1;
      await expect(row.getByRole('button', { name: /brochure image/i })).toHaveCount(0);
    }
    if (pdfRows === 0) {
      console.warn('[brochure] this product has no PDF attachment; the PDF rule was not exercised');
    }

    // Clearing is destructive enough to confirm - never a one-click.
    await tap(page.getByRole('button', { name: /clear brochure image/i }).first());
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog).toContainText(/clear brochure image\?/i);
    // Says what clearing does NOT do. "Clear" next to a file list reads as
    // "delete the file", and the copy exists to say it does not.
    await expect(dialog).toContainText(/stays attached/i);
    // Cancel leaves the choice alone, which is the half of a confirmation that
    // is usually left untested.
    await tap(page.getByRole('button', { name: /^cancel$/i }));
    await expect(page.getByText('Brochure image')).toHaveCount(1);
  });
});

// A separate describe with test.use: setViewportSize mid-test wedges against the
// protected layout's never-resolving fetch, which is why the other Dealer Kit
// specs do it this way too.
test.describe('Dealer Kit brochure images at 375px', () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test('does not scroll the body sideways', async ({ page }) => {
    await login(page);

    // On a phone the sidebar is a drawer behind the header's menu button, and
    // reaching the screen has to go through it - a deep link would say nothing
    // about whether a phone user can get here at all.
    await page.goto('/', { waitUntil: 'commit' });
    const menu = page.locator('header button[aria-haspopup="dialog"]').first();
    await expect(menu, 'the phone header should offer a navigation drawer').toBeVisible({
      timeout: 20_000,
    });
    await openTrigger(menu);

    const group = page.getByRole('button', { name: /dealer kit/i }).first();
    await expect(group).toBeVisible({ timeout: 20_000 });
    if ((await group.getAttribute('aria-expanded')) !== 'true') await group.dispatchEvent('click');
    const link = page.getByRole('link', { name: /brochure images/i }).first();
    await expect(link).toBeVisible({ timeout: 15_000 });
    await link.dispatchEvent('click');
    await page.waitForURL(/brochure-images/, { timeout: 30_000 });
    await settled(page);

    // The filters, the counter and a grid of 112px thumbnails all have to fit a
    // phone. Horizontal body scroll is the tell that one of them does not.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // And the controls are still reachable rather than clipped off the edge.
    for (const selector of ['#dk-bi-promotion', '#dk-bi-search', '#dk-bi-only-unset']) {
      const box = await page.locator(selector).boundingBox();
      expect(box, `${selector} should be laid out`).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(376);
    }
  });
});

test.describe('Dealer Kit brochure images at 1280px', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test('lays out on a laptop without sideways scroll or console errors', async ({ page }) => {
    // Console noise is a finding, not decoration: a failed thumbnail sign or a
    // React key warning in a grid of tiles both show up here and nowhere else.
    const problems: string[] = [];
    page.on('console', (message) => {
      if (message.type() !== 'error') return;
      const text = message.text();
      // Ignored on purpose: the layout fires a dev-ingest request at a port
      // nothing listens on in a test environment, which is not this screen.
      if (/7242|ERR_CONNECTION_REFUSED|favicon/i.test(text)) return;
      problems.push(text.slice(0, 200));
    });
    page.on('pageerror', (error) => problems.push(`pageerror: ${String(error).slice(0, 200)}`));

    await login(page);
    await openPicker(page);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // The thumbnails are the screen. One that renders 0x0 is a signed URL the
    // browser could not load, and it looks identical to "no photo" in a
    // screenshot.
    const images = page.locator('[data-dk-bi-candidate] img');
    if ((await images.count()) > 0) {
      await expect
        .poll(async () => images.first().evaluate((node) => (node as HTMLImageElement).naturalWidth), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
    }

    expect(problems, `console errors on the picker: ${problems.join(' | ')}`).toHaveLength(0);
  });
});
