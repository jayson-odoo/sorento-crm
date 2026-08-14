import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

/**
 * Promotional pricing on catalogue tiles (S7.2), in a real browser.
 *
 * Run:
 *   set -a; . ./.env.local; set +a
 *   PORTAL_E2E_BASE_URL=http://localhost:3020 \
 *   npx playwright test e2e/dealer-kit-offer-pricing.spec.ts --reporter=line
 *
 * ## What can break here that no unit test sees
 *
 * `dealer_kit.page.promotion_id` decides which offer prices a brochure, and the
 * figure a reader ends up looking at crosses five layers: the promotion link on
 * the page, `pricing.resolve_prices`, the tile resolver's formatting, the public
 * catalogue payload, and `TilePrices` in `TileGrid`. The failure that matters is
 * silent: swap the two figures and BOTH numbers are still on screen, still in
 * the right currency, still the right pair - only the strikethrough is on the
 * wrong one, and the flyer then advertises a price nobody is charging. So every
 * assertion here names WHICH element carries the line, never "two prices are
 * shown".
 *
 *   `price`      = the LIST price, the higher original figure ("LP: RM 1,260").
 *                  The strikethrough belongs on THIS one.
 *   `offerPrice` = the PROMOTIONAL price ("SP RM 599"), the prominent figure.
 *
 * ## The database is a copy of production
 *
 * Linking a promotion to a real page is a real change, so this suite touches no
 * real row. It creates its own `zzt-` page, its own `zzt-` collection and its
 * own `zzt-` promotion, and deletes all three in `afterAll`. The one REAL
 * promotion it uses (`_SORENTO A3 FLYER 2025-2026_compressed`) is only ever
 * READ - and it is linked to the suite's OWN page, never to anybody else's.
 * There is no unscoped write anywhere in this file.
 *
 * ## Company scoping
 *
 * Promotions, products and pages are company-scoped, and the flyer's products
 * belong to Sorento. The suite switches to that company through the topbar
 * control a user would use and switches back at the end, because
 * `last_active_company_id` is user state and leaving it moved is a change too.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;
const API_BASE = process.env.DEALER_KIT_E2E_API_BASE ?? 'http://localhost:8020';
const KIT = `${API_BASE}/api/v1/dealer-kit`;
const MARKETING = `${API_BASE}/api/v1/marketing/promotions`;

/**
 * The company whose catalogue this suite prices, and the product it prices.
 *
 * A code rather than a uuid, resolved through the API, so the spec survives a
 * reseed. `SRTWC286-SH` is the worked example from the flyer: RM 1,260 list.
 */
const COMPANY = /sorento/i;
const OFFER_CODE = 'SRTWC286-SH';
/** What this suite's own promotion charges for it. Lower than list, on purpose. */
const OFFER_PRICE = '599';

/**
 * A REAL promotion, only ever read. It is expired (ended 2026-05-31) and
 * switched off, which is exactly why it earns a test of its own: linking it must
 * price nothing at all.
 */
