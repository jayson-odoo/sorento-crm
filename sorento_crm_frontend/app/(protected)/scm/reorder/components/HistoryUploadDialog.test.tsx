/**
 * The curation feeds' dialog: test, confirm, and what each state says.
 *
 * What is asserted here is what the SCREEN promises, not what the parser does. Four claims
 * carry most of the weight:
 *
 * 1. Choosing a file runs NOTHING. Test reads it; Confirm queues the write. The old dialog
 *    previewed on drop, which is the behaviour the captain asked us to remove.
 * 2. Confirm QUEUES: `notifyImportQueued()` so the upload drawer follows the job, the dialog
 *    closes, and no counts are claimed - the write happens on the worker.
 * 3. A file that could not be read says WHY, and does not offer to be queued.
 * 4. The problems are NAMED, not only counted - the unmatched item codes and the sales
 *    orders we have not received yet are the lists somebody acts on.
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

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const notifyImportQueued = vi.fn();
vi.mock('@/components/upload-activity/useImportJobDrawer', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued }),
}));

const previewPurchaseHistory = vi.fn();
const applyPurchaseHistory = vi.fn();
const previewOrderInquiry = vi.fn();
const applyOrderInquiry = vi.fn();
const testPurchaseHistory = vi.fn();
const testOrderInquiry = vi.fn();
vi.mock('../services/purchaseHistoryService', () => ({
  previewPurchaseHistory: (...a: unknown[]) => previewPurchaseHistory(...a),
  applyPurchaseHistory: (...a: unknown[]) => applyPurchaseHistory(...a),
  previewOrderInquiry: (...a: unknown[]) => previewOrderInquiry(...a),
  applyOrderInquiry: (...a: unknown[]) => applyOrderInquiry(...a),
  testPurchaseHistory: (...a: unknown[]) => testPurchaseHistory(...a),
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

import { HistoryUploadDialog } from './HistoryUploadDialog';
import type { UploadTestResult } from './UploadTestVerdict';
import type {
  OrderInquiryPreview,
  PurchaseHistoryPreview,
} from '../services/purchaseHistoryService';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';

// ── fixtures ────────────────────────────────────────────────────────────────
// Distinct numbers throughout, so a `getByText` on one figure can never match another.

const QUEUED: ImportQueuedResult = {
  message: 'Purchase history upload queued.',
  job_id: 'job-hist-1',
  id: 'row-1',
};

function historyPreview(over: Partial<PurchaseHistoryPreview> = {}): PurchaseHistoryPreview {
  return {
    ok: true,
    problems: [],
    orders: 1586,
    orders_new: 1500,
    orders_existing: 86,
    lines: 13458,
    charge_lines: 534,
    unmatched_items: 2,
    unmatched_item_codes: ['GHOSTCODE1', 'GHOSTCODE2'],
    so_claims: 43,
    date_from: '2020-01-02',
    date_to: '2020-12-30',
    ...over,
  };
}


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

function file(name = 'book.xls'): File {
  return new File(['x'], name, { type: XLSX });
}

function dropzone(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

/** Pick a file. Runs nothing - that is the point of the change. */
async function pick(name = 'book.xls') {
  fireEvent.change(dropzone(), { target: { files: [file(name)] } });
  await waitFor(() => expect(testButton()).toBeEnabled());
}

/** Pick a file AND press Test, which is what every assertion about the summary needs. */
async function choose(name = 'book.xls') {
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
    summary: { total_rows: 13458, would_create: 1586, would_update: 0, error_count: 0 },
    ...over,
  };
}

function testButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^Test$/i }) as HTMLButtonElement;
}

function renderDialog(
  kind: 'purchase-history' | 'order-inquiry',
  onQueued = vi.fn(),
  onOpenChange = vi.fn(),
) {
  render(
    <HistoryUploadDialog open kind={kind} onOpenChange={onOpenChange} onQueued={onQueued} />,
  );
  return { onQueued, onOpenChange };
}

beforeEach(() => {
  previewPurchaseHistory.mockReset().mockResolvedValue(historyPreview());
  applyPurchaseHistory.mockReset().mockResolvedValue(QUEUED);
  previewOrderInquiry.mockReset().mockResolvedValue(inquiryPreview());
  applyOrderInquiry.mockReset().mockResolvedValue(QUEUED);
  notifyImportQueued.mockReset();
  push.mockReset();
  getOutstandingUploadConfig
    .mockReset()
    .mockResolvedValue({ allowed_extensions: ['.xlsx', '.xlsm', '.xls'] });
  testPurchaseHistory.mockReset().mockResolvedValue(verdict());
  testOrderInquiry.mockReset().mockResolvedValue(verdict());
});

