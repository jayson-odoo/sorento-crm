/**
 * The Order Inquiry upload dialog: test, confirm, and what each state says.
 *
 * Renamed from `HistoryUploadDialog.test.tsx` (ingest-parity-standardisation S4, AC-P4-1): the
 * purchase-history and sales-history describe blocks this file used to also carry were
 * deleted along with the retired channels. What is asserted here is what the SCREEN promises,
 * not what the parser does. Four claims carry most of the weight:
 *
 * 1. Choosing a file runs NOTHING. Test reads it; Confirm queues the write.
 * 2. Confirm QUEUES: `notifyImportQueued()` so the upload drawer follows the job, the dialog
 *    closes, and no counts are claimed - the write happens on the worker.
 * 3. A file that could not be read says WHY, and does not offer to be queued.
 * 4. The problems are NAMED, not only counted - the sales orders we have not received yet are
 *    the list somebody acts on.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const notifyImportQueued = vi.fn();
vi.mock('@/components/upload-activity/useImportJobDrawer', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued }),
}));

const previewOrderInquiry = vi.fn();
const applyOrderInquiry = vi.fn();
const testOrderInquiry = vi.fn();
vi.mock('../services/orderInquiryService', () => ({
  previewOrderInquiry: (...a: unknown[]) => previewOrderInquiry(...a),
  applyOrderInquiry: (...a: unknown[]) => applyOrderInquiry(...a),
  testOrderInquiry: (...a: unknown[]) => testOrderInquiry(...a),
}));

// The accept list is the server's, asked for as soon as the dialog opens. Mocked here for
// the same reason it is mocked in the outstanding dialog's suite: leaving it out makes the
// import undefined and every test fails inside an effect, for a reason unrelated to what it
// was asserting.
const getOutstandingUploadConfig = vi.fn();
vi.mock('../services/outstandingImportService', () => ({
  getOutstandingUploadConfig: (...a: unknown[]) => getOutstandingUploadConfig(...a),
}));

import { OrderInquiryUploadDialog } from './OrderInquiryUploadDialog';
import type { UploadTestResult } from './UploadTestVerdict';
import type { OrderInquiryPreview } from '../services/orderInquiryService';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';

// ── fixtures ────────────────────────────────────────────────────────────────
// Distinct numbers throughout, so a `getByText` on one figure can never match another.

const QUEUED: ImportQueuedResult = {
  message: 'Order inquiry upload queued.',
  job_id: 'job-inq-1',
  id: 'row-1',
};

/**
 * The migration-tool shape, AC-S1-22 exactly (`PLAN-scm-oi-sheet-migration.md`). The retired
 * keys - `instalments`, `lines_matched`, `po_claims`, `unknown_locations`, `not_ordered` and
 * the rest - are gone, because the sheet no longer creates sales orders or writes locations:
 * AutoCount owns both, and what the sheet carries is which line is owed and on which PO/SPO.
 */
function inquiryPreview(over: Partial<OrderInquiryPreview> = {}): OrderInquiryPreview {
  return {
    ok: true,
    problems: [],
    orders_adopted: 9,
    orders_stamped: 14,
    rows: 105,
    rows_raised: 71,
    rows_already_raised: 17,
    rows_delivery_date_updated: 6,
    rows_line_not_found: 12,
    line_not_found: [
      { so_number: 'SO414040', item_code: 'C-FH14', qty: 30, reason: 'location_differs' },
    ],
    sales_orders_not_found: ['SO414033', 'SO414034'],
    orders_not_plannable: [
      { so_number: 'SO414099', code: 'sales_order_not_project_class' },
    ],
    links_written: 62,
    links_partial: 4,
    links_from_autocount: 41,
    documents_not_linkable: ['202606-S0024'],
    sheets_read: ['Sheet1'],
    sheets_skipped: [],
    ...over,
  };
}

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function file(name = 'inquiry.xlsx'): File {
  return new File(['x'], name, { type: XLSX });
}

function dropzone(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

/** Pick a file. Runs nothing - that is the point of the change. */
async function pick(name = 'inquiry.xlsx') {
  fireEvent.change(dropzone(), { target: { files: [file(name)] } });
  await waitFor(() => expect(testButton()).toBeEnabled());
}

/** Pick a file AND press Test, which is what every assertion about the summary needs. */
async function choose(name = 'inquiry.xlsx') {
  await pick(name);
  fireEvent.click(testButton());
  await waitFor(() => expect(testButton()).toBeEnabled());
}

function confirmButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /Confirm upload/i }) as HTMLButtonElement;
}

