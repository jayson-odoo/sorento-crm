/**
 * The customer's revision request, end to end - and back onto the salesperson's screen.
 *
 * The client's question was literally "when i request changes, how can i see it from the system?",
 * so a spec that stops when the counter-sign page says "Changes requested" proves nothing they
 * asked about. This one closes the loop: it hands out the counter-sign link, answers it as the
 * customer, and then returns to the CRM through the sidebar to prove the words came back onto the
 * DOCUMENT - not into the Signatures tab that nobody opens, which was the original complaint.
 *
 * What it pins, in order:
 *   1. Gear -> Copy counter-sign link mints a token
 *      (`POST .../issues/{issueId}/sign-link`) and the URL is readable on screen.
 *   2. A stranger (its own browser context, no CRM session) can open that URL and read the
 *      quotation - same Our Ref the salesperson is looking at.
 *   3. "Request changes" opens the note, and Send is DISABLED while the note is empty. An empty
 *      request is not a request: the backend refuses it, so the button that would send it never
 *      goes live.
 *   4. Sending settles the page to "Changes requested" with the customer's own words quoted back,
 *      WITHOUT a reload (the response carries the whole page; proved with a window marker that
 *      would not survive a navigation).
 *   5. Back in the CRM, reached by clicking the sidebar: the project's Quotations list reads
 *      "Changes requested" in its Status column, and opening the quotation shows the words in a
 *      banner on the document itself - asserted while the Signatures tab is demonstrably NOT open.
 *
 * Required env vars (the spec skips itself without them):
 *   PORTAL_E2E_BASE_URL=http://localhost:3010   (defaults to :3000 in playwright.config.ts)
 *   QUOTATION_E2E_EMAIL     / QUOTATION_E2E_PASSWORD, or
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD
 *
 * Data: registers one `ZZT ...` project, quotes one scope with one line, signs and issues R1,
 * requests changes on it as the customer, then deletes the project - which cascades the whole
 * quotation, its issue, its sign token and the request away.
 */
import { test, expect } from '@playwright/test';
import {
  EMAIL,
  PASSWORD,
  createIssuedQuotation,
  deleteProject,
  login,
  openMenu,
  press,
} from './support/quotationRoundTrip';

test.skip(!EMAIL || !PASSWORD, 'Set QUOTATION_E2E_* (or REQUEST_BATCH_E2E_*) to run this spec.');

const NOTE = 'ZZT can you provide more discount on the townhouse rate?';

