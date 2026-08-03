import { expect, type APIRequestContext, type Browser } from '@playwright/test';

/**
 * Delete the rows a Dealer Kit E2E run left behind.
 *
 * The local database is a COPY OF PRODUCTION DATA, so a test suite that creates
 * rows and walks away is not harmless: after a few runs the real lists are
 * mostly test litter and nobody can tell the two apart. Every row this suite
 * creates is named with the reserved `zzt-` prefix, and this deletes exactly
 * those - never by pattern against a column that real data also uses, never an
 * unscoped DELETE.
 *
 * It runs against the API rather than the UI because a teardown that has to
 * click through four list pages is a teardown that silently stops working.
 */

const MARKER = 'zzt-';
const API_BASE = process.env.DEALER_KIT_E2E_API_BASE ?? 'http://localhost:8020';

/** Every Dealer Kit resource the suite creates, as (list path, name field). */
const RESOURCES = [
  { path: '/api/v1/dealer-kit/pages', field: 'name' },
  { path: '/api/v1/dealer-kit/collections', field: 'name' },
  { path: '/api/v1/dealer-kit/bundles', field: 'name' },
  { path: '/api/v1/dealer-kit/tile-templates', field: 'name' },
] as const;

/** Read the backend session token out of an authenticated browser context. */
async function apiToken(request: APIRequestContext): Promise<string> {
  const response = await request.get('/api/auth/token');
  expect(response.ok(), 'teardown needs a live session to clean up after itself').toBeTruthy();
  const body = (await response.json()) as { token?: string };
  expect(body.token, 'session token missing').toBeTruthy();
  return body.token!;
}

/**
 * Purge marker rows using an already-authenticated context.
 *
 * Failures are reported, not thrown: a teardown that fails the whole run
 * because one row was already gone teaches people to skip teardown.
 */
export async function purgeDealerKitTestRows(request: APIRequestContext): Promise<number> {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  let removed = 0;

  for (const resource of RESOURCES) {
    const listed = await request.get(`${API_BASE}${resource.path}`, { headers });
    if (!listed.ok()) {
      console.warn(`[cleanup] could not list ${resource.path}: ${listed.status()}`);
      continue;
    }

    const rows = (await listed.json()) as Array<Record<string, unknown>>;
    for (const row of Array.isArray(rows) ? rows : []) {
      const name = String(row[resource.field] ?? '');
      const id = String(row.id ?? '');
      if (!name.startsWith(MARKER) || !id) continue;

      const deleted = await request.delete(`${API_BASE}${resource.path}/${id}`, { headers });
      if (deleted.ok()) removed += 1;
      else console.warn(`[cleanup] ${name} survived: ${deleted.status()}`);
    }
  }

  return removed;
}

/**
 * Log in with a throwaway context and purge.
 *
 * `afterAll` has no page fixture, and reusing a worker's page risks tearing down
 * against a context a failing test already navigated away from.
 */
export async function purgeWithFreshLogin(browser: Browser, baseURL?: string): Promise<void> {
  const email = process.env.REQUEST_BATCH_E2E_EMAIL;
  const password = process.env.REQUEST_BATCH_E2E_PASSWORD;
  if (!email || !password) return;

  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  try {
    await page.goto('/');
    await page.locator('input[type="email"], input[name="email"]').first().fill(email);
    await page.locator('input[type="password"], input[name="password"]').first().fill(password);
    await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
    await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });

    const removed = await purgeDealerKitTestRows(context.request);
    console.log(`[cleanup] removed ${removed} Dealer Kit ${MARKER} rows`);
  } catch (error) {
    console.warn(`[cleanup] skipped: ${String(error).slice(0, 200)}`);
  } finally {
    await context.close();
  }
}

/**
 * The signed background URLs a page currently binds, read BEFORE it is deleted.
 *
 * There is no assets endpoint, and there should not be one just so a test can
 * tidy up. The editor payload already resolves `{assetId: signedUrl}` for the
 * document it is about to open, and that is enough: a URL that still answers
 * 200 after the run's pages and readings are deleted is a storage object nobody
 * can reach any more, which is exactly the leak that put 1,356 orphans in the
 * bucket.
 */
export async function boundBackgroundUrls(
  request: APIRequestContext,
  token: string,
  pageIds: string[],
): Promise<string[]> {
  const urls: string[] = [];
  for (const id of new Set(pageIds)) {
    const response = await request.get(`${API_BASE}/api/v1/dealer-kit/pages/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok()) continue;
    const body = (await response.json()) as { assets?: Record<string, string> };
    urls.push(...Object.values(body.assets ?? {}));
  }
  return urls;
}

/**
 * Of those URLs, the ones whose bytes are still there.
 *
 * Empty is the only acceptable answer once the run's rows are gone. The signed
 * link stays valid for an hour, so what this fetches is the OBJECT and not the
 * signature: a 200 means the row was deleted and the bytes were not.
 */
export async function stillStoredUrls(
  request: APIRequestContext,
  urls: string[],
): Promise<string[]> {
  const leaked: string[] = [];
  for (const url of new Set(urls)) {
    try {
      const response = await request.get(url);
      if (response.ok()) leaked.push(url.split('?')[0]);
    } catch {
      // Unreachable is not "still stored". A network failure here must not be
      // reported as a leak, or the suite fails for the wrong reason.
    }
  }
  return leaked;
}

/**
 * Delete selections by id.
 *
 * Selections cannot be found by the `zzt-` name prefix - the designer creates
 * them unnamed, because a user who has not named their design has not named it.
 * So the spec records the ids it created and hands them back here. Deleting
 * exactly what a run made is stricter than a prefix match anyway.
 */
export async function purgeSelections(
  browser: Browser,
  selectionIds: string[],
  baseURL?: string,
): Promise<void> {
  const email = process.env.REQUEST_BATCH_E2E_EMAIL;
  const password = process.env.REQUEST_BATCH_E2E_PASSWORD;
  if (!email || !password || selectionIds.length === 0) return;

  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  try {
    await page.goto('/');
    await page.locator('input[type="email"], input[name="email"]').first().fill(email);
    await page.locator('input[type="password"], input[name="password"]').first().fill(password);
    await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
    await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });

    const token = await apiToken(context.request);
    let removed = 0;
    for (const id of new Set(selectionIds)) {
      const response = await context.request.delete(
        `${API_BASE}/api/v1/dealer-kit/selections/${id}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (response.ok()) removed += 1;
    }
    console.log(`[cleanup] removed ${removed} selections`);
  } catch (error) {
    console.warn(`[cleanup] selections skipped: ${String(error).slice(0, 200)}`);
  } finally {
    await context.close();
  }
}