const REAL_PROMOTION = '_SORENTO A3 FLYER 2025-2026_compressed';

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the offer pricing flow');

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
  throw new Error('no backend session token; the suite cannot set up or clean up');
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` };
}

/**
 * Switch the active company through the topbar control a user would use.
 *
 * Not the API: a user cannot reach another company any other way, and a broken
 * switcher would leave this suite asserting against an empty catalogue while
 * reporting green.
 */
async function switchCompanyTo(page: Page, label: RegExp): Promise<boolean> {
  const switcher = page.locator('button[title="Switch active company"]').first();
  try {
    await switcher.waitFor({ state: 'attached', timeout: 20_000 });
  } catch {
    return false; // single-company user: the control is not rendered at all
  }

  if (label.test((await switcher.innerText()).split('\n')[0].trim())) return true;

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
  // The switch persists server-side and re-mints the session; a scoped call
  // issued too early still answers for the previous company.
  await page.waitForTimeout(3_000);
  return true;
}

/**
 * The company the USER was left in, read as an id rather than a label.
 *
 * Recorded once, from the server, and restored by id at the end. Reading it off
 * the topbar instead is what let an earlier run leave the account somewhere
 * else: a run that failed to restore made the NEXT run record the wrong
 * "original", and after two runs nothing remembered where the user actually
 * was. An id from `my-context` cannot drift that way.
 */
async function rememberHomeCompany(page: Page) {
  if (homeCompanyId !== undefined) return;
  const token = await apiToken(page.context().request);
  const response = await page.context().request.get(
    `${API_BASE}/api/v1/system/companies/my-context`,
    { headers: auth(token) },
  );
  if (!response.ok()) return;
  const body = (await response.json()) as { last_active_company_id?: string | null };
  homeCompanyId = body.last_active_company_id ?? null;
}

interface Fixture {
  pageId: string;
  slug: string;
  name: string;
  publicPath: string;
  collectionId: string;
  promotionId: string;
  /** The product this suite's promotion discounts. */
  offerProductId: string;
  offerProductCode: string;
  /** Its list price, as the tile formats it, e.g. "MYR 1,260.00". */
  listPriceText: string;
  /** The offer, formatted the same way. */
  offerPriceText: string;
  /** A product the promotion does NOT cover. */
  plainProductId: string;
  plainProductCode: string;
  plainPriceText: string;
}

let fixture: Fixture | null = null;
/**
 * The company id the account was left in, so the run can put it back.
 *
 * `undefined` means "not read yet"; `null` means the user genuinely has none.
 */
let homeCompanyId: string | null | undefined;
/** Everything this run created, torn down in reverse. */
const created = { pageId: '', collectionId: '', promotionId: '' };

function money(value: number): string {
  return `MYR ${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * A published brochure holding one discounted product and one that is not.
 *
 * Built through the API rather than by clicking, because the layout editor is
 * S1's flow and has its own coverage: what THIS suite is about starts at "a page
 * exists and is live". Every row it writes carries the reserved `zzt-` prefix.
 */
async function buildFixture(page: Page): Promise<Fixture | null> {
  if (fixture) return fixture;

  const request = page.context().request;
  // Re-read AFTER the company switch: a token minted beforehand keeps answering
  // for the company the run started in.
  const token = await apiToken(request);

  const find = async (query: string) => {
    const response = await request.get(
      `${API_BASE}/api/v1/master-data/products/?query=${encodeURIComponent(query)}&limit=25`,
      { headers: auth(token) },
    );
    if (!response.ok()) return [];
    const body = (await response.json()) as {
      data?: Array<{ id: string; product_code: string; list_price?: string | number | null; is_active?: boolean; is_discontinued?: boolean }>;
    };
    return body.data ?? [];
  };

  const offerProduct = (await find(OFFER_CODE)).find((row) => row.product_code === OFFER_CODE);
  if (!offerProduct) return null;

  // Anything else sellable and priced. It is "not in the promotion" by
  // construction: the promotion below holds exactly one product.
  const plainProduct = (await find('SRTWC')).find(
    (row) =>
      row.id !== offerProduct.id &&
      row.is_active !== false &&
      row.is_discontinued !== true &&
      Number(row.list_price ?? 0) > 0,
  );
  if (!plainProduct) return null;

  const suffix = Math.random().toString(36).slice(2, 8);

  // A promotion of this suite's own, so the figures are a genuine discount and
  // the window is open today. Every live promotion in the real data either
  // ended, is switched off, or prices its products ABOVE list - none of which
  // can demonstrate a struck-through list price.
  const today = new Date();
  const iso = (offsetDays: number) =>
    new Date(today.getTime() + offsetDays * 86_400_000).toISOString().slice(0, 10);
  const promotion = await request.post(`${MARKETING}/`, {
    headers: auth(token),
    data: {
      description: `zzt-offer-pricing-${suffix}`,
      start_date: iso(-1),
      end_date: iso(30),
      is_active: true,
      // `end_user` is what an anonymous reader resolves to, and staff previewing
      // hold no trade code either, so this one audience covers both surfaces.
      access_levels: ['end_user', 'dealer'],
    },
  });
  expect(promotion.ok(), 'the suite needs a promotion of its own').toBeTruthy();
  created.promotionId = ((await promotion.json()) as { id: string }).id;

  const line = await request.post(`${MARKETING}/${created.promotionId}/products/`, {
    headers: auth(token),
    data: { product_id: offerProduct.id, promotion_price: OFFER_PRICE },
  });
  expect(line.ok(), 'the promotion needs the product it discounts').toBeTruthy();

  const pageRow = await request.post(`${KIT}/pages`, {
    headers: auth(token),
    data: { name: `zzt-offer-pricing-${suffix}`, slug: `zzt-offer-pricing-${suffix}` },
  });
  expect(pageRow.ok(), 'the suite needs a page of its own').toBeTruthy();
  const pageBody = (await pageRow.json()) as { id: string; slug: string; name: string; publicPath: string };
  created.pageId = pageBody.id;

  const collection = await request.post(`${KIT}/collections`, {
    headers: auth(token),
    data: {
      scope: 'page',
      page_id: pageBody.id,
      pinned_product_ids: [offerProduct.id, plainProduct.id],
      excluded_product_ids: [],
      manual_order: [],
    },
  });
  expect(collection.ok(), 'the page needs tiles to price').toBeTruthy();
  created.collectionId = ((await collection.json()) as { id: string }).id;

  const doc = {
    sections: [
      {
        id: 'sec-zzt',
        name: 'Section 1',
        style: { paddingY: 'lg', background: 'transparent' },
        blocks: [
          {
            id: 'blk-zzt',
            type: 'collection',
            props: {
              kind: 'collection',
              columns: { mobile: 1, tablet: 2, desktop: 2 },
              collectionId: created.collectionId,
              // No design bound, so the renderer falls back to
              // ['image','name','code','price'] - the binding EVERY design saved
              // before offers existed carries, and the one that must start
              // showing the offer without anybody re-editing anything.
              tileTemplateId: null,
            },
            hideInPrint: false,
          },
        ],
        layouts: {
          mobile: { blocks: { 'blk-zzt': { colStart: 1, colSpan: 4, rowStart: 1, rowSpan: 14 } }, isDerived: true },
          tablet: { blocks: { 'blk-zzt': { colStart: 1, colSpan: 8, rowStart: 1, rowSpan: 14 } }, isDerived: true },
          desktop: { blocks: { 'blk-zzt': { colStart: 1, colSpan: 12, rowStart: 1, rowSpan: 14 } }, isDerived: false },
        },
        printMode: 'include',
      },
    ],
    printProfile: {
      cover: false,
      margins: { top: 15, left: 15, right: 15, bottom: 15 },
      pageSize: 'A4',
      orientation: 'portrait',
      headerFooter: { left: '', right: '', pageNumbers: true },
    },
  };

  const version = await request.post(`${KIT}/pages/${pageBody.id}/versions`, {
    headers: auth(token),
    data: { doc, commitMessage: 'zzt fixture' },
  });
  expect(version.ok(), 'the fixture page needs a version').toBeTruthy();
  const versionId = ((await version.json()) as { id: string }).id;

  // Published, because the public catalogue deliberately refuses to fall back to
  // an unpublished draft.
  const published = await request.put(`${KIT}/pages/${pageBody.id}/labels/published`, {
    headers: auth(token),
    data: { versionId },
  });
  expect(published.ok(), 'the fixture page needs to be live').toBeTruthy();

  fixture = {
    pageId: pageBody.id,
    slug: pageBody.slug,
    name: pageBody.name,
    publicPath: pageBody.publicPath,
    collectionId: created.collectionId,
    promotionId: created.promotionId,
    offerProductId: offerProduct.id,
    offerProductCode: offerProduct.product_code,
    listPriceText: money(Number(offerProduct.list_price)),
    offerPriceText: money(Number(OFFER_PRICE)),
    plainProductId: plainProduct.id,
    plainProductCode: plainProduct.product_code,
    plainPriceText: money(Number(plainProduct.list_price)),
  };
  return fixture;
}

/** Link (or clear) the page's promotion without going through the UI. */
async function setPromotion(page: Page, promotionId: string | null) {
  const token = await apiToken(page.context().request);
  const response = await page.context().request.put(
    `${KIT}/pages/${fixture!.pageId}/promotion`,
    { headers: auth(token), data: { promotionId } },
  );
  expect(response.ok()).toBeTruthy();
}

/** Reach the page editor the way a user does: sidebar group, leaf, then the row. */
async function openEditor(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });

  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }

  const link = page.getByRole('link', { name: /catalogue pages/i }).first();
  await expect(link, 'Catalogue Pages leaf should render inside the group').toBeVisible({
    timeout: 15_000,
  });
  expect(await link.getAttribute('href')).toBe('/dealer-kit');
  await link.dispatchEvent('click');
  await page.waitForURL(/\/dealer-kit$/, { timeout: 30_000 });

  // Filtered rather than paged to: the list holds every page in the company and
  // the fixture is not necessarily on page one.
  await type(page.getByRole('textbox', { name: /search pages/i }), fixture!.name);
  const row = page.getByRole('row').filter({ hasText: fixture!.name }).first();
  await expect(row, 'the fixture page should be listed').toBeVisible({ timeout: 30_000 });
  await row.dispatchEvent('click');
  await page.waitForURL(new RegExp(`/dealer-kit/pages/${fixture!.pageId}`), { timeout: 30_000 });
  await expect(page.locator('#dk-page-promotion')).toBeVisible({ timeout: 30_000 });
}