// ── 5. the Test function, which every other importer in this system has ─────

describe('HistoryUploadDialog - Test', () => {
  it('is offered once a file is chosen, and writes nothing', async () => {
    renderDialog('purchase-history');
    expect(testButton()).toBeDisabled();

    await pick();
    fireEvent.click(testButton());

    await waitFor(() => expect(testPurchaseHistory).toHaveBeenCalledTimes(1));
    // Both reads on one press: the rich preview AND the standard verdict.
    expect(previewPurchaseHistory).toHaveBeenCalledTimes(1);
    expect(applyPurchaseHistory).not.toHaveBeenCalled();
  });

  it('shows the green verdict when there is nothing to fix', async () => {
    renderDialog('purchase-history');
    await choose();

    expect(await screen.findByText('No errors')).toBeInTheDocument();
  });

  it('shows errors and warnings separately, because only one of them blocks', async () => {
    testPurchaseHistory.mockResolvedValue(
      verdict({
        valid: false,
        errors: ['No order block found in this file.'],
        warnings: ['2 item codes we do not hold, so those lines are skipped: A, B'],
      }),
    );
    renderDialog('purchase-history');
    await choose();

    expect(await screen.findByText('Errors (1)')).toBeInTheDocument();
    expect(screen.getByText('Warnings (1)')).toBeInTheDocument();
    expect(screen.queryByText('No errors')).toBeNull();
  });

  it('warns on a file that is still perfectly loadable', async () => {
    // The distinction the button exists for: a warning is information, not a refusal.
    testPurchaseHistory.mockResolvedValue(
      verdict({ warnings: ['534 charge lines carry cost but no product'] }),
    );
    renderDialog('purchase-history');
    await choose();

    expect(await screen.findByText('No errors')).toBeInTheDocument();
    expect(screen.getByText('Warnings (1)')).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });

  it('does not force a Test before Confirm', async () => {
    // Testing is a tool, not ceremony - the same rule as the GRN and customer importers.
    renderDialog('purchase-history');
    await pick();

    expect(confirmButton()).toBeEnabled();
    expect(testPurchaseHistory).not.toHaveBeenCalled();
    expect(previewPurchaseHistory).not.toHaveBeenCalled();
  });

  it('drops the verdict when a different file is chosen', async () => {
    // A green tick for the previous file, still on screen above a new one, is how somebody
    // uploads a bad file believing it was tested.
    renderDialog('purchase-history');
    await choose('first.xls');
    expect(await screen.findByText('No errors')).toBeInTheDocument();

    await pick('second.xls');
    await waitFor(() => expect(screen.queryByText('No errors')).toBeNull());
  });
});

// ── 1. nothing is written from a single click ───────────────────────────────