test.describe('Quotation revision request round trip', () => {
  test('the customer asks for changes and the salesperson reads it on the document', async ({
    page,
    browser,
  }) => {
    // Registering a project, pricing it, issuing it, answering it as the customer and tearing it
    // all down does not fit the 90s default.
    test.setTimeout(300_000);

    await login(page);

    /**
     * The counter-sign dialog only renders when the clipboard write is refused - the happy path
     * copies silently and toasts. Removing `navigator.clipboard` picks the fallback branch
     * DETERMINISTICALLY (it is the branch the product already ships for plain HTTP and for
     * browsers that block clipboard access) so the URL can be read off the DOM instead of the
     * spec racing a clipboard permission it does not control.
     */
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    });

    let projectUrl: string | null = null;
    try {
      const quotation = await createIssuedQuotation(page, 'revision', (url) => {
        projectUrl = url;
      });

      // ---- 1: mint the link ---------------------------------------------------------------
      const minted = page.waitForResponse(
        (response) =>
          /\/quotation-documents\/[0-9a-f-]+\/issues\/[0-9a-f-]+\/sign-link$/.test(
            response.url(),
          ) && response.request().method() === 'POST',
        { timeout: 30_000 },
      );
      await openMenu(page, page.getByRole('button', { name: /quotation actions/i }));
      await press(page.getByRole('menuitem', { name: /copy counter-sign link/i }));
      expect((await minted).status()).toBe(200);

      const linkDialog = page.getByRole('dialog');
      await expect(linkDialog.getByText('Counter-sign link')).toBeVisible({ timeout: 15_000 });
      const signUrl = await linkDialog.getByLabel('Counter-sign link').inputValue();
      expect(signUrl, 'the dialog shows the tokenised counter-sign URL').toMatch(
        /\/quotation-sign\/[^/]+$/,
      );

      // ---- 2: the customer opens it cold --------------------------------------------------
      // Its own context: the counter-sign page is a public, NextAuth-independent surface, and
      // arriving on it with a staff session would not be the journey being tested. This is the
      // one legitimate direct navigation in these specs - it IS how the customer arrives.
      const customerContext = await browser.newContext();
      const customer = await customerContext.newPage();
      try {
        await customer.goto(signUrl, { waitUntil: 'commit' });
        await expect(customer.getByTestId('quotation-sign-page')).toBeVisible({
          timeout: 30_000,
        });
        // The same reference the salesperson is looking at, proving the token resolved to THIS
        // revision rather than to some other quotation.
        await expect(customer.getByText(quotation.ourRef)).toBeVisible({ timeout: 15_000 });

        // ---- 3: an empty request is refused before it is sent -----------------------------
        await expect(
          customer.getByRole('heading', { name: /accept this quotation/i }),
        ).toBeVisible({ timeout: 15_000 });
        await press(customer.getByRole('button', { name: /request changes/i }));

        const note = customer.getByLabel('What needs to change');
        await expect(note).toBeVisible({ timeout: 15_000 });
        const send = customer.getByRole('button', { name: /send request/i });
        await expect(send, 'Send stays disabled until the customer says what to change')
          .toBeDisabled();
        await expect(customer.getByText(/tell us what to change before sending/i)).toBeVisible();

        // A box holding only spaces is still empty: the note is trimmed before it counts.
        await note.fill('    ');
        await expect(send, 'whitespace is not a request').toBeDisabled();

        // ---- 4: send it, and settle in place ----------------------------------------------
        await note.fill(NOTE);
        await expect(send).toBeEnabled({ timeout: 10_000 });

        // A marker that only survives if the page never navigates.
        await customer.evaluate(() => {
          (window as unknown as Record<string, unknown>).__zztNoReload = true;
        });

        const sent = customer.waitForResponse(
          (response) =>
            /\/api\/v1\/public\/quotation-sign\/[^/]+\/request-changes$/.test(response.url()) &&
            response.request().method() === 'POST',
          { timeout: 30_000 },
        );
        await press(send);
        expect((await sent).status()).toBe(200);

        // The form is REPLACED by the settled answer - a form still sitting there is how the
        // same message gets sent four times.
        await expect(customer.getByText('Changes requested')).toBeVisible({ timeout: 20_000 });
        await expect(customer.getByText(NOTE)).toBeVisible({ timeout: 15_000 });
        await expect(customer.getByRole('button', { name: /send request/i })).toHaveCount(0);

        expect(
          await customer.evaluate(
            () => (window as unknown as Record<string, unknown>).__zztNoReload,
          ),
          'the page settled on the response, without a reload',
        ).toBe(true);
      } finally {
        await customerContext.close();
      }

      // ---- 5: and the salesperson reads it, on the document -------------------------------
      // Back in through the sidebar rather than by re-opening the URL still in the address bar:
      // the list is where a salesperson notices, and its Status column is the other surface the
      // client's question covers.
      await page.goto('/', { waitUntil: 'commit' });
      const group = page.getByRole('button', { name: 'Project Sales', exact: true }).first();
      await expect(group).toBeVisible({ timeout: 20_000 });
      if ((await group.getAttribute('aria-expanded')) !== 'true') {
        await group.dispatchEvent('click');
      }
      await press(page.getByRole('link', { name: /^pipeline$/i }).first());
      await page.waitForURL(/project-sales\/pipeline/, { timeout: 30_000 });

      // Grid view, because a row is the way into a record and the board draws cards.
      await press(page.getByRole('button', { name: /grid view/i }));
      await page.getByRole('textbox', { name: /search projects/i }).fill(quotation.projectTitle);
      const projectRow = page.locator('table tbody tr', { hasText: quotation.projectTitle });
      await expect(projectRow).toHaveCount(1, { timeout: 30_000 });
      await press(projectRow.first());
      await page.waitForURL(/project-sales\/[0-9a-f-]{36}(\?|$)/, { timeout: 30_000 });

      await press(page.getByRole('button', { name: /^quotations$/i }));
      const quotationRow = page.locator('table tbody tr', { hasText: quotation.ourRef });
      await expect(quotationRow).toHaveCount(1, { timeout: 30_000 });
      // The customer's answer IS where the quotation stands, so it replaces "Issued" in the
      // existing Status column rather than arriving as a second, mostly-empty column.
      await expect(quotationRow.getByText('Changes requested')).toBeVisible({ timeout: 15_000 });

      await press(quotationRow.first());
      await page.waitForURL(/quotation-documents\/[0-9a-f-]{36}$/, { timeout: 30_000 });

      // THE POINT OF THIS SPEC. On the document, on the tab it opens on, without going looking.
      await expect(page.getByText(/asked for changes on/i)).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(NOTE)).toBeVisible({ timeout: 15_000 });
      await expect(page.getByRole('button', { name: /revise this quotation/i })).toBeVisible();

      // ... and the Signatures tab is demonstrably still shut. Asserted positively as well as
      // negatively: "not active" alone would also hold on a page where no tab is active at all.
      expect(page.url(), 'the banner is read without opening Signatures').not.toContain(
        '/signatures',
      );
      const tabStrip = page.getByTestId('quotation-document-tab-strip');
      await expect(tabStrip.getByRole('tab', { name: /^scopes$/i })).toHaveAttribute(
        'data-state',
        'active',
      );
      await expect(tabStrip.getByRole('tab', { name: /^signatures$/i })).toHaveAttribute(
        'data-state',
        'inactive',
      );
    } finally {
      // Deleting the PROJECT is the only way out: the document's own DELETE refuses an issued
      // quotation, and the project FK cascades.
      if (projectUrl) await deleteProject(page, projectUrl);
    }
  });
});