/** Pick a promotion in the page's own control, by the name a human reads. */
async function pickPromotion(page: Page, label: string) {
  await openTrigger(page.locator('#dk-page-promotion'));
  const search = page.getByPlaceholder('Search...').first();
  await expect(search).toBeVisible({ timeout: 15_000 });
  await search.fill(label);

  const option = page.getByRole('option').filter({ hasText: label }).first();
  await expect(option, `the control should offer "${label}"`).toBeVisible({ timeout: 30_000 });

  const saved = page.waitForResponse(
    (response) => response.request().method() === 'PUT' && /\/promotion$/.test(response.url()),
    { timeout: 30_000 },
  );
  await option.dispatchEvent('click');
  return saved;
}

/** What `/api/v1/public/c/{company}/{slug}` sends the renderer. */
interface CataloguePayload {
  collections: Record<
    string,
    Array<{ productId: string; price: string | null; offerPrice: string | null }>
  >;
}

/** The tile for one product code, on whichever catalogue surface is open. */
function tile(page: Page, productId: string) {
  return page.locator(`[data-dk-tile="${productId}"]`);
}

/**
 * Collect console errors from here on. Noise is a finding, not decoration.
 *
 * The dev-ingest request the protected layout fires at a port nothing listens on
 * in a test environment is ignored; it is not this feature.
 */
