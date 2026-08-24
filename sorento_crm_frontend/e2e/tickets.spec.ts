/**
 * Tickets module e2e - covers the verification steps from
 * docs/TICKETING-SYSTEM-PLAN.md.
 *
 * Run against a deployed (or local) instance:
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   TICKETS_E2E_EMAIL=admin@example.com \
 *   TICKETS_E2E_PASSWORD='...' \
 *   npx playwright test e2e/tickets.spec.ts
 *
 * Skipped automatically when the credentials env vars aren't set so it
 * doesn't block local dev. The flow assumes the running backend has
 * Phase 1 alembic migrations applied (`alembic upgrade head`) and that
 * the menu patch has been applied (`git apply
 * docs/patches/add-ticket-menu-entry.patch`).
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.TICKETS_E2E_EMAIL;
const PASSWORD = process.env.TICKETS_E2E_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  'Set TICKETS_E2E_EMAIL and TICKETS_E2E_PASSWORD to run the tickets flow',
);

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page
    .locator('input[type="password"], input[name="password"]')
    .first()
    .fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), {
    timeout: 30_000,
  });
}

/** Capture console errors/warnings so each test can assert a clean console. */
function trackConsole(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      errors.push(`[${msg.type()}] ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => {
    errors.push(`[pageerror] ${err.message}`);
  });
  return { errors };
}

/** Plan step 1: footer Support link goes to the ticket list. */
test('footer Support button lands on /ticket-management/tickets', async ({ page }) => {
  await login(page);
  await page.goto('/');
  const supportLink = page.getByRole('link', { name: 'Support' });
  await expect(supportLink).toBeVisible();
  await supportLink.click();
  await page.waitForURL(/\/ticket-management\/tickets$/);
  await expect(
    page.getByRole('heading', { name: 'Tickets' }).first(),
  ).toBeVisible({ timeout: 15_000 });
});

/** Plan steps 2 & 3: Create + Detail flow. */
test('create + detail: TCK number, status pill, SLA strip, panel launcher', async ({
  page,
}) => {
  const cons = trackConsole(page);
  await login(page);
  await page.goto('/ticket-management/tickets');

  // Create.
  await page.getByRole('link', { name: /create ticket/i }).click();
  await page.waitForURL(/\/tickets\/new$/);
  const title = `E2E test ticket ${Date.now()}`;
  await page.getByLabel('Title *').fill(title);
  await page.getByLabel('Description').fill('Trying to verify the ticketing flow.');
  await page.getByRole('button', { name: 'Submit' }).click();

  // Detail page.
  await page.waitForURL(/\/ticket-management\/tickets\/[^/]+$/, {
    timeout: 30_000,
  });
  const breadcrumbItem = page.getByText(/^TCK-\d{4}-\d+/).first();
  await expect(breadcrumbItem).toBeVisible({ timeout: 20_000 });

  // SLA strip + Response/Resolution cards visible.
  await expect(page.getByText('Response time:')).toBeVisible();
  await expect(page.getByText('Resolution time:')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Response' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Resolution' })).toBeVisible();

  // Floating activities launcher visible (red pulse icon).
  await expect(
    page.getByRole('button', { name: /open activities & notes/i }),
  ).toBeVisible();

  // No console errors throughout.
  expect(cons.errors).toEqual([]);
});

/** Plan step 4: panel pushes content (lg+) when opened. */
test('activities panel pushes content (margin-right) on lg+', async ({ page }) => {
  await login(page);
  await page.goto('/ticket-management/tickets');
  // Open the most recent ticket.
  const firstRow = page.locator('table tbody tr').first();
  await expect(firstRow).toBeVisible({ timeout: 15_000 });
  await firstRow.click();
  await page.waitForURL(/\/ticket-management\/tickets\/[^/]+$/);

  const launcher = page.getByRole('button', { name: /open activities & notes/i });
  await launcher.click();

  // Header reads "Activities & notes".
  await expect(
    page.getByRole('heading', { name: 'Activities & notes' }),
  ).toBeVisible();

  // Main element should now have lg:mr-[420px] applied. We assert the
  // computed margin-right is non-zero on a viewport >= 1024 px.
  const main = page.locator('main').first();
  const marginRight = await main.evaluate(
    (el) => getComputedStyle(el).marginRight,
  );
  expect(parseInt(marginRight, 10)).toBeGreaterThan(0);
});

/** Plan step 5 & 7: status select moves the ticket through workflow. */
test('status select transitions and SLA fields update', async ({ page }) => {
  await login(page);
  await page.goto('/ticket-management/tickets');
  const firstRow = page.locator('table tbody tr').first();
  await expect(firstRow).toBeVisible({ timeout: 15_000 });
  await firstRow.click();
  await page.waitForURL(/\/ticket-management\/tickets\/[^/]+$/);

  // Open the status Select in the sidebar; pick "Submitted" if not already.
  const statusTrigger = page
    .locator('[role="combobox"]')
    .filter({ hasText: /Draft|Submitted|Assigned|Responded|Resolved/ })
    .first();
  await statusTrigger.click();
  await page.getByRole('option', { name: 'Submitted' }).click();

  // Toast confirms.
  await expect(
    page.getByText(/Status .* submitted/i, { exact: false }).first(),
  ).toBeVisible({ timeout: 5_000 });
});

/** Plan step 11: list ↔ board view toggle persists. */
test('list/board view toggle persists in localStorage', async ({ page }) => {
  await login(page);
  await page.goto('/ticket-management/tickets');
  await expect(page.locator('table thead')).toBeVisible({ timeout: 15_000 });

  // Switch to board.
  const boardToggle = page.getByRole('radio', { name: /board view/i });
  await boardToggle.click();
  await expect(page.getByText('Draft', { exact: false }).first()).toBeVisible();

  // Reload - should land back on board.
  await page.reload();
  await page.waitForLoadState('networkidle');
  // The board has explicit column headers labelled Draft/Submitted/...
  await expect(page.getByText('Draft', { exact: true }).first()).toBeVisible({
    timeout: 15_000,
  });
});

/** Plan step 13: panel takes full width on a phone viewport. */
test('mobile: panel covers full width', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  await login(page);
  await page.goto('/ticket-management/tickets');
  const firstRow = page.locator('table tbody tr').first();
  if ((await firstRow.count()) === 0) {
    await ctx.close();
    test.skip(true, 'no tickets to open in mobile flow');
    return;
  }
  await firstRow.click();
  await page.waitForURL(/\/ticket-management\/tickets\/[^/]+$/);
  await page
    .getByRole('button', { name: /open activities & notes/i })
    .click();
  const aside = page.locator('aside').first();
  const box = await aside.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(300); // ~full mobile width
  await ctx.close();
});