function tile(label: string): HTMLElement {
  const node = screen.getByText(label).closest('[data-slot="count-tile"]');
  if (!node) throw new Error(`no count tile labelled ${label}`);
  return node as HTMLElement;
}

function verdict(over: Partial<UploadTestResult> = {}): UploadTestResult {
  return {
    valid: true,
    errors: [],
    warnings: [],
    summary: { total_rows: 105, would_create: 71, would_update: 0, error_count: 0 },
    ...over,
  };
}

function testButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^Test$/i }) as HTMLButtonElement;
}

function renderDialog(onQueued = vi.fn(), onOpenChange = vi.fn()) {
  render(
    <OrderInquiryUploadDialog open onOpenChange={onOpenChange} onQueued={onQueued} />,
  );
  return { onQueued, onOpenChange };
}

beforeEach(() => {
  previewOrderInquiry.mockReset().mockResolvedValue(inquiryPreview());
  applyOrderInquiry.mockReset().mockResolvedValue(QUEUED);
  notifyImportQueued.mockReset();
  push.mockReset();
  getOutstandingUploadConfig
    .mockReset()
    .mockResolvedValue({ allowed_extensions: ['.xlsx', '.xlsm', '.xls'] });
  testOrderInquiry.mockReset().mockResolvedValue(verdict());
});

// ── 5. the Test function, which every other importer in this system has ─────

describe('OrderInquiryUploadDialog - Test', () => {
  it('is offered once a file is chosen, and writes nothing', async () => {
    renderDialog();
    expect(testButton()).toBeDisabled();

    await pick();
    fireEvent.click(testButton());

    await waitFor(() => expect(testOrderInquiry).toHaveBeenCalledTimes(1));
    // Both reads on one press: the rich preview AND the standard verdict.
    expect(previewOrderInquiry).toHaveBeenCalledTimes(1);
    expect(applyOrderInquiry).not.toHaveBeenCalled();
  });

  it('shows the green verdict when there is nothing to fix', async () => {
    renderDialog();
    await choose();

    expect(await screen.findByText('No errors')).toBeInTheDocument();
  });

  it('shows errors and warnings separately, because only one of them blocks', async () => {
    testOrderInquiry.mockResolvedValue(
      verdict({
        valid: false,
        errors: ['No inquiry rows found in this file.'],
        warnings: ['2 locations we do not recognise'],
      }),
    );
    renderDialog();
    await choose();

    expect(await screen.findByText('Errors (1)')).toBeInTheDocument();
    expect(screen.getByText('Warnings (1)')).toBeInTheDocument();
    expect(screen.queryByText('No errors')).toBeNull();
  });

  it('warns on a file that is still perfectly loadable', async () => {
    // The distinction the button exists for: a warning is information, not a refusal.
    testOrderInquiry.mockResolvedValue(
      verdict({ warnings: ['19 rows carry no order yet'] }),
    );
    renderDialog();
    await choose();

    expect(await screen.findByText('No errors')).toBeInTheDocument();
    expect(screen.getByText('Warnings (1)')).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });

  it('does not force a Test before Confirm', async () => {
    // Testing is a tool, not ceremony - the same rule as the GRN and customer importers.
    renderDialog();
    await pick();

    expect(confirmButton()).toBeEnabled();
    expect(testOrderInquiry).not.toHaveBeenCalled();
    expect(previewOrderInquiry).not.toHaveBeenCalled();
  });

  it('drops the verdict when a different file is chosen', async () => {
    // A green tick for the previous file, still on screen above a new one, is how somebody
    // uploads a bad file believing it was tested.
    renderDialog();
    await choose('first.xlsx');
    expect(await screen.findByText('No errors')).toBeInTheDocument();

    await pick('second.xlsx');
    await waitFor(() => expect(screen.queryByText('No errors')).toBeNull());
  });
});

// ── 6. the reading row holds its place ──────────────────────────────────────