function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (/7242|ERR_CONNECTION_REFUSED|favicon/i.test(text)) return;
    problems.push(text.slice(0, 200));
  });
  page.on('pageerror', (error) => problems.push(`pageerror: ${String(error).slice(0, 200)}`));
  return problems;
}

/** Is this element actually drawn with a line through it? */
async function struckThrough(locator: ReturnType<Page['locator']>): Promise<boolean> {
  return locator.evaluate((node) =>
    getComputedStyle(node as Element).textDecorationLine.includes('line-through'),
  );
}

test.describe('Dealer Kit offer pricing', () => {
  // Every test logs in fresh, switches company and does real server round trips.
  test.describe.configure({ timeout: 240_000 });

  test.beforeEach(async ({ page }) => {
    await login(page);
    await rememberHomeCompany(page);
    await switchCompanyTo(page, COMPANY);
    await buildFixture(page);
  });

  test('the promotion control names the promotion, never a uuid', async ({ page }) => {
    test.skip(!fixture, 'the fixture catalogue could not be built in this company');
    const problems = watchConsole(page);
    await setPromotion(page, null);
    await openEditor(page);

    // An empty control has to read as finished rather than unanswered.
    await expect(page.locator('#dk-page-promotion')).toContainText('List prices only');

    const saved = await pickPromotion(page, REAL_PROMOTION);
    expect(saved.status()).toBe(200);
    expect(JSON.parse(saved.request().postData() ?? '{}')).toMatchObject({
      promotionId: expect.stringMatching(/^[0-9a-f-]{36}$/i),
    });
    // The BACKEND resolves the label; the control must never have to invent one.
    expect(await saved.json()).toMatchObject({ promotionLabel: REAL_PROMOTION });

    const trigger = page.locator('#dk-page-promotion');
    await expect(trigger).toContainText(REAL_PROMOTION);
    await expect(trigger).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-/i);

    // Saved state, not a draft: a reload has to show the same answer, or the
    // decision was only ever in the browser.
    await page.reload({ waitUntil: 'commit' });
    await expect(page.locator('#dk-page-promotion')).toContainText(REAL_PROMOTION, {
      timeout: 30_000,
    });

    expect(problems, `console errors on the editor: ${problems.join(' | ')}`).toHaveLength(0);
  });

  test('a linked promotion strikes the LIST price and leads with the offer', async ({ page }) => {
    test.skip(!fixture, 'the fixture catalogue could not be built in this company');
    await setPromotion(page, fixture!.promotionId);

    await openEditor(page);

    // Reached by clicking "View live" rather than by typing the address: the
    // link is what a Designer actually uses, and a broken one is a real defect.
    //
    // The listener sits on the CONTEXT, not this page: the catalogue opens in a
    // new tab, and a page-level `waitForResponse` never sees the tab's own
    // requests - it waits out its timeout while the payload arrives next door.
    const payloads: Array<Promise<CataloguePayload>> = [];
    page.context().on('response', (response) => {
      if (response.url().includes('/api/v1/public/c/') && response.ok()) {
        payloads.push(response.json() as Promise<CataloguePayload>);
      }
    });

    const opened = page.waitForEvent('popup', { timeout: 30_000 });
    await tap(page.getByRole('link', { name: /view live/i }).first());
    const live = await opened;
    await expect
      .poll(() => payloads.length, { timeout: 40_000 })
      .toBeGreaterThan(0);
    const body = await payloads[0];

    // THE WIRE. Both figures, on the discounted product only.
    const tiles = body.collections[fixture!.collectionId] ?? [];
    const discounted = tiles.find((row) => row.productId === fixture!.offerProductId);
    const plain = tiles.find((row) => row.productId === fixture!.plainProductId);
    expect(discounted, 'the discounted product should be on the page').toBeTruthy();
    expect(discounted!.price).toBe(fixture!.listPriceText);
    expect(discounted!.offerPrice).toBe(fixture!.offerPriceText);
    // A price a viewer may not see is ABSENT rather than hidden, so "no offer"
    // has to be null on the wire, not an empty string.
    expect(plain!.offerPrice).toBeNull();

    // THE SCREEN. Which element carries the line is the whole assertion: with
    // the two swapped, both numbers are still here and still correct.
    const discountedTile = tile(live, fixture!.offerProductId);
    await expect(discountedTile).toBeVisible({ timeout: 40_000 });
    const listOn = discountedTile.locator('[data-dk-list-price]');
    const offerOn = discountedTile.locator('[data-dk-offer-price]');
    await expect(listOn).toHaveText(fixture!.listPriceText);
    await expect(offerOn).toHaveText(fixture!.offerPriceText);
    expect(await struckThrough(listOn), 'the LIST price carries the strikethrough').toBe(true);
    expect(await struckThrough(offerOn), 'the OFFER price must not be struck through').toBe(false);
    // And the offer is the prominent one, not the whisper.
    const weights = await Promise.all(
      [listOn, offerOn].map((node) =>
        node.evaluate((element) => Number(getComputedStyle(element as Element).fontWeight)),
      ),
    );
    expect(weights[1], 'the offer should be at least as heavy as the struck list price')
      .toBeGreaterThanOrEqual(weights[0]);

    await live.close();
  });

  test('a product the promotion misses shows ONE plain price', async ({ page }) => {
    test.skip(!fixture, 'the fixture catalogue could not be built in this company');
    await setPromotion(page, fixture!.promotionId);

    await page.goto(fixture!.publicPath, { waitUntil: 'commit' });
    const plainTile = tile(page, fixture!.plainProductId);
    await expect(plainTile).toBeVisible({ timeout: 40_000 });

    // No offer element at all - not an empty one, and not a hidden one. A tile
    // must not look discounted to itself, and it must not leave a gap where an
    // offer would have gone (ADR 0008 rule 5).
    await expect(plainTile.locator('[data-dk-offer-price]')).toHaveCount(0);
    const price = plainTile.locator('[data-dk-list-price]');
    await expect(price).toHaveCount(1);
    await expect(price).toHaveText(fixture!.plainPriceText);
    expect(await struckThrough(price), 'an undiscounted price is never struck through').toBe(false);

    // One row of money, one figure in it. Same on this tile as on any page with
    // no promotion linked at all.
    expect(await plainTile.locator('[data-dk-price-row] > span').count()).toBe(1);
  });

  test('unlinking the promotion returns every tile to a plain list price', async ({ page }) => {
    test.skip(!fixture, 'the fixture catalogue could not be built in this company');
    await setPromotion(page, fixture!.promotionId);
    await openEditor(page);

    // Cleared through the control's own affordance, which is what a Designer has.
    const cleared = page.waitForResponse(
      (response) => response.request().method() === 'PUT' && /\/promotion$/.test(response.url()),
      { timeout: 30_000 },
    );
    await page
      .locator('#dk-page-promotion [role="button"][aria-label="Clear selection"]')
      .dispatchEvent('pointerdown', { bubbles: true });
    const response = await cleared;
    expect(response.status()).toBe(200);
    // Null is a real answer, not a missing one.
    expect(JSON.parse(response.request().postData() ?? '{}')).toEqual({ promotionId: null });
    expect(await response.json()).toMatchObject({ promotionId: null, promotionLabel: null });
    await expect(page.locator('#dk-page-promotion')).toContainText('List prices only');

    // The published catalogue follows immediately: the promotion lives on the
    // PAGE, not in the document, so nothing has to be republished.
    await page.goto(fixture!.publicPath, { waitUntil: 'commit' });
    await expect(tile(page, fixture!.offerProductId)).toBeVisible({ timeout: 40_000 });
    await expect(page.locator('[data-dk-offer-price]')).toHaveCount(0);
    const price = tile(page, fixture!.offerProductId).locator('[data-dk-list-price]');
    await expect(price).toHaveText(fixture!.listPriceText);
    expect(await struckThrough(price)).toBe(false);
  });

  test('an expired, switched-off promotion prices nothing', async ({ page }) => {
    test.skip(!fixture, 'the fixture catalogue could not be built in this company');

    // The REAL flyer, read only. It holds this exact product at RM 599 against
    // the RM 1,260 list price - and it ended on 2026-05-31 and is switched off,
    // so an offer reaching a tile from it would be a live price quoted from a
    // dead promotion.
    const token = await apiToken(page.context().request);
    const promotions = await page.context().request.get(
      `${API_BASE}/api/v1/marketing/promotions/?query=${encodeURIComponent(REAL_PROMOTION)}&limit=10`,
      { headers: auth(token) },
    );
    expect(promotions.ok()).toBeTruthy();
    const rows = ((await promotions.json()) as { data?: Array<{ id: string; description: string }> }).data ?? [];
    const flyer = rows.find((row) => row.description === REAL_PROMOTION);
    test.skip(!flyer, 'the real A3 flyer promotion is not in this database');

    await setPromotion(page, flyer!.id);
    await page.goto(fixture!.publicPath, { waitUntil: 'commit' });

    await expect(tile(page, fixture!.offerProductId)).toBeVisible({ timeout: 40_000 });
    await expect(page.locator('[data-dk-offer-price]')).toHaveCount(0);
    const price = tile(page, fixture!.offerProductId).locator('[data-dk-list-price]');
    await expect(price).toHaveText(fixture!.listPriceText);
    expect(await struckThrough(price), 'an expired offer leaves no styling behind').toBe(false);

    await setPromotion(page, fixture!.promotionId);
  });

  /**
   * What this test does and does NOT prove.
   *
   * It proves the export round trip: the button queues a render for the page in
   * front of the user, the worker finishes it, and what comes back is a real
   * PDF. It does NOT read the figures INSIDE the file - nothing in this repo can
   * extract PDF text, and adding a PDF parser as a dependency to assert two
   * numbers is a poor trade. The reason that is acceptable: the PDF is printed
   * from the SAME `CatalogueRenderer` and the SAME `TilePrices` this suite has
   * already asserted against on the public page, from a payload resolved by the
   * same `resolve_prices`. If the price block were wrong in the PDF it would be
   * wrong on screen too, and the tests above would be red.
   */
  test('the PDF export renders the same document', async ({ page }) => {
    test.skip(!fixture, 'the fixture catalogue could not be built in this company');
    await setPromotion(page, fixture!.promotionId);
    await openEditor(page);

    const requested = page.waitForResponse(
      (response) => response.request().method() === 'POST' && /\/exports$/.test(response.url()),
      { timeout: 40_000 },
    );
    await tap(page.getByRole('button', { name: /export pdf/i }).first());
    const response = await requested;
    // 202: the file does not exist yet, and the caller watches My Downloads.
    expect(response.status()).toBe(202);
    const { downloadId } = (await response.json()) as { downloadId: string };
    expect(downloadId).toBeTruthy();

    // The render needs the RQ worker on `catalogue_render`. Without one this
    // stays `pending` forever, which is an environment gap rather than a defect -
    // so it says so rather than failing silently at the timeout.
    const token = await apiToken(page.context().request);
    const request = page.context().request;
    let status = 'pending';
    for (let attempt = 0; attempt < 90 && status !== 'ready'; attempt += 1) {
      const rows = await request.get(`${API_BASE}/api/v1/downloads`, { headers: auth(token) });
      if (rows.ok()) {
        const body = (await rows.json()) as { downloads?: Array<{ id: string; status: string; error?: string | null }> };
        const row = (body.downloads ?? []).find((candidate) => candidate.id === downloadId);
        status = row?.status ?? 'pending';
        if (status === 'failed') {
          throw new Error(`the render failed: ${row?.error ?? 'no reason recorded'}`);
        }
      }
      if (status !== 'ready') await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
    test.skip(
      status !== 'ready',
      'no worker is draining `catalogue_render`, so no PDF could be produced',
    );

    // A real PDF, not an error page with a .pdf name.
    const link = await request.get(`${API_BASE}/api/v1/downloads/${downloadId}/url`, {
      headers: auth(token),
    });
    expect(link.ok(), 'a finished render has a file behind it').toBeTruthy();
    const { url } = (await link.json()) as { url: string };
    const file = await request.get(url);
    expect(file.ok()).toBeTruthy();
    const bytes = await file.body();
    expect(bytes.subarray(0, 4).toString('latin1')).toBe('%PDF');
    expect(bytes.byteLength).toBeGreaterThan(5_000);
  });
});

