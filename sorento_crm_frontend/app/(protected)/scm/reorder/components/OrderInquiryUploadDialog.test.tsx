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

function inquiryPreview(over: Partial<OrderInquiryPreview> = {}): OrderInquiryPreview {
  return {
    ok: true,
    problems: [],
    rows: 105,
    instalments: 88,
    rows_restating_an_instalment: 17,
    sheets_read: ['Sheet1'],
    sheets_skipped: [],
    lines_matched: 71,
    lines_unmatched: 34,
    sales_orders_not_found: ['SO414033', 'SO414034'],
    with_location: 105,
    unknown_locations: ['BRW-ZZ'],
    po_claims: 62,
    not_ordered: 19,
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

describe('OrderInquiryUploadDialog - order inquiry', () => {
  it('shows the rows, the locations and the purchase-order links', async () => {
    renderDialog();
    await choose('inquiry.xlsx');

    expect(await screen.findByText('Rows')).toBeInTheDocument();
    expect(within(tile('Matched')).getByText('71')).toBeInTheDocument();
    expect(within(tile('PO links')).getByText('62')).toBeInTheDocument();
    // `ORDER` in the remark column means nothing has been placed yet. It is a state, not a
    // parse failure, so it is counted on its own rather than reported as a problem.
    expect(within(tile('Not ordered yet')).getByText('19')).toBeInTheDocument();
  });

  it('names the sales orders whose locations could not be written', async () => {
    // A location can only be written onto a line that exists. That limit is real, so the
    // orders are NAMED - re-uploading after the SO book lands applies them, and somebody
    // has to be able to see which.
    renderDialog();
    await choose('inquiry.xlsx');

    expect(await screen.findByText('SO414033')).toBeInTheDocument();
    expect(screen.getByText(/Upload this sheet again once those orders land/i)).toBeInTheDocument();
  });

  it('heads the list with the real total, not the length of the capped sample', async () => {
    // The backend caps every named list at 200. Heading the section with the length of what
    // it happens to be showing turned 15,787 missing sales orders into "(200)" on the real
    // file - a number that reads like a small, closed problem.
    previewOrderInquiry.mockResolvedValue(
      inquiryPreview({
        rows: 15797,
        lines_matched: 10,
        lines_unmatched: 15787,
        sales_orders_not_found: Array.from({ length: 200 }, (_, i) => `SO90${i}`),
      }),
    );
    renderDialog();
    await choose('book.xlsx');

    expect(
      await screen.findByText(/Sales orders we have not received yet \(15,787\)/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\(200\)/)).toBeNull();
  });

  it('names a location code it does not recognise', async () => {
    renderDialog();
    await choose('inquiry.xlsx');

    expect(await screen.findByText('BRW-ZZ')).toBeInTheDocument();
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

describe('OrderInquiryUploadDialog - one delivery, stated on many sheets', () => {
  it('shows the row count AND the number of scheduled deliveries', async () => {
    // The customer's book carries a month tab, a roll-up tab covering that month and dated
    // working snapshots, so 15,797 rows describe 8,272 deliveries. Showing only the smaller
    // figure reads as rows lost; showing only the larger one is the bug we just fixed.
    renderDialog();
    await choose('inquiry.xlsx');

    const rows = (await screen.findByText('Rows')).closest(
      '[data-slot="count-tile"]',
    ) as HTMLElement;
    expect(within(rows).getByText('105')).toBeInTheDocument();
    const deliveries = screen
      .getByText('Scheduled deliveries')
      .closest('[data-slot="count-tile"]') as HTMLElement;
    expect(within(deliveries).getByText('88')).toBeInTheDocument();
  });

  it('says how many rows restated a delivery another sheet already lists', async () => {
    renderDialog();
    await choose('inquiry.xlsx');

    expect(
      await screen.findByText(/17 rows restate a delivery another sheet already lists/),
    ).toBeInTheDocument();
  });

  it('reports a withdrawal on the JOB, not here - but never silently', async () => {
    /**
     * Deleting demand silently is the one thing an import must never do, and it still does
     * not: every withdrawn instalment is recorded as its own per-row outcome
     * (`line_withdrawn`) on the job. What changed is where it is read, because the deletion
     * happens on the worker.
     */
    renderDialog();
    await choose('inquiry.xlsx');
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    fireEvent.click(confirmButton());

    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
    expect(screen.queryByText(/no longer lists/)).toBeNull();
  });
});