/**
 * Pressing Test on a large book made the popup shake for as long as `Reading the file...` was
 * on screen. Two causes, both measured in a browser rather than guessed at, and both are
 * properties of this row:
 *
 * 1. mounting the row on press grew the dialog by 36px, and `DialogContent` is centred with
 *    `translate-y-[-50%]`, so the whole popup jumped when the read started and again when it
 *    finished;
 * 2. the spinner is `animate-spin` inside `DialogBody`, which is `overflow-y-auto` with no
 *    padding. A rotating square's border box reaches `16 * sqrt(2)` = 22.6px and a transform
 *    still counts towards an ancestor's scrollable overflow, so the body's `scrollHeight`
 *    crossed its `clientHeight` and back every animation frame - measured flipping the body's
 *    `clientWidth` 718 <-> 703 wherever the platform draws a space-taking scrollbar.
 *
 * jsdom computes no layout, so neither is directly assertable here. What IS assertable is the
 * structure both fixes depend on: the row is always in the DOM (so its height never changes),
 * it is hidden with `invisible` rather than unmounted, and the spinner sits in a clipped box
 * and only spins while reading.
 */
describe('OrderInquiryUploadDialog - the reading row', () => {
  function readingRow(): HTMLElement {
    const node = document.querySelector('[data-slot="upload-reading-indicator"]');
    if (!node) throw new Error('the reading row is not in the DOM');
    return node as HTMLElement;
  }

  it('keeps its row before, during and after the read, so the popup never moves', async () => {
    let release!: (p: OrderInquiryPreview) => void;
    previewOrderInquiry.mockReturnValue(
      new Promise<OrderInquiryPreview>((resolve) => {
        release = resolve;
      }),
    );
    renderDialog();

    // Before: present, holding its space, and hidden rather than absent.
    expect(readingRow()).toHaveClass('invisible');
    expect(readingRow()).toHaveClass('min-h-5');

    await pick();
    fireEvent.click(testButton());

    // During: the same element, now visible and spinning.
    await waitFor(() => expect(readingRow()).not.toHaveClass('invisible'));
    expect(readingRow().querySelector('.animate-spin')).not.toBeNull();

    release(inquiryPreview());

    // After: back to hidden, never unmounted.
    await waitFor(() => expect(readingRow()).toHaveClass('invisible'));
    expect(readingRow().querySelector('.animate-spin')).toBeNull();
  });

  it('clips the spinner to its own box, so its rotation cannot overflow the scrolling body', async () => {
    let release!: (p: OrderInquiryPreview) => void;
    previewOrderInquiry.mockReturnValue(
      new Promise<OrderInquiryPreview>((resolve) => {
        release = resolve;
      }),
    );
    renderDialog();
    await pick();
    fireEvent.click(testButton());

    await waitFor(() => expect(readingRow()).not.toHaveClass('invisible'));
    const spinner = readingRow().querySelector('.animate-spin');
    const clip = spinner?.parentElement;
    expect(clip).not.toBeNull();
    // Without the clip the rotated 16px icon reaches 22.6px and pushes the body's
    // scrollHeight past its clientHeight and back, sixty times a second.
    expect(clip).toHaveClass('overflow-hidden');
    expect(clip).toHaveClass('size-4');

    release(inquiryPreview());
    await waitFor(() => expect(readingRow()).toHaveClass('invisible'));
  });

  it('runs one read per press, so the row cannot flicker on a double toggle', async () => {
    renderDialog();
    await choose();

    expect(previewOrderInquiry).toHaveBeenCalledTimes(1);
    expect(testOrderInquiry).toHaveBeenCalledTimes(1);
  });
});

// ── 1. nothing is written from a single click ───────────────────────────────

describe('OrderInquiryUploadDialog - test, then upload', () => {
  it('opens with nothing chosen and Confirm disabled', () => {
    renderDialog();

    expect(confirmButton()).toBeDisabled();
    expect(previewOrderInquiry).not.toHaveBeenCalled();
    expect(applyOrderInquiry).not.toHaveBeenCalled();
  });

  it('reads NOTHING when a file is chosen', async () => {
    renderDialog();
    await pick();

    await Promise.resolve();
    expect(previewOrderInquiry).not.toHaveBeenCalled();
    expect(testOrderInquiry).not.toHaveBeenCalled();
    expect(applyOrderInquiry).not.toHaveBeenCalled();
  });

  it('reads the file on Test, and Test writes nothing', async () => {
    renderDialog();
    await choose();

    await waitFor(() => expect(previewOrderInquiry).toHaveBeenCalledTimes(1));
    expect(applyOrderInquiry).not.toHaveBeenCalled();
    expect(confirmButton()).toBeEnabled();
  });

  it('queues on Confirm: drawer, close, and no counts it cannot have', async () => {
    const { onQueued, onOpenChange } = renderDialog();
    await choose();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyOrderInquiry).toHaveBeenCalledTimes(1));
    // The drawer is what follows the job; without it the operator is told "queued" and has
    // nowhere to watch it.
    expect(notifyImportQueued).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onQueued).toHaveBeenCalledWith(QUEUED);
    expect(screen.queryByText('Upload applied.')).toBeNull();
  });

  it('surfaces the extracted backend message when queueing is refused', async () => {
    applyOrderInquiry.mockRejectedValue(
      new Error('Select a single company before uploading this file.'),
    );
    const { onQueued } = renderDialog();
    await choose();

    fireEvent.click(confirmButton());

    expect(
      await screen.findByText('Select a single company before uploading this file.'),
    ).toBeInTheDocument();
    expect(onQueued).not.toHaveBeenCalled();
    expect(notifyImportQueued).not.toHaveBeenCalled();
  });
});

