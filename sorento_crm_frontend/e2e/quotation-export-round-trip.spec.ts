/**
 * The quotation PDF export, end to end: queue -> worker -> storage -> collected in the browser.
 *
 * A quotation PDF is no longer rendered in the request. "Download PDF" leaves a `user_downloads`
 * row behind, an RQ worker renders it with WeasyPrint, stores it, and the file is collected from
 * the printer chip on the document (or the My Downloads drawer). This spec walks that whole loop
 * against the real stack, with data it creates and deletes itself.
 *
 * What it pins, in order:
 *   1. The click POSTs `.../issues/{issueId}/export/pdf` ...
 *   2. ... and issues NO synchronous `GET .../issues/{issueId}/pdf`. That inline route still
 *      exists for API callers, so nothing but a test stops this screen quietly going back to it -
 *      and going back to it is exactly the regression the async work was done to prevent.
 *   3. The printer chip's count moves on the click, not on its next 4-second poll (the mutation
 *      invalidates `entity-downloads`; without that the user presses the button and sees nothing).
 *   4. The chip opens a downloads dialog SCOPED to that revision
 *      (`GET /api/v1/downloads?source_entity_type=quotation_issue&source_entity_id={issueId}`).
 *   5. The row reaches Ready - i.e. the worker really rendered and stored a file - and previews.
 *
 * Step 5 needs EXACTLY ONE RQ worker draining `imports`, and it has to be booted from THIS
 * worktree. A worker started from another checkout drains the same queue but cannot import
 * `app.tasks.export_tasks.generate_quotation_issue_pdf`, so it fails the job on sight and the row
 * never leaves `pending`. Two workers is worse than one wrong one: RQ hands the queue to whichever
 * has been blocked longest, so they alternate and this spec passes every other run. The assertion
 * names all of that rather than letting a green-then-red pattern read as UI flake.
 *
 * Required env vars (the spec skips itself without them):
 *   PORTAL_E2E_BASE_URL=http://localhost:3010   (defaults to :3000 in playwright.config.ts)
 *   QUOTATION_E2E_EMAIL     / QUOTATION_E2E_PASSWORD, or
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD
 *
 * Data: registers one `ZZT ...` project, quotes one scope with one line, signs and issues R1,
 * queues one PDF, then deletes the project - which cascades the whole quotation away.
 */
import { test, expect, type Page } from '@playwright/test';
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

/** Every request the page makes, so an assertion can be made about one that must NOT happen. */
function recordRequests(page: Page): string[] {
  const seen: string[] = [];
  page.on('request', (request) => seen.push(`${request.method()} ${request.url()}`));
  return seen;
}

/** The synchronous renders this screen must never call. Still mounted for API callers. */
const INLINE_RENDER =
  /\/quotation-documents\/[0-9a-f-]+\/issues\/[0-9a-f-]+\/(pdf|xlsx)(\?|$)/;

test.describe('Quotation PDF export round trip', () => {
  test('Download PDF queues, the chip counts it, and the worker delivers a ready file', async ({
    page,
  }) => {
    // Registering a project, pricing it, issuing it, rendering a PDF and tearing it all down
    // does not fit the 90s default.
    test.setTimeout(300_000);

    const requests = recordRequests(page);
    await login(page);

    // Captured as soon as the project exists so the teardown below can still remove it when
    // the setup itself is what breaks.
    let projectUrl: string | null = null;
    try {
      const quotation = await createIssuedQuotation(page, 'export', (url) => {
        projectUrl = url;
      });

      const chip = page.locator('button[title^="View downloads for"]');
      // Nothing has been exported yet. Asserted rather than assumed: if the chip already read
      // 1 the "moves immediately" assertion below would pass without the click doing anything.
      await expect(chip).toHaveText('0', { timeout: 20_000 });

      // ---- 1 + 2: queued, not rendered inline -------------------------------------------
      const queued = page.waitForResponse(
        (response) =>
          /\/quotation-documents\/[0-9a-f-]+\/issues\/[0-9a-f-]+\/export\/pdf$/.test(
            response.url(),
          ) && response.request().method() === 'POST',
        { timeout: 30_000 },
      );
      await openMenu(page, page.getByRole('button', { name: /quotation actions/i }));
      await press(page.getByRole('menuitem', { name: /download pdf/i }));
      const queuedResponse = await queued;
      expect(queuedResponse.status()).toBe(200);

      const issueId = queuedResponse.url().match(/\/issues\/([0-9a-f-]+)\/export\/pdf$/)?.[1];
      expect(issueId, 'the export POST names the revision it is exporting').toBeTruthy();

      // The whole point of the change. The inline render is still mounted on the backend for
      // API callers, so only an assertion keeps this screen off it.
      expect(
        requests.filter((request) => INLINE_RENDER.test(request)),
        'Download PDF must not fall back to the synchronous inline render',
      ).toEqual([]);

      // The click's only feedback in the browser, so it is worth pinning too.
      await expect(page.getByText(/preparing the pdf/i)).toBeVisible({ timeout: 15_000 });

      // ---- 3: the count moves on the click ------------------------------------------------
      // Under 4s deliberately: 4s is `EntityDownloadsButton`'s poll interval, so a longer window
      // would also pass if the mutation stopped invalidating `entity-downloads` altogether.
      await expect(chip).toHaveText('1', { timeout: 3_500 });

      // ---- 4: the chip opens THIS revision's downloads -------------------------------------
      const scopedFeed = page.waitForResponse(
        (response) =>
          response.url().includes('/api/v1/downloads?') &&
          response.url().includes('source_entity_type=quotation_issue') &&
          response.url().includes(`source_entity_id=${issueId}`) &&
          response.request().method() === 'GET' &&
          response.status() === 200,
        { timeout: 30_000 },
      );
      await press(chip);
      await scopedFeed;

      const dialog = page.getByRole('dialog');
      // Titled with the revision, not the document: earlier revisions' files stay in the drawer.
      await expect(dialog.getByText(`Downloads · ${quotation.ourRef}`)).toBeVisible({
        timeout: 15_000,
      });
      await expect(dialog.getByText('Quotation PDF')).toBeVisible({ timeout: 15_000 });

      // ---- 5: the worker actually rendered it ---------------------------------------------
      // The dialog re-polls every 4s while anything is in flight, so this is a wait, not a race.
      await expect(
        dialog.getByText('Ready'),
        'The export never left Queued/Preparing, so look at the RQ worker before the UI. ' +
          'Exactly ONE worker must be draining `imports`, booted from THIS worktree: one from ' +
          'another checkout cannot import app.tasks.export_tasks.generate_quotation_issue_pdf ' +
          'and fails the job instantly, and two workers alternate, which makes this spec pass ' +
          'every other run. Check with `ps ax | grep worker.py` and the worker log.',
      ).toBeVisible({ timeout: 180_000 });

      // ... and the stored file can be read without leaving the page.
      await press(dialog.getByRole('button', { name: /^preview /i }));
      const preview = page.getByRole('dialog').filter({ has: page.locator('iframe') });
      await expect(preview.locator('iframe')).toBeVisible({ timeout: 30_000 });

      // Re-checked over the WHOLE flow, not just the click: collecting the file must not reach
      // for the inline render either.
      expect(
        requests.filter((request) => INLINE_RENDER.test(request)),
        'nothing in the export flow may call the synchronous inline render',
      ).toEqual([]);
    } finally {
      // Deleting the PROJECT is the only way out: the document's own DELETE refuses an issued
      // quotation, and the project FK cascades.
      if (projectUrl) await deleteProject(page, projectUrl);
    }
  });
});