describe('HistoryUploadDialog - test, then upload', () => {
  it('opens with nothing chosen and Confirm disabled', () => {
    renderDialog('purchase-history');

    expect(confirmButton()).toBeDisabled();
    expect(previewPurchaseHistory).not.toHaveBeenCalled();
    expect(applyPurchaseHistory).not.toHaveBeenCalled();
  });

  it('reads NOTHING when a file is chosen', async () => {
    renderDialog('purchase-history');
    await pick();

    await Promise.resolve();
    expect(previewPurchaseHistory).not.toHaveBeenCalled();
    expect(testPurchaseHistory).not.toHaveBeenCalled();
    expect(applyPurchaseHistory).not.toHaveBeenCalled();
  });

  it('reads the file on Test, and Test writes nothing', async () => {
    renderDialog('purchase-history');
    await choose();

    await waitFor(() => expect(previewPurchaseHistory).toHaveBeenCalledTimes(1));
    expect(applyPurchaseHistory).not.toHaveBeenCalled();
    expect(confirmButton()).toBeEnabled();
  });

  it('queues on Confirm: drawer, close, and no counts it cannot have', async () => {
    const { onQueued, onOpenChange } = renderDialog('purchase-history');
    await choose();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyPurchaseHistory).toHaveBeenCalledTimes(1));
    // The drawer is what follows the job; without it the operator is told "queued" and has
    // nowhere to watch it.
    expect(notifyImportQueued).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onQueued).toHaveBeenCalledWith(QUEUED);
    expect(screen.queryByText('Upload applied.')).toBeNull();
  });

  it('surfaces the extracted backend message when queueing is refused', async () => {
    applyPurchaseHistory.mockRejectedValue(
      new Error('Select a single company before uploading this file.'),
    );
    const { onQueued } = renderDialog('purchase-history');
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

describe('HistoryUploadDialog - an unreadable file', () => {
  it('says why, and does not offer to apply it', async () => {
    previewPurchaseHistory.mockResolvedValue(
      historyPreview({ ok: false, problems: ['No order block found in this file.'] }),
    );
    renderDialog('purchase-history');
    await choose();

    expect(
      await screen.findByText('No order block found in this file.'),
    ).toBeInTheDocument();
    await waitFor(() => expect(confirmButton()).toBeDisabled());
  });

  it('surfaces a failed request as an error rather than an empty dialog', async () => {
    /**
     * A failed READ does not disable Confirm. Test is a tool, not a gate, so a file whose
     * Test could not reach the server may still be queued - and the job then reports what
     * the worker made of it. What must not happen is silence.
     */
    previewPurchaseHistory.mockRejectedValue(new Error('Backend is down'));
    renderDialog('purchase-history');
    await choose();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
    expect(applyPurchaseHistory).not.toHaveBeenCalled();
  });
});

// ── 3. purchase history reads as history ────────────────────────────────────

describe('HistoryUploadDialog - purchase history', () => {
  it('states plainly that this feed is never counted as incoming stock', () => {
    // The single most expensive misreading available on this screen: a year of closed 2020
    // orders taken for supply would inflate every position in the system.
    renderDialog('purchase-history');

    expect(screen.getByText(/Never counted as incoming stock/i)).toBeInTheDocument();
  });

  it('shows the book it read, and the period it covers', async () => {
    renderDialog('purchase-history');
    await choose();

    await screen.findByText('Orders');
    expect(within(tile('Orders')).getByText('1,586')).toBeInTheDocument();
    expect(within(tile('Charge lines')).getByText('534')).toBeInTheDocument();
    // Charge lines are real money with no product behind them, so they are counted
    // separately rather than folded into the line total or reported as a problem.
    expect(screen.getByText(/43 orders name a sales order/i)).toBeInTheDocument();
  });

  it('names the item codes it could not match rather than only counting them', async () => {
    renderDialog('purchase-history');
    await choose();

    expect(await screen.findByText('GHOSTCODE1')).toBeInTheDocument();
    expect(screen.getByText('GHOSTCODE2')).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing is created in the product catalogue from an upload/i),
    ).toBeInTheDocument();
  });

  it('never claims what the upload DID - that lands on the job', async () => {
    /**
     * The tiles used to switch from "would" to "did" on the response. The write is on the
     * worker now, so those numbers do not exist when this dialog closes: claiming them would
     * be inventing them. The job page reports them, and the drawer is already pointed at it.
     */
    renderDialog('purchase-history');
    await choose();
    fireEvent.click(confirmButton());

    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
    expect(screen.queryByText('Orders written')).toBeNull();
    expect(screen.queryByText('Lines written')).toBeNull();
  });
});

// ── 4. the order inquiry sheet ──────────────────────────────────────────────

describe('HistoryUploadDialog - order inquiry', () => {
  it('shows the rows, the locations and the purchase-order links', async () => {
    renderDialog('order-inquiry');
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
    renderDialog('order-inquiry');
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
    renderDialog('order-inquiry');
    await choose('book.xlsx');

    expect(
      await screen.findByText(/Sales orders we have not received yet \(15,787\)/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\(200\)/)).toBeNull();
  });

  it('names a location code it does not recognise', async () => {
    renderDialog('order-inquiry');
    await choose('inquiry.xlsx');

    expect(await screen.findByText('BRW-ZZ')).toBeInTheDocument();
  });

  it('leaves the link resolution to the job, which is where it now happens', async () => {
    /**
     * The resolve runs inside the queued job (it must: it is a write). So the pairing this
     * upload completed is reported on the job's result rather than here - the half nothing
     * else would say is still said, just not by a dialog that has already closed.
     */
    renderDialog('order-inquiry');
    await choose('inquiry.xlsx');
    fireEvent.click(confirmButton());

    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
    expect(screen.queryByRole('region', { name: /Order links/i })).toBeNull();
  });
});

describe('HistoryUploadDialog - one delivery, stated on many sheets', () => {
  it('shows the row count AND the number of scheduled deliveries', async () => {
    // The customer's book carries a month tab, a roll-up tab covering that month and dated
    // working snapshots, so 15,797 rows describe 8,272 deliveries. Showing only the smaller
    // figure reads as rows lost; showing only the larger one is the bug we just fixed.
    renderDialog('order-inquiry');
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
    renderDialog('order-inquiry');
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
    renderDialog('order-inquiry');
    await choose('inquiry.xlsx');
    fireEvent.click(confirmButton());

    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
    expect(screen.queryByText(/no longer lists/)).toBeNull();
  });
});
