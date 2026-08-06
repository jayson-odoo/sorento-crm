/**
 * Certificate register e2e - FE -> BE -> DB round-trip against the real
 * `/api/v1/master-data/certificates` API.
 *
 * Covers: sidebar (Product Management -> Certificates) -> list -> create modal
 * -> find the new row -> detail page -> revision timeline renders -> delete
 * behind the confirmation dialog -> row gone.
 *
 * Acceptance criteria exercised:
 *   FE-3  the list opens validity-scoped (`validity_state=expiring_soon,expired`)
 *   FE-5  the detail page renders EVERY section, each with its empty state
 *   FE-6  revision history renders as the delivery-tracking timeline
 *   FE-8  create is a modal; delete is AlertDialog-confirmed, never confirm()
 *   NAV   the leaf renders in the sidebar under Product Management
 *
 * Run against a running stack (FE + BE with the `product` module enabled for the
 * tenant; worker NOT required):
 *
 *   PORTAL_E2E_BASE_URL=http://localhost:3000 \
 *   REQUEST_BATCH_E2E_EMAIL=admin@example.com \
 *   REQUEST_BATCH_E2E_PASSWORD='...' \
 *   npx playwright test e2e/certificates.spec.ts
 *
 * Credentials live in the frontend .env.local as REQUEST_BATCH_E2E_* (reused
 * across the e2e specs). Skips automatically when they aren't set so local dev
 * isn't blocked. Navigation ALWAYS goes through the sidebar (never a deep URL)
 * so a broken menu gate (moduleKey / permission) fails the test.
 *
 * The certificate is created with an expiry in the PAST so it lands inside the
 * validity-scoped default view - proving FE-3 rather than working around it -
 * and its number is timestamped so a re-run never hits the SCH-2 409 on the
 * normalized identity.
 */
import { test, expect, Page } from '@playwright/test';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the certificate flow');

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

/**
 * Confirm the Product Management sidebar group + the Certificates leaf render
 * (catches a missing entry / wrong moduleKey / permission gating), then navigate
 * via the leaf's resolved href. Clicking the <Link> directly hangs: the
 * protected layout fires a localhost:7242 ingest fetch that holds the page in a
 * pre-load state and intercepts Playwright's click auto-wait (established repo
 * workaround, same as e2e/scm-policies.spec.ts).
 */
async function openCertificatesLeaf(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: /product management/i }).first();
  await expect(group).toBeVisible({ timeout: 20_000 });
  const link = page.getByRole('link', { name: /^Certificates$/ }).first();
  for (let i = 0; i < 6 && (await link.count()) === 0; i++) {
    await group.click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(400);
  }
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  if (!href) throw new Error('Sidebar link "Certificates" has no href');
  expect(href).toBe('/master-data-management/certificates');
  await page.goto(href, { waitUntil: 'commit' });
}