/**
 * Teardown for the WHOLE file, not one describe.
 *
 * The responsive describes below reuse the same fixture, so deleting it after
 * the first describe would leave them asserting against a page that no longer
 * exists. A file-level `afterAll` runs once, after everything.
 */
test.afterAll(async ({ browser }, testInfo) => {
  if (!EMAIL || !PASSWORD) return;
  if (!created.pageId && !created.promotionId && !homeCompanyId) return;

  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const page = await context.newPage();
  try {
    await login(page);
    await switchCompanyTo(page, COMPANY);
    const token = await apiToken(context.request);

    // Reverse order, and only rows this run created. The page's promotion link
    // is cleared first so nothing is left pointing at a promotion about to go.
    if (created.pageId) {
      await context.request.put(`${KIT}/pages/${created.pageId}/promotion`, {
        headers: auth(token),
        data: { promotionId: null },
      });
    }
    if (created.collectionId) {
      const gone = await context.request.delete(`${KIT}/collections/${created.collectionId}`, {
        headers: auth(token),
      });
      if (!gone.ok()) console.warn(`[cleanup] collection survived: ${gone.status()}`);
    }
    if (created.pageId) {
      const gone = await context.request.delete(`${KIT}/pages/${created.pageId}`, {
        headers: auth(token),
      });
      if (!gone.ok()) console.warn(`[cleanup] page survived: ${gone.status()}`);
    }
    if (created.promotionId) {
      const gone = await context.request.delete(`${MARKETING}/${created.promotionId}`, {
        headers: auth(token),
      });
      if (!gone.ok()) console.warn(`[cleanup] promotion survived: ${gone.status()}`);
    }

    // `last_active_company_id` is user state, so a run that moved it puts it
    // back rather than leaving the next person in a company they did not pick.
    // By id and through the same endpoint the switcher posts to: a label lookup
    // here can silently match nothing, and the miss is only discovered by the
    // NEXT run, which then records the wrong company as home.
    if (homeCompanyId) {
      const restored = await context.request.post(
        `${API_BASE}/api/v1/system/companies/switch`,
        { headers: auth(token), data: { company_id: homeCompanyId } },
      );
      if (!restored.ok()) {
        console.warn(`[cleanup] active company NOT restored to ${homeCompanyId}: ${restored.status()}`);
      }
      // Verified, not assumed. This is the one piece of the teardown that
      // touches a row the suite did not create.
      const context_ = await context.request.get(
        `${API_BASE}/api/v1/system/companies/my-context`,
        { headers: auth(token) },
      );
      if (context_.ok()) {
        const now = ((await context_.json()) as { last_active_company_id?: string | null })
          .last_active_company_id;
        if (now !== homeCompanyId) {
          console.warn(`[cleanup] active company is ${now}, expected ${homeCompanyId}`);
        }
      }
    }
  } catch (error) {
    console.warn(`[cleanup] skipped: ${String(error).slice(0, 300)}`);
  } finally {
    await context.close();
  }
});

