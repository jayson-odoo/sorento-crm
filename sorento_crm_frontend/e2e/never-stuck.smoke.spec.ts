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
 * `never-stuck/known-failures.json` with their audit row id (`route: "*"` covers every
 * route for that persona). They still run and are reported, but do not fail the night;
 * the summary names the ones that passed so their entries get deleted.
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

/**
 * Visible loading placeholders, described (`skeleton in "Packing list"`) so a failure says
 * where to look. A spinner inside a button is a pending action, not a stuck page.
 */
async function visibleLoaders(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    document.querySelectorAll('[data-loading], .animate-spin').forEach((el) => {
      if (el.closest('button')) return;
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) return;
      if (!(el as Element & { checkVisibility?: () => boolean }).checkVisibility?.()) return;
      const kind = el.getAttribute('data-slot') ?? (el.hasAttribute('data-loading') ? 'loader' : 'spinner');
      const region = el.closest('section, [role=tabpanel], [role=dialog], main, header, aside');
      const label = (region?.querySelector('h1, h2, h3, [role=tab][aria-selected=true]')?.textContent ?? '')
        .trim()
        .slice(0, 40);
      found.push(label ? `${kind} in "${label}"` : `${kind} in <${region?.tagName.toLowerCase() ?? 'body'}>`);
    });
    return found;
  });
}

/** Settled = no loading placeholder on two reads 500 ms apart. Returns what is still loading. */
async function waitSettled(page: Page, budgetMs: number): Promise<string[]> {
  const deadline = Date.now() + budgetMs;
  let clearReads = 0;
  let last: string[] = [];
  while (Date.now() < deadline) {
    last = await visibleLoaders(page).catch(() => ['page not readable']);
    clearReads = last.length === 0 ? clearReads + 1 : 0;
    if (clearReads >= 2) return [];
    await page.waitForTimeout(500);
  }
  return last;
}

const onSignIn = (url: string) => /\/signin(?:[/?#]|$)/.test(new URL(url).pathname + new URL(url).search);

for (const persona of PERSONAS) {
  test.describe(`never-stuck ${persona}`, () => {
    test.describe.configure({ mode: 'parallel' });
    test.skip(!seed, 'Set NEVER_STUCK_SEED to the manifest scripts/seed_never_stuck_smoke.py wrote');
    test.use({ storageState: seed ? statePath(persona) : undefined });

    for (const route of routes) {
      test(`${persona} ${route}`, async ({ page }) => {
        const known = KNOWN.find(
          (k) => k.persona === persona && (k.route === route || k.route === '*'),
        );

        const url = concreteUrl(route, seed!);
        const refused: string[] = [];
        page.on('response', (res) => {
          if (res.status() === 403 && res.url().includes('/api/v1/')) {
            refused.push(new URL(res.url()).pathname);
          }
        });

        const problems: string[] = [];
        const started = Date.now();
        // `load`, not `commit`: before the document has parsed there is nothing on screen,
        // and "no loader visible" on a blank page would read as settled.
        const loaded = await page
          .goto(url, { waitUntil: 'load', timeout: SETTLE_MS })
          .then(() => true)
          .catch(() => false);

        if (!loaded && !onSignIn(page.url())) {
          problems.push(`document did not finish loading in ${SETTLE_MS / 1000}s`);
        } else if (persona === 'expired') {
          const landed = await page
            .waitForURL((u) => onSignIn(u.toString()), {
              // Never 0: Playwright reads a 0 timeout as "no timeout".
              timeout: Math.max(1, SIGNIN_MS - (Date.now() - started)),
            })
            .then(() => true)
            .catch(() => false);
          if (!landed) problems.push(`expired session not on /signin after ${SIGNIN_MS / 1000}s (at ${page.url()})`);
        } else {
          const stuck = await waitSettled(page, SETTLE_MS - (Date.now() - started));
          if (stuck.length) {
            const what = [...new Set(stuck)].slice(0, 3).join(', ');
            problems.push(`still loading after ${SETTLE_MS / 1000}s at ${new URL(page.url()).pathname}: ${what}`);
          }
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

        if (known) {
          // A ranked audit row whose fix lane is open: report, do not fail. Not `test.fail()`:
          // several of these (the expired-session redirect) are timing-bound and flap, and a
          // ratchet that fails the night a flaky row happens to pass is noise, not signal.
          // The summary lists the ones that passed so their entries get deleted.
          test.info().annotations.push({
            type: problems.length ? 'known-failure' : 'known-passed',
            description: `${known.audit}: ${problems.join('; ') || known.reason}`,
          });
          return;
        }
        expect(problems, `${persona} ${url}`).toEqual([]);
      });
    }
  });
}