test('certificates: sidebar -> list -> create -> detail -> timeline -> delete', async ({ page }) => {
  const calls: string[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (u.includes('/api/v1/master-data/certificates')) {
      const parsed = new URL(u);
      calls.push(`${r.method()} ${parsed.pathname}${parsed.search}`);
    }
  });
  const seen = (method: string, pattern: RegExp) =>
    calls.some((c) => c.startsWith(method) && pattern.test(c));

  const stamp = Date.now();
  const certNumber = `E2E-${stamp}`;
  const scheme = 'PPS';
  const title = `${scheme} ${certNumber}`;

  await login(page);

  // NAV - the Certificates leaf renders under Product Management and routes.
  await openCertificatesLeaf(page);
  await page.waitForURL(/\/master-data-management\/certificates$/);

  // FE-3 - the first list call is validity-scoped, not "all".
  await expect
    .poll(() => seen('GET', /\/master-data\/certificates\/\?.*validity_state=expiring_soon%2Cexpired/), {
      timeout: 15_000,
    })
    .toBeTruthy();

  // ── Create via the modal (FE-8) ──────────────────────────────────────────
  await page.getByRole('button', { name: /Add Certificate/i }).click();
  const createDialog = page.getByRole('dialog', { name: /Add Certificate/i });
  await expect(createDialog).toBeVisible({ timeout: 10_000 });

  await createDialog.getByLabel('Scheme *').fill(scheme);
  await createDialog.getByLabel('Certificate number *').fill(certNumber);
  await createDialog.getByLabel('Certifying body *').fill('SIRIM QAS International');
  // An expiry in the past keeps the row inside the validity-scoped default view.
  await createDialog.getByLabel('Valid from').fill('2020-01-01');
  await createDialog.getByLabel('Valid until').fill('2021-01-01');
  await createDialog.getByRole('button', { name: /^Create$/ }).click();

  await expect
    .poll(() => seen('POST', /\/master-data\/certificates$/), { timeout: 15_000 })
    .toBeTruthy();
  await expect(createDialog).toBeHidden({ timeout: 15_000 });

  // ── Find the new row ─────────────────────────────────────────────────────
  await page.getByPlaceholder('Search by number...').fill(certNumber);
  const row = page.getByRole('row').filter({ hasText: certNumber }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  // The derived validity state is rendered as a pill, never a stored status.
  await expect(row.getByText('Expired')).toBeVisible();

  // ── Row -> detail page ───────────────────────────────────────────────────
  await row.click();
  await page.waitForURL(/\/master-data-management\/certificates\/[0-9a-f-]{36}$/, {
    timeout: 20_000,
  });
  await expect
    .poll(() => seen('GET', /\/master-data\/certificates\/[0-9a-f-]{36}$/), { timeout: 15_000 })
    .toBeTruthy();

  // FE-9 - the header carries the human identity, not an id.
  await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 15_000 });

  // FE-5 - EVERY section renders, even though this certificate has nothing
  // attached, each with its own empty state.
  for (const section of [
    'Certificate',
    'Review flags',
    'Revision history',
    'Covered products',
    'Unmatched product codes',
    'Suspected duplicate',
    'Expiry reminders',
  ]) {
    await expect(page.getByText(section, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText('No product is covered yet')).toBeVisible();
  await expect(page.getByText('Everything matched')).toBeVisible();
  await expect(page.getByText('No near match')).toBeVisible();
  await expect(page.getByText('No reminder sent yet')).toBeVisible();

  // FE-6 - the revision history renders the timeline. A manually created
  // certificate has no document behind it, so the empty node is what shows,
  // with its upload next-step CTA.
  await expect(page.getByText('No revision on file')).toBeVisible();
  await expect(page.getByRole('link', { name: /Upload the document/i })).toHaveAttribute(
    'href',
    '/resource-management/attachment-directories',
  );

  // ── Delete behind the confirmation dialog (FE-8) ─────────────────────────
  await page.getByRole('button', { name: /^Delete$/ }).click();
  const confirm = page.getByRole('dialog', { name: /confirm delete/i });
  await expect(confirm.getByText('Confirm delete')).toBeVisible();
  await expect(confirm.getByText(new RegExp(`Delete ${scheme} ${certNumber}`))).toBeVisible();
  await expect(confirm.getByText(/This action cannot be undone/i)).toBeVisible();
  await confirm.getByRole('button', { name: /^Delete$/ }).click();

  await expect
    .poll(() => seen('DELETE', /\/master-data\/certificates\/[0-9a-f-]{36}$/), { timeout: 15_000 })
    .toBeTruthy();

  // Back on the list, and the row is gone.
  await page.waitForURL(/\/master-data-management\/certificates$/, { timeout: 20_000 });
  await page.getByPlaceholder('Search by number...').fill(certNumber);
  await expect(page.getByRole('row').filter({ hasText: certNumber })).toHaveCount(0, {
    timeout: 15_000,
  });
});
