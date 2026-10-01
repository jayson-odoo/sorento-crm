/**
 * Never-stuck smoke (guard G4): open every app route as an admin, as a restricted user
 * and with an expired session, and fail on any state that is not final and honest.
 * Standard: `documentation/reference/NEVER-STUCK-UI.md`. Owner-approved exception to the
 * no-new-Playwright-specs order (1 Oct 2026): this is the one spec it covers.
 *
 * A route fails when:
 * - admin / restricted: anything is still loading 15 s after navigation (a visible
 *   `[data-loading]` placeholder, or a spinner outside a button);
 * - admin / restricted: the page bounced to sign-in although the session is alive;
 * - restricted: an API call answered 403 and the page shows an empty / not-found state
 *   instead of `AccessDenied` (a refusal rendered as "nothing here");
 * - any persona: raw backend permission text (`Permission required: x.y.z`) is on screen;
 * - expired: the page is not on `/signin` within 5 s.
 *
 * Rows the audit already ranked and whose fix lane has not merged are listed in
 * `never-stuck/known-failures.json` with their audit row id. They run as expected
 * failures, so the night one starts passing it fails as "fixed, remove the entry".
 *
 * Run (needs the stack up and seeded; recipe in `never-stuck/README.md`):
 *   NEVER_STUCK_SEED=e2e/.never-stuck/seed.json \
 *     npx playwright test -c playwright.never-stuck.config.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import {
  PERSONAS,
  type Persona,
  concreteUrl,
  loadSeed,
  routeTemplates,
  statePath,
} from './never-stuck/routes';

const SETTLE_MS = 15_000;
const SIGNIN_MS = 5_000;

const RAW_PERMISSION_TEXT =
  /Permission required:|One of these permissions required|Module not enabled:/;
/** Copy a page shows when it decided there is nothing: list empties and not-found states. */
const EMPTY_STATE_TEXT =
  /No data available|No [\w\s-]{1,40} (?:yet|found)\b|nothing (?:here|to show)|not found|doesn't exist|does not exist/i;

interface KnownFailure {
  persona: Persona;
  route: string;
  audit: string;
  reason: string;
}
const KNOWN: KnownFailure[] = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'never-stuck', 'known-failures.json'), 'utf8'),
).failures;

const seed = loadSeed();
const routes = routeTemplates();

/** Visible loading placeholders. A spinner inside a button is a pending action, not a page. */
async function loadingCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    const nodes = document.querySelectorAll('[data-loading], .animate-spin');
    let n = 0;
    nodes.forEach((el) => {
      if (el.closest('button')) return;
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) return;
      if (!(el as Element & { checkVisibility?: () => boolean }).checkVisibility?.()) return;
      n += 1;
    });
    return n;
  });
}

/** Settled = no loading placeholder on two reads 500 ms apart, within the budget. */
async function waitSettled(page: Page, budgetMs: number): Promise<boolean> {
  const deadline = Date.now() + budgetMs;
  let clearReads = 0;
  while (Date.now() < deadline) {
    const n = await loadingCount(page).catch(() => 1);
    clearReads = n === 0 ? clearReads + 1 : 0;
    if (clearReads >= 2) return true;
    await page.waitForTimeout(500);
  }
  return false;
}

const onSignIn = (url: string) => /\/signin(?:[/?#]|$)/.test(new URL(url).pathname + new URL(url).search);

for (const persona of PERSONAS) {
  test.describe(`never-stuck ${persona}`, () => {
    test.describe.configure({ mode: 'parallel' });
    test.skip(!seed, 'Set NEVER_STUCK_SEED to the manifest scripts/seed_never_stuck_smoke.py wrote');
    test.use({ storageState: seed ? statePath(persona) : undefined });

    for (const route of routes) {
      test(`${persona} ${route}`, async ({ page }) => {
        const known = KNOWN.find((k) => k.persona === persona && k.route === route);
        if (known) {
          test.info().annotations.push({ type: 'audit', description: `${known.audit}: ${known.reason}` });
          test.fail(true, `known failure, audit ${known.audit}`);
        }

        const url = concreteUrl(route, seed!);
        const refused: string[] = [];
        page.on('response', (res) => {
          if (res.status() === 403 && res.url().includes('/api/v1/')) {
            refused.push(new URL(res.url()).pathname);
          }
        });

        const problems: string[] = [];
        await page.goto(url, { waitUntil: 'commit', timeout: SETTLE_MS });

        if (persona === 'expired') {
          const landed = await page
            .waitForURL((u) => onSignIn(u.toString()), { timeout: SIGNIN_MS })
            .then(() => true)
            .catch(() => false);
          if (!landed) problems.push(`expired session not on /signin after ${SIGNIN_MS / 1000}s (at ${page.url()})`);
        } else {
          const settled = await waitSettled(page, SETTLE_MS);
          if (!settled) problems.push(`still loading after ${SETTLE_MS / 1000}s`);
          if (onSignIn(page.url())) problems.push('live session bounced to /signin');
        }

        const text = await page.locator('body').innerText({ timeout: 2_000 }).catch(() => '');
        const raw = text.match(RAW_PERMISSION_TEXT);
        if (raw) problems.push(`raw permission text on screen: "${raw[0]}..."`);

        if (persona === 'restricted' && refused.length > 0) {
          const denied = await page.locator('[data-access-denied]').count();
          const empty = text.match(EMPTY_STATE_TEXT);
          if (denied === 0 && empty) {
            problems.push(
              `refusal rendered as empty ("${empty[0]}") after 403 on ${[...new Set(refused)].join(', ')}`,
            );
          }
        }

        expect(problems, `${persona} ${url}`).toEqual([]);
      });
    }
  });
}
