/**
 * Company-aware assignment routing e2e - the company switcher must drive what the
 * Access Agent detail page shows.
 *
 * Pins the bug this was written for: `useAgentTeams` was keyed on the agent id
 * alone, and `invalidateQueries()` only refetches MOUNTED queries. An agent page
 * that was not open during a company switch kept its cached payload and served it
 * on the next visit, so one company's team sets rendered under the other
 * company's label. A browser is the only place that reproduces: the API returns
 * the right rows, the cache serves the wrong ones.
 *
 * Acceptance criteria exercised:
 *   D8      the Access Agents LIST is identical under every company (agents are
 *           not company-scoped; one router serves both brands)
 *   AC-H2   opening an agent shows only the ACTIVE company's team sets
 *   AC-H2b  an agent with none in this company still renders, with an empty
 *           state and an add CTA - never hidden
 *   AC-F1   teams are company-scoped, so the Teams list follows the switcher
 *
 * Run against a running stack (FE prod build + BE; worker NOT required):
 *
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   REQUEST_BATCH_E2E_EMAIL=... REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/company-scoped-team-sets.spec.ts
 *
 * Assumes the two live companies (Sorento incumbent, Mocha) and that Mocha has no
 * teams configured yet - which is the shipped state: the migration backfills
 * everything to Sorento and creates no Mocha rows on purpose.
 *
 * KNOWN FLAKY, and worth knowing what it does and does not buy you:
 *   - It is timing-flaky. Observed 13s for the whole file on one run and a
 *     240s timeout on a single test the next, same code and stack. The sidebar
 *     expand loop and the two JWT re-mints per test are the slow parts.
 *   - It does NOT catch a backend company-scope regression. Deleting the company
 *     predicate from the listing query and re-running left it green, because the
 *     ORM scope filter still isolates the rows. Treat this as UX cover (the label,
 *     the empty state, the list staying company-agnostic), and pin backend
 *     isolation in pytest instead.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the company-scope flow');

// Each test logs in, switches company twice and walks the sidebar twice. Every
// switch re-mints the JWT and invalidates every query, so this legitimately runs
// past the 90s default.
test.setTimeout(240_000);

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

/** Switch the active company via the topbar switcher and wait for the refetch. */
async function switchCompany(page: Page, name: RegExp) {
  const switcher = page
    .getByRole('button', { name: /(sorento\s+SRT|mocha\s+MOCHA)/i })
    .first();
  await expect(switcher).toBeVisible({ timeout: 20_000 });
  await switcher.click();
  await page.getByRole('menuitem', { name }).click();
  // The provider re-mints the JWT and invalidates every query before the toast.
  await expect(switcher).toHaveText(name, { timeout: 30_000 });
}

/**
 * Assert a sidebar leaf really renders under its group (catches a missing entry /
 * wrong moduleKey / permission gating), then navigate via its resolved href.
 *
 * Clicking the <Link> directly hangs: the protected layout fires an ingest fetch
 * that holds the page in a pre-load state and intercepts Playwright's click
 * auto-wait. Established repo workaround, same as e2e/certificates.spec.ts.
 */
async function openSidebarLeaf(page: Page, group: RegExp, leaf: RegExp, expectedHref: string) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const groupButton = page.getByRole('button', { name: group }).first();
  await expect(groupButton).toBeVisible({ timeout: 60_000 });
  const link = page.getByRole('link', { name: leaf }).first();
  // A cold prod page behind auth needs longer than the 2.4s the certificates spec
  // allows, and an even number of clicks would toggle the group shut again - so
  // re-check between every click rather than clicking blind.
  for (let i = 0; i < 20 && (await link.count()) === 0; i++) {
    await groupButton.click({ timeout: 5_000 }).catch(() => {});
    await page.waitForTimeout(1_000);
  }
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  if (!href) throw new Error(`Sidebar link ${leaf} has no href`);
  expect(href).toBe(expectedHref);
  await page.goto(href, { waitUntil: 'commit' });
}

const openAccessAgents = (page: Page) =>
  openSidebarLeaf(page, /^user management$/i, /^ai agents$/i, '/user-management/access-agents');

const openTeams = (page: Page) =>
  openSidebarLeaf(page, /^user management$/i, /^teams$/i, '/user-management/teams');

test('company switcher drives the agent detail team sets', async ({ page }) => {
  await login(page);

  // --- Sorento: the agent has its ladder -------------------------------------
  await switchCompany(page, /sorento/i);
  await openAccessAgents(page);

  const agentCell = page.getByRole('cell', { name: 'incoming_stock_enquiries' }).first();
  await expect(agentCell).toBeVisible({ timeout: 30_000 });
  await agentCell.click();
  await page.waitForURL(/\/user-management\/access-agents\/[0-9a-f-]{36}/, { timeout: 30_000 });

  await expect(page.getByText(/showing sorento/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('purchasing', { exact: true }).first()).toBeVisible({
    timeout: 30_000,
  });

  // --- Mocha: same agent, no ladder, and NOT the Sorento one -----------------
  // The regression: this page is mounted, but the cache entry it had been served
  // was keyed without the company. Keying on the company makes the stale payload
  // unreachable rather than merely refetched.
  await switchCompany(page, /mocha/i);

  await expect(page.getByText(/showing mocha/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/no team assignments for mocha yet/i)).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole('button', { name: /edit access agent/i })).toBeVisible();
  // Sorento's team set must be gone, not merely re-fetched.
  await expect(page.getByText('purchasing', { exact: true })).toHaveCount(0);
});

test('access agents list is the same under every company', async ({ page }) => {
  // D8: agents are NOT company-scoped - one router serves both brands through two
  // ladders. Split from the test above so neither walks the sidebar twice, which
  // is what made the combined test flaky.
  await login(page);

  await switchCompany(page, /sorento/i);
  await openAccessAgents(page);
  await expect(
    page.getByRole('cell', { name: 'incoming_stock_enquiries' }).first(),
  ).toBeVisible({ timeout: 30_000 });

  await switchCompany(page, /mocha/i);
  await expect(
    page.getByRole('cell', { name: 'incoming_stock_enquiries' }).first(),
  ).toBeVisible({ timeout: 30_000 });
});

test('teams list follows the active company', async ({ page }) => {
  await login(page);

  await switchCompany(page, /sorento/i);
  await openTeams(page);

  await expect(page.getByText(/\d+ teams/i)).toBeVisible({ timeout: 30_000 });

  await switchCompany(page, /mocha/i);
  await expect(page.getByText(/no teams yet/i)).toBeVisible({ timeout: 30_000 });
});