// ── 2. a file we could not read ─────────────────────────────────────────────

describe('OrderInquiryUploadDialog - an unreadable file', () => {
  it('says why, and does not offer to apply it', async () => {
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({ ok: false, problems: ['No inquiry rows found in this file.'] }),
    );
    renderDialog();
    await choose();

    expect(
      await screen.findByText('No inquiry rows found in this file.'),
    ).toBeInTheDocument();
    await waitFor(() => expect(confirmButton()).toBeDisabled());
  });

  it('surfaces a failed request as an error rather than an empty dialog', async () => {
    /**
     * A failed READ does not disable Confirm. Test is a tool, not a gate, so a file whose
     * Test could not reach the server may still be queued - and the job then reports what
     * the worker made of it. What must not happen is silence.
     */
    previewOrderInquiry.mockRejectedValue(new Error('Backend is down'));
    renderDialog();
    await choose();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
    expect(applyOrderInquiry).not.toHaveBeenCalled();
  });
});

// ── 4. the order inquiry sheet ──────────────────────────────────────────────

describe('OrderInquiryUploadDialog - the migration preview', () => {
  it('renders eight tiles from the preview', async () => {
    // AC-S2-1 and AC-S2-8. What the operator has to decide before Confirm, and nothing else:
    // how many rows, how many will be raised, how many are already raised, how many of
    // those correct a migrated row's date (19 Sep 2026), how many found no line, how many
    // PLANNING RECORDS this opens, how many rows get linked, and the documents it could not
    // link. No tile for scheduled deliveries, matched lines, PO links or not-ordered - the
    // sheet no longer means any of them.
    renderDialog();
    await choose('inquiry.xlsx');

    expect(within(tile('Rows')).getByText('105')).toBeInTheDocument();
    expect(within(tile('Will raise')).getByText('71')).toBeInTheDocument();
    expect(within(tile('Already raised')).getByText('17')).toBeInTheDocument();
    expect(within(tile('Dates corrected')).getByText('6')).toBeInTheDocument();
    expect(within(tile('No SO line')).getByText('12')).toBeInTheDocument();
    expect(within(tile('Orders adopted')).getByText('9')).toBeInTheDocument();
    // Per ROW, and labelled as one: 62 rows gained a link, which is not a count of
    // documents (review finding 6, 14 Sep).
    expect(within(tile('Rows linked')).getByText('62')).toBeInTheDocument();
    expect(within(tile('Documents not found')).getByText('1')).toBeInTheDocument();
    expect(document.querySelectorAll('[data-slot="count-tile"]')).toHaveLength(8);
    expect(screen.queryByText('Documents found')).toBeNull();
    for (const retired of ['Matched', 'PO links', 'Not ordered yet', 'Scheduled deliveries']) {
      expect(screen.queryByText(retired)).toBeNull();
    }
  });

  it('omits an empty chip list', async () => {
    // AC-S2-2. An empty state is ABSENT, never an empty box: a heading over nothing reads
    // as a list that failed to load.
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({ documents_not_linkable: [], sales_orders_not_found: [] }),
    );
    renderDialog();
    await choose('inquiry.xlsx');

    expect(await screen.findByText('Rows')).toBeInTheDocument();
    expect(screen.queryByText(/Documents we could not link/)).toBeNull();
    expect(screen.queryByText(/Sales orders not in the CRM/)).toBeNull();
    // The list that DOES have entries is still there, so this asserts absence and not a
    // panel that failed to render at all.
    expect(screen.getByText(/Rows with no matching line/)).toBeInTheDocument();
  });

  it('names the sales orders the CRM does not hold, and the documents it could not link', async () => {
    // AC-S2-2. Named rather than only counted: the number says there is a problem, the list
    // is what somebody acts on - and NEITHER heading prints a count, because the server caps
    // both lists at 200 and the length of a capped sample reads as a small closed problem
    // (review finding 11, 14 Sep). Asserted by exact text: "(2)" beside the title would miss.
    renderDialog();
    await choose('inquiry.xlsx');

    expect(await screen.findByText('SO414033')).toBeInTheDocument();
    expect(screen.getByText('SO414034')).toBeInTheDocument();
    expect(screen.getByText('202606-S0024')).toBeInTheDocument();
    expect(screen.getByText('Sales orders not in the CRM')).toBeInTheDocument();
    expect(screen.getByText('Documents we could not link')).toBeInTheDocument();
  });

  it('formats line_not_found entries with the reason in words', async () => {
    // AC-S2-3. `SO · item · qty · reason`, and the reason in words - the chip is read by a
    // person, so the code itself never reaches the screen. The words are the ones
    // `import_outcome_codes.LABELS` prints on the job page for the same codes (review
    // finding 5, 14 Sep): the earlier paraphrases said "open line" and "outstanding", and
    // this matcher takes a closed line and compares against what the line ORDERED.
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({
        rows_line_not_found: 3,
        line_not_found: [
          { so_number: 'SO414040', item_code: 'C-FH14', qty: 30, reason: 'location_differs' },
          { so_number: 'SO414041', item_code: 'M310-CR', qty: 8, reason: 'no_line_for_item' },
          {
            so_number: 'SO414042',
            item_code: 'MSK11C',
            qty: 67,
            reason: 'qty_exceeds_ordered',
          },
        ],
      }),
    );
    renderDialog();
    await choose('inquiry.xlsx');

    expect(
      await screen.findByText(
        'SO414040 · C-FH14 · 30 · No line for this item at that stock location',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('SO414041 · M310-CR · 8 · No sales order line for this item'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('SO414042 · MSK11C · 67 · Quantity exceeds what the line ordered'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/location_differs/)).toBeNull();
  });

  it('heads the list with the real total, not the length of the capped sample', async () => {
    // AC-S2-3. The backend caps the named list at 200 and the chip list shows 20. Heading
    // the section with the length of what it happens to be showing turned 15,787 rows with
    // no line into "(20)", which reads like a small, closed problem.
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({
        rows: 15797,
        rows_raised: 10,
        rows_line_not_found: 15787,
        line_not_found: Array.from({ length: 25 }, (_, i) => ({
          so_number: `SO90${i}`,
          item_code: 'C-FH14',
          qty: 1,
          reason: 'no_line_for_item' as const,
        })),
      }),
    );
    renderDialog();
    await choose('book.xlsx');

    expect(
      await screen.findByText(/Rows with no matching line \(15,787\)/),
    ).toBeInTheDocument();
    expect(screen.getByText('+15,767 more')).toBeInTheDocument();
  });

  it('confirm disabled when nothing would be raised', async () => {
    // AC-S2-4. A sheet whose every line is already raised is a re-upload that would write
    // nothing, so Confirm is not offered - and it IS offered the moment one row would land.
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({ rows_raised: 0, rows_already_raised: 105 }),
    );
    renderDialog();
    await choose('again.xlsx');

    await waitFor(() => expect(confirmButton()).toBeDisabled());

    previewOrderInquiry.mockResolvedValue(inquiryPreview({ rows_raised: 1 }));
    await choose('fresh.xlsx');

    await waitFor(() => expect(confirmButton()).toBeEnabled());
  });

  it('leaves the link resolution to the job, which is where it now happens', async () => {
    /**
     * The resolve runs inside the queued job (it must: it is a write). So the pairing this
     * upload completed is reported on the job's result rather than here - the half nothing
     * else would say is still said, just not by a dialog that has already closed.
     */
    renderDialog();
    await choose('inquiry.xlsx');
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    fireEvent.click(confirmButton());

    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
    expect(screen.queryByRole('region', { name: /Order links/i })).toBeNull();
  });
});

describe('OrderInquiryUploadDialog - how many sheets were read', () => {
  it('says how many tabs it read, and how many it skipped', async () => {
    // A workbook of monthly tabs where one silently fails to parse looks exactly like a
    // quiet month, so the skipped count stays on screen beside the tiles.
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({ sheets_read: ['JAN 26', 'FEB 26'], sheets_skipped: ['SUMMARY'] }),
    );
    renderDialog();
    await choose('book.xlsx');

    expect(await screen.findByText(/2 sheets read, 1 skipped/)).toBeInTheDocument();
  });
});