// A separate describe with test.use: setViewportSize mid-test wedges against the
// protected layout's never-resolving fetch, which is why the other Dealer Kit
// specs do it this way too.
for (const width of [375, 1280]) {
  test.describe(`Dealer Kit offer pricing at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test('a two-figure price block stays inside its tile', async ({ page }) => {
      test.skip(!EMAIL || !PASSWORD, 'credentials required');
      const problems = watchConsole(page);

      await login(page);
      // Recorded here too, so running ONLY the responsive tests still restores
      // the account to the company it was found in.
      await rememberHomeCompany(page);
      await switchCompanyTo(page, COMPANY);
      const built = await buildFixture(page);
      test.skip(!built, 'the fixture catalogue could not be built in this company');
      await setPromotion(page, built!.promotionId);

      await page.goto(built!.publicPath, { waitUntil: 'commit' });
      const discounted = tile(page, built!.offerProductId);
      await expect(discounted).toBeVisible({ timeout: 40_000 });

      // Money WRAPS rather than clips. A truncated price shows a number that is
      // not the price, which is worse than a second line.
      const box = (await discounted.boundingBox())!;
      for (const selector of ['[data-dk-list-price]', '[data-dk-offer-price]']) {
        const figure = (await discounted.locator(selector).boundingBox())!;
        expect(figure, `${selector} should be laid out`).not.toBeNull();
        expect(figure.x).toBeGreaterThanOrEqual(box.x - 1);
        expect(figure.x + figure.width).toBeLessThanOrEqual(box.x + box.width + 1);
      }
      // Nothing overflowing its own box: `truncate` on a price would show one.
      const clipped = await discounted
        .locator('[data-dk-list-price], [data-dk-offer-price]')
        .evaluateAll((nodes) =>
          nodes.some((node) => (node as HTMLElement).scrollWidth > (node as HTMLElement).clientWidth + 1),
        );
      expect(clipped, 'a price is never clipped').toBe(false);

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
      expect(problems, `console errors on the catalogue: ${problems.join(' | ')}`).toHaveLength(0);
    });
  });
}
