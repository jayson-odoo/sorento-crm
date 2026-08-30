/**
 * ============================================================================
 * SCM - OutstandingUploadDialog
 * ============================================================================
 * The upload channel for the order book. It lives on the existing planning
 * screen (`app/(protected)/scm/reorder`) as a dialog opened from the toolbar, not
 * as a page of its own - the whole plan is computed from this data, so uploading it
 * is a planning action - and the sales-order list opens the SAME dialog.
 *
 * What is pinned here, and why each one matters:
 *
 *  1. TEST, THEN UPLOAD - and choosing a file does NOTHING. No fetch fires on
 *     drop or pick; Test reads the file; Confirm queues the write. This is the
 *     captain's own complaint ("we supposed to use test just like other import"),
 *     so it is pinned on the fetch call log rather than on what renders.
 *  2. TEST ANSWERS THE STANDARD THREE QUESTIONS, and nothing else: how many rows
 *     were read, how many would import, what fails, what is only a warning. It used
 *     to print a bespoke diff report - a count tile per change kind, sample rows per
 *     kind, scope chips, a planning-change card - and the captain's verdict was that
 *     nobody reads it: "if i click test i just need to know how many succeed, how
 *     many fail, how many warning, like the SPO / product list / delivery order /
 *     GRN uploads". So the verdict is the SHARED `UploadTestVerdict`, and the sample
 *     tables are asserted GONE rather than left to creep back.
 *  3. FAIL vs WARNING is the split that decides whether a file is worth fixing
 *     first. A row the reader could not use, and a row naming a product or warehouse
 *     we do not hold, will not import - those are errors. An ignored column, and an
 *     agent code that cannot classify anything yet, cost the file nothing - warnings.
 *     Neither blocks Confirm: only a header missing required columns does.
 *  4. ok:false + missing_columns DISABLES Confirm and names the columns.
 *  5. Confirm QUEUES: 202 -> `notifyImportQueued()` so the upload drawer opens and
 *     follows the job, the dialog closes, and `onQueued` fires. No counts are shown
 *     afterwards - the write happens on the worker, so there are none to show.
 *  6. The file surface is the SHARED FileDropzone (`@/components/common/FileDropzone`):
 *     a `role="button"` drop-and-click surface wrapping a hidden, aria-labelled
 *     `input[type=file]`. Asserted structurally so a hand-rolled input fails.
 *  7. A WRONG EXTENSION IS REFUSED LOCALLY. `accept=".xlsx,.xlsm"` is this importer's
 *     authoritative format list, so a `.txt` is refused instantly with a message naming
 *     the file and the accepted formats, and is NEVER sent to the server: making the
 *     user wait for a round trip to be told what the extension already said is a worse
 *     answer, and forwarding a file the shared dropzone rejected would make its filter
 *     mean nothing to the next reader. The server still gets the last word on a real
 *     workbook it cannot read (a corrupt .xlsx), which is a different path.
 *  8. THE TITLE DOES NOT SAY "OUTSTANDING" for the sales book: the file carries the
 *     whole book, completed orders included.
 *
 * The service layer is mocked - no network, and the two-step guarantee is asserted
 * on the mock call log.
 * ============================================================================
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

// The drawer bridge: what a queued import hands the watching over to.
const notifyImportQueued = vi.fn();
vi.mock('@/components/upload-activity/useImportJobDrawer', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued }),
}));

const previewOutstandingImport = vi.fn();
const applyOutstandingImport = vi.fn();
// Mocked too, and not optional: the dialog asks the server what it accepts as soon as it
// opens. Leaving it out of the factory makes the import `undefined`, which throws inside the
// effect and fails every test in the file for a reason that has nothing to do with the
// assertion - which is exactly what happened when the config call was added.
const getOutstandingUploadConfig = vi.fn();
vi.mock('../services/outstandingImportService', () => ({
  previewOutstandingImport: (...a: unknown[]) => previewOutstandingImport(...a),
  applyOutstandingImport: (...a: unknown[]) => applyOutstandingImport(...a),
  getOutstandingUploadConfig: (...a: unknown[]) => getOutstandingUploadConfig(...a),
}));

import { toast } from 'sonner';
import { OutstandingUploadDialog, verdictFromPreview } from './OutstandingUploadDialog';
import type { OutstandingPreview } from '../services/outstandingImportService';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';

// ── fixtures ────────────────────────────────────────────────────────────────

const PREVIEW: OutstandingPreview = {
  doc_type: 'outstanding_so',
  ok: true,
  scope_documents: ['SO397450', 'SO397512'],
  counts: {
    added: 4,
    qty_changed: 6,
    date_moved: 9,
    date_and_qty_changed: 2,
    closed: 3,
    unchanged: 412,
  },
  total_rows: 500,
  unmapped_headers: [],
  missing_columns: [],
  row_problems: [],
  resolution_issues: [],
  unmapped_agents: [],
  samples: {
    date_moved: [
      {
        doc_number: 'SO397450',
        item_code: 'SRTWC8613-RL',
        location: 'WH-KL',
        qty_before: 135,
        qty_after: 135,
        date_before: '2026-07-01',
        date_after: '2026-07-15',
        days_moved: 14,
        label: 'Tuju Residence',
      },
    ],
  },
};

const QUEUED: ImportQueuedResult = {
  message: 'Order book upload queued.',
  job_id: 'job-2026-07-16',
  id: 'row-1',
};

function preview(over: Partial<OutstandingPreview> = {}): OutstandingPreview {
  return { ...PREVIEW, ...over };
}

function xlsx(name = 'outstanding-so.xlsx'): File {
  return new File([new Uint8Array(16)], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

/** A file whose extension the importer does not accept. */
function txt(name = 'notes.txt'): File {
  return new File([new Uint8Array(16)], name, { type: 'text/plain' });
}

/** A workbook over the 25 MB ceiling. Sparse - nothing ever reads the bytes. */
function oversized(name = 'enormous.xlsx'): File {
  const file = xlsx(name);
  Object.defineProperty(file, 'size', { value: 26 * 1024 * 1024 });
  return file;
}

// ── harness ─────────────────────────────────────────────────────────────────

function renderDialog(
  over: Partial<React.ComponentProps<typeof OutstandingUploadDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onQueued = vi.fn();
  render(
    <OutstandingUploadDialog
      open
      onOpenChange={onOpenChange}
      kind="sales-orders"
      onQueued={onQueued}
      {...over}
    />,
  );
  return { onOpenChange, onQueued };
}

function testButton(): HTMLElement {
  return screen.getByRole('button', { name: /^Test$/i });
}

/** The hidden input inside the shared FileDropzone. */
function fileInput(): HTMLInputElement {
  return screen.getByLabelText('Sales orders file') as HTMLInputElement;
}

/** The drop-and-click surface the shared FileDropzone renders around that input. */
function dropSurface(): HTMLElement {
  const surface = fileInput().closest('[role="button"]');
  if (!surface) {
    throw new Error(
      'the file input is not wrapped in a role="button" drop surface - use the shared ' +
        '@/components/common/FileDropzone rather than a hand-rolled input',
    );
  }
  return surface as HTMLElement;
}

function confirmButton(): HTMLElement {
  return screen.getByRole('button', { name: /Confirm upload/i });
}

/**
 * The dialog's own failure banner, told apart from the Test verdict's alerts.
 *
 * Both are `role="alert"` now that the verdict is the shared one, so a bare
 * `getByRole('alert')` would happily match "No errors" and pass a test about a refusal.
 */
function failureBanner(): HTMLElement | null {
  const banners = screen.queryAllByRole('alert');
  return (
    banners.find((el) => !el.closest('[data-slot="upload-test-verdict"]')) ?? null
  );
}

async function findFailureBanner(): Promise<HTMLElement> {
  await waitFor(() => expect(failureBanner()).not.toBeNull());
  return failureBanner() as HTMLElement;
}

/** The whole verdict panel, whatever it is currently saying. */
function verdict(): HTMLElement {
  const el = document.querySelector('[data-slot="upload-test-verdict"]');
  if (!el) throw new Error('the Test verdict is not on screen');
  return el as HTMLElement;
}

/** Pick a file. Deliberately does NOT read it - that is what Test is for. */
function pickFile(file = xlsx()) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
  return file;
}

/** Pick a file AND press Test, which is what every assertion about the verdict needs. */
async function chooseFile(file = xlsx()) {
  pickFile(file);
  fireEvent.click(testButton());
  await waitFor(() => expect(previewOutstandingImport).toHaveBeenCalled());
  return file;
}

beforeEach(() => {
  previewOutstandingImport.mockReset().mockResolvedValue(preview());
  applyOutstandingImport.mockReset().mockResolvedValue(QUEUED);
  notifyImportQueued.mockReset();
  push.mockReset();
  getOutstandingUploadConfig
    .mockReset()
    .mockResolvedValue({ allowed_extensions: ['.xlsx', '.xlsm', '.xls'] });
});

// ── 1. empty state ──────────────────────────────────────────────────────────

describe('OutstandingUploadDialog - empty state', () => {
  it('opens on the drop surface with nothing chosen and Confirm disabled', () => {
    renderDialog();

    expect(screen.getByRole('heading', { name: /Upload sales orders/i })).toBeInTheDocument();
    expect(dropSurface()).toBeInTheDocument();
    expect(fileInput().accept).toContain('.xlsx');
    expect(confirmButton()).toBeDisabled();
    expect(testButton()).toBeDisabled();
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('never calls the sales book "outstanding" - the file carries all of it', () => {
    renderDialog();
    expect(screen.queryByText(/outstanding/i)).toBeNull();
  });

  it('renders nothing when closed', () => {
    renderDialog({ open: false });
    expect(screen.queryByRole('heading', { name: /Upload sales orders/i })).toBeNull();
  });
});

// ── 2. two-step flow ────────────────────────────────────────────────────────

describe('OutstandingUploadDialog - test, then upload', () => {
  it('reads NOTHING when a file is picked: no request until Test is pressed', async () => {
    renderDialog();
    pickFile();

    // Deliberately given time to fire. `choose` calls no fetch synchronously, so an
    // immediate assertion proves only that nothing happened in that tick - it would still
    // pass against a dialog that kicked the preview off from an effect or a promise chain,
    // which is a real way to reintroduce read-on-drop. Flushing a microtask first is what
    // makes the claim "no request AT ALL" rather than "no request yet".
    await Promise.resolve();
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
    expect(testButton()).toBeEnabled();
  });

  it('reads NOTHING when a file is DROPPED either', async () => {
    renderDialog();
    const file = xlsx('dragged.xlsx');

    fireEvent.drop(dropSurface(), { dataTransfer: { files: [file], types: ['Files'] } });

    await waitFor(() => expect(testButton()).toBeEnabled());
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('reads the file on Test, and Test writes nothing', async () => {
    renderDialog();
    const file = await chooseFile();

    expect(previewOutstandingImport).toHaveBeenCalledTimes(1);
    expect(previewOutstandingImport).toHaveBeenCalledWith('sales-orders', file);
    // The whole point of the split: Test must not touch apply.
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('sends the purchase-orders kind when opened for the purchase order book', async () => {
    renderDialog({ kind: 'purchase-orders' });
    expect(
      screen.getByRole('heading', { name: /Upload purchase orders/i }),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByLabelText('Purchase orders file') as HTMLInputElement,
      { target: { files: [xlsx('outstanding-po.xlsx')] } },
    );
    fireEvent.click(testButton());

    await waitFor(() =>
      expect(previewOutstandingImport).toHaveBeenCalledWith('purchase-orders', expect.any(File)),
    );
  });
});

// ── 3. loading state ────────────────────────────────────────────────────────

describe('OutstandingUploadDialog - loading', () => {
  it('shows the reading-the-file state and keeps Confirm disabled while the preview is in flight', async () => {
    let release!: (p: OutstandingPreview) => void;
    previewOutstandingImport.mockReturnValue(
      new Promise<OutstandingPreview>((resolve) => {
        release = resolve;
      }),
    );
    renderDialog();

    pickFile();
    fireEvent.click(testButton());

    const row = () =>
      document.querySelector('[data-slot="upload-reading-indicator"]') as HTMLElement;

    expect(await screen.findByText(/Reading the file/i)).toBeInTheDocument();
    expect(row()).not.toHaveClass('invisible');
    expect(confirmButton()).toBeDisabled();

    release(preview());
    // Hidden, not unmounted: the row holds its height so the centred dialog does not jump
    // when the read ends. See `UploadReadingIndicator`.
    await waitFor(() => expect(row()).toHaveClass('invisible'));
  });
});

// ── 4. the verdict: how many read, how many import, what fails ──────────────

describe('OutstandingUploadDialog - the Test verdict', () => {
  it('says the file is clean, and how many rows it read, when nothing is wrong', async () => {
    renderDialog();
    await chooseFile();

    const panel = await screen.findByText(/No errors/i);
    expect(panel).toBeInTheDocument();
    expect(verdict()).toHaveTextContent('Rows: 500');
    expect(verdict()).toHaveTextContent('Would import: 500');
    expect(confirmButton()).toBeEnabled();
  });

  it('counts the rows the import would SKIP and names each one, as a warning', async () => {
    // A row the import merely leaves out does not make the file unusable, so it is amber,
    // not red. Reported in red, a file that imports 498 of its 500 rows perfectly read as
    // "this upload failed", and the panel that cries wolf is the panel nobody reads.
    previewOutstandingImport.mockResolvedValue(
      preview({
        row_problems: [{ row_number: 1087, reason: 'missing item_code', value: 'SO349557' }],
        resolution_issues: [
          {
            row_number: 2,
            field: 'stock_location',
            value: 'WH-ZZ',
            reason: 'no warehouse with this code',
          },
        ],
      }),
    );
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Warnings \(2\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/Errors \(/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Row 1087: missing item_code \(SO349557\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/Row 2: stock_location: no warehouse with this code \(WH-ZZ\)/),
    ).toBeInTheDocument();
    // 500 read, 2 of them left out - and the file still says "No errors".
    expect(verdict()).toHaveTextContent('Would import: 498');
    expect(verdict()).toHaveTextContent('Skipped: 2');
    expect(screen.getByText(/No errors/i)).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });

  it('scrolls a long warning list instead of pushing the buttons off the dialog', async () => {
    // Radix `ScrollArea` renders its own viewport inside the element the `max-h` is on, and
    // that viewport does not inherit it - so the list grew to whatever height it liked.
    previewOutstandingImport.mockResolvedValue(
      preview({
        row_problems: Array.from({ length: 40 }, (_, i) => ({
          row_number: i + 1,
          reason: 'missing item_code',
          value: '',
        })),
      }),
    );
    renderDialog();
    await chooseFile();

    const list = (await screen.findByText(/Row 1: missing item_code/)).closest('ul');
    const box = list?.parentElement;
    expect(box?.className).toContain('max-h-[220px]');
    expect(box?.className).toContain('overflow-y-auto');
  });

  it('keeps the things that cost the file nothing as warnings, not failures', async () => {
    previewOutstandingImport.mockResolvedValue(
      preview({
        unmapped_headers: ['Salesman'],
        unmapped_agents: [
          {
            code: 'ACT',
            is_new: true,
            reason: 'new agent, unclassified: this upload is the first thing to name it',
          },
        ],
      }),
    );
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Warnings \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Agent ACT: new agent, unclassified/)).toBeInTheDocument();
    expect(screen.getByText(/Column not recognised: Salesman/)).toBeInTheDocument();
    // Nothing failed, so the file still reads as clean and every row still imports.
    expect(screen.getByText(/No errors/i)).toBeInTheDocument();
    expect(verdict()).toHaveTextContent('Would import: 500');
    expect(confirmButton()).toBeEnabled();
  });

  it('shows no bespoke diff report at all - no count tiles, no sample rows, no scope chips', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText(/No errors/i);
    expect(document.querySelector('[data-slot="count-tile"]')).toBeNull();
    expect(screen.queryByText(/Date moved \(showing/i)).toBeNull();
    expect(screen.queryByRole('region', { name: /Scope/i })).toBeNull();
    expect(screen.queryByText(/Orders not in this file are untouched/i)).toBeNull();
    expect(screen.queryByText('SRTWC8613-RL')).toBeNull();
  });

  it('says nothing would change, and STILL allows Confirm, when only unchanged rows are found', async () => {
    previewOutstandingImport.mockResolvedValue(
      preview({
        counts: {
          added: 0,
          qty_changed: 0,
          date_moved: 0,
          date_and_qty_changed: 0,
          closed: 0,
          unchanged: 412,
        },
        samples: {},
      }),
    );
    renderDialog();
    await chooseFile();

    // The note stays: it is the one thing the standard verdict cannot say. What it no
    // longer does is decide - the diff answers for quantities and dates only, so a book
    // that moves neither still carries money, units and closures worth writing, and a
    // greyed Confirm over a readable file reads as a broken dialog.
    expect(await screen.findByText(/Nothing would change/i)).toBeInTheDocument();
    expect(confirmButton()).toBeEnabled();
  });
});

// ── 4a. the shipping-order half of a purchase book ──────────────────────────
// The prod defect: the verdict printed "721 rows are shipping orders (SPO)" and, directly
// under it, "Nothing would change - every line already matches what we hold". The sentence
// read the PURCHASE-order diff only, so a book whose entire content was shipping orders
// claimed to change nothing while it filed 721 lines.

const NO_PO_CHANGES = {
  added: 0,
  qty_changed: 0,
  date_moved: 0,
  date_and_qty_changed: 0,
  closed: 0,
  unchanged: 0,
};

describe('OutstandingUploadDialog - the shipping orders in a purchase book', () => {
  it('states what the shipping-order lines would do, in one line', async () => {
    previewOutstandingImport.mockResolvedValue(
      preview({
        counts: { ...NO_PO_CHANGES, unchanged: 12 },
        samples: {},
        shipping_order_rows: 9,
        spo_documents: 2,
        spo_lines: 9,
        spo_new: 4,
        spo_changed: 2,
        spo_unchanged: 3,
        spo_closed: 5,
        spo_unknown_locations: 1,
      }),
    );
    renderDialog();
    await chooseFile();

    expect(
      await screen.findByText(
        /Shipping orders: 2 documents, 4 new, 2 changed, 3 unchanged, 5 would close, 1 with no warehouse/i,
      ),
    ).toBeInTheDocument();
  });

  it('says nothing about shipping orders when the book carries none', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText(/No errors/i);
    expect(screen.queryByText(/Shipping orders:/i)).toBeNull();
  });

  it('never claims nothing would change while it files a shipping-order line', async () => {
    previewOutstandingImport.mockResolvedValue(
      preview({
        counts: { ...NO_PO_CHANGES, unchanged: 12 },
        samples: {},
        shipping_order_rows: 721,
        spo_documents: 30,
        spo_lines: 721,
        spo_new: 721,
        spo_changed: 0,
        spo_unchanged: 0,
        spo_closed: 0,
        spo_unknown_locations: 0,
      }),
    );
    renderDialog();
    await chooseFile();

    await screen.findByText(/Shipping orders:/i);
    expect(screen.queryByText(/Nothing would change/i)).toBeNull();
  });

  it('still says nothing would change when BOTH halves already match what we hold', async () => {
    previewOutstandingImport.mockResolvedValue(
      preview({
        counts: { ...NO_PO_CHANGES, unchanged: 12 },
        samples: {},
        shipping_order_rows: 721,
        spo_documents: 30,
        spo_lines: 721,
        spo_new: 0,
        spo_changed: 0,
        spo_unchanged: 721,
        spo_closed: 0,
        spo_unknown_locations: 0,
      }),
    );
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Nothing would change/i)).toBeInTheDocument();
  });
});

// ── 4b. the derivation itself ───────────────────────────────────────────────
// The verdict is computed in the browser off the preview rather than asked for a second
// time, so the mapping is pinned directly: it is the one piece of logic in this file.

describe('verdictFromPreview', () => {
  it('is invalid only when the FILE cannot be used', () => {
    // The line the whole panel turns on: an error means the file is unusable (a header with
    // no required column), and nothing else qualifies. A row the import skips is a warning -
    // it costs that row, not the upload.
    expect(verdictFromPreview(preview()).valid).toBe(true);
    expect(
      verdictFromPreview(preview({ unmapped_headers: ['Salesman'] })).valid,
    ).toBe(true);
    expect(
      verdictFromPreview(
        preview({ row_problems: [{ row_number: 4, reason: 'no quantity', value: '' }] }),
      ).valid,
    ).toBe(true);
    expect(
      verdictFromPreview(preview({ ok: false, missing_columns: ['qty_outstanding'] })).valid,
    ).toBe(false);
  });

  it('is invalid, with an ERROR naming the orders, when the class cannot be decided', () => {
    // QP1: an order nothing can classify refuses the whole FILE, so it is an error and not
    // a skipped row - the rest of the book does not go in without it, and a yellow warning
    // beside a blocked upload is the panel lying about what happens next.
    const result = verdictFromPreview(
      preview({
        ok: false,
        unclassified_documents: ['SO394803', 'SO411133'],
        row_problems: [
          { row_number: 4, reason: 'SO394803 states no order type', value: 'SO394803' },
        ],
      }),
    );

    expect(result.valid).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0]).toContain('2 sales orders carry no demand class');
    expect(result.errors[0]).toContain('SO394803, SO411133');
    expect(result.summary?.would_apply).toBe(0);
  });

  it('names ten refused orders and counts the rest, rather than printing the whole book', () => {
    const many = Array.from({ length: 13 }, (_, i) => `SO${i + 1}`);

    const result = verdictFromPreview(preview({ ok: false, unclassified_documents: many }));

    expect(result.errors[0]).toContain('SO1, SO2');
    expect(result.errors[0]).toContain('and 3 more');
    expect(result.errors[0]).not.toContain('SO13');
  });

  it('reports a skipped row as a warning, and counts it apart from the file-level notes', () => {
    const result = verdictFromPreview(
      preview({
        row_problems: [{ row_number: 4, reason: 'no quantity', value: '' }],
        resolution_issues: [
          { row_number: 9, field: 'item_code', value: 'ZZZ', reason: 'no product' },
        ],
        unmapped_headers: ['Salesman'],
      }),
    );

    expect(result.errors).toEqual([]);
    expect(result.warnings).toEqual([
      'Row 4: no quantity',
      'Row 9: item_code: no product (ZZZ)',
      'Column not recognised: Salesman',
    ]);
    // `skipped_rows` counts ROWS. The unrecognised column is a warning and skips nothing,
    // so folding it into the same figure would overstate what the import leaves out.
    expect(result.summary).toMatchObject({
      total_rows: 500,
      would_apply: 498,
      skipped_rows: 2,
      warning_count: 3,
      error_count: 0,
    });
  });

  it('prints the file-level notices the backend states, and keeps them out of "would import"', () => {
    // A purchase book carries shipping orders too, and this channel does not write them.
    // The count is its own field because "would import" is a count: a book that is half SPO
    // would otherwise promise to import twice what it will. The sentence itself is the
    // backend's, printed as it was written rather than re-worded here.
    const result = verdictFromPreview(
      preview({
        total_rows: 500,
        shipping_order_rows: 120,
        warnings: ['120 rows are shipping orders (SPO), which this book does not carry; ' +
          'they are left out'],
      }),
    );

    expect(result.valid).toBe(true);
    expect(result.warnings).toContain(
      '120 rows are shipping orders (SPO), which this book does not carry; they are left out',
    );
    expect(result.summary).toMatchObject({
      total_rows: 500,
      would_apply: 380,
      skipped_rows: 0,
      warning_count: 1,
    });
  });

  it('reads a header that is missing required columns as an error per column', () => {
    const result = verdictFromPreview(
      preview({
        ok: false,
        total_rows: 0,
        counts: {},
        missing_columns: ['required_date', 'qty_outstanding'],
        samples: {},
      }),
    );
    expect(result.valid).toBe(false);
    expect(result.errors).toEqual([
      'Missing required column: required_date',
      'Missing required column: qty_outstanding',
    ]);
    expect(result.summary).toMatchObject({ total_rows: 0, would_apply: 0, error_count: 2 });
  });
});

// ── 5. unusable file: ok:false + missing_columns ────────────────────────────

describe('OutstandingUploadDialog - unreadable header (ok:false)', () => {
  const UNUSABLE = preview({
    ok: false,
    scope_documents: [],
    counts: {},
    total_rows: 0,
    missing_columns: ['required_date', 'qty_outstanding'],
    samples: {},
  });

  it('disables Confirm and names every missing column', async () => {
    previewOutstandingImport.mockResolvedValue(UNUSABLE);
    renderDialog();
    await chooseFile();

    expect(
      await screen.findByText(/Missing required column: required_date/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Missing required column: qty_outstanding/)).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
  });

  it('never claims a row would import from a file it could not read', async () => {
    previewOutstandingImport.mockResolvedValue(UNUSABLE);
    renderDialog();
    await chooseFile();

    await screen.findByText(/Missing required column: required_date/);
    expect(verdict()).toHaveTextContent('Would import: 0');
    expect(screen.queryByText(/No errors/i)).toBeNull();
  });
});

// ── 6. refused locally: wrong extension, or over the ceiling ────────────────

describe('OutstandingUploadDialog - the wrong kind of file is refused here', () => {
  it('refuses a non-workbook on the spot and never sends it to the server', async () => {
    renderDialog();

    fireEvent.change(fileInput(), { target: { files: [txt('notes.txt')] } });

    const alert = await findFailureBanner();
    // Names the file AND the formats that would have worked: "invalid file" alone
    // leaves the user guessing which of the two facts is the problem.
    expect(alert).toHaveTextContent('notes.txt');
    expect(alert).toHaveTextContent('.xlsx or .xlsm');
    // `accept` is authoritative for this importer, so nothing is uploaded to be told
    // what the extension already said.
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
    expect(confirmButton()).toBeDisabled();
  });

  it('refuses a workbook over the size ceiling the same way', async () => {
    renderDialog();

    fireEvent.change(fileInput(), { target: { files: [oversized()] } });

    const alert = await findFailureBanner();
    expect(alert).toHaveTextContent('enormous.xlsx');
    expect(alert).toHaveTextContent('25 MB');
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(confirmButton()).toBeDisabled();
  });

  it('clears the refusal as soon as a usable workbook is chosen', async () => {
    renderDialog();
    fireEvent.change(fileInput(), { target: { files: [txt('notes.txt')] } });
    await findFailureBanner();

    pickFile();

    await waitFor(() => expect(failureBanner()).toBeNull());
    expect(confirmButton()).toBeEnabled();
  });
});

// ── 7. the server still gets the last word on a real workbook ───────────────
// A `.xlsx` that is corrupt, empty or otherwise unreadable is a SERVER answer, not
// something the extension could have told us. That path must keep surfacing the
// extracted backend message - it is what the local refusal above does NOT replace.

describe('OutstandingUploadDialog - preview error from the server', () => {
  it('surfaces the extracted backend message and leaves Confirm disabled', async () => {
    previewOutstandingImport.mockRejectedValue(
      new Error('Could not read the workbook: the file is corrupt.'),
    );
    renderDialog();
    await chooseFile(xlsx('outstanding-so.xlsx'));

    const alert = await findFailureBanner();
    expect(alert).toHaveTextContent('Could not read the workbook: the file is corrupt.');
    // Nothing was written by the Test itself. Confirm is not blocked on a failed READ -
    // the same file may still queue, and the job reports what the worker makes of it -
    // which is exactly how the GRN and customer importers behave.
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('is recoverable: a good workbook after the failure clears the alert and enables Confirm', async () => {
    previewOutstandingImport.mockRejectedValueOnce(
      new Error('Could not read the workbook: the file is corrupt.'),
    );
    renderDialog();
    await chooseFile(xlsx('corrupt.xlsx'));
    await findFailureBanner();

    // The next Test takes the default resolved preview from beforeEach.
    await chooseFile(xlsx('outstanding-so.xlsx'));

    await screen.findByText(/No errors/i);
    expect(failureBanner()).toBeNull();
    expect(confirmButton()).toBeEnabled();
  });
});

// ── 8. confirm -> apply ─────────────────────────────────────────────────────

describe('OutstandingUploadDialog - confirm queues the upload', () => {
  it('queues the SAME file that was tested, exactly once', async () => {
    renderDialog();
    const file = await chooseFile();

    await screen.findByText(/No errors/i);
    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyOutstandingImport).toHaveBeenCalledTimes(1));
    expect(applyOutstandingImport).toHaveBeenCalledWith('sales-orders', file);
    // Test is not re-run on confirm.
    expect(previewOutstandingImport).toHaveBeenCalledTimes(1);
  });

  it('queues a file that was never tested - Test is a tool, not a gate', async () => {
    renderDialog();
    const file = pickFile();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyOutstandingImport).toHaveBeenCalledWith('sales-orders', file));
    expect(previewOutstandingImport).not.toHaveBeenCalled();
  });

  it('opens the upload drawer, closes itself and notifies the page', async () => {
    const { onOpenChange, onQueued } = renderDialog();
    await chooseFile();

    await screen.findByText(/No errors/i);
    fireEvent.click(confirmButton());

    // The drawer is what follows the job to completion; without this the operator is
    // told "queued" and has nowhere to watch it.
    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalledTimes(1));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onQueued).toHaveBeenCalledWith(QUEUED);
    expect(toast.success).toHaveBeenCalledWith(
      expect.stringMatching(/queued/i),
      expect.objectContaining({ action: expect.objectContaining({ label: 'View job' }) }),
    );
  });

  it('never claims counts it cannot have - the write happens on the worker', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText(/No errors/i);
    fireEvent.click(confirmButton());

    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
    expect(screen.queryByText(/Upload applied/i)).toBeNull();
  });

  it('disables Confirm while the queue call is in flight so it cannot be double-submitted', async () => {
    let release!: (r: ImportQueuedResult) => void;
    applyOutstandingImport.mockReturnValue(
      new Promise<ImportQueuedResult>((resolve) => {
        release = resolve;
      }),
    );
    renderDialog();
    await chooseFile();

    await screen.findByText(/No errors/i);
    fireEvent.click(confirmButton());

    await waitFor(() => expect(confirmButton()).toBeDisabled());
    fireEvent.click(confirmButton());
    expect(applyOutstandingImport).toHaveBeenCalledTimes(1);

    release(QUEUED);
    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalled());
  });

  it('surfaces the extracted backend message when queueing fails, and allows a retry', async () => {
    applyOutstandingImport.mockRejectedValue(
      new Error('Select a single company before uploading the order book.'),
    );
    const { onQueued } = renderDialog();
    await chooseFile();

    await screen.findByText(/No errors/i);
    fireEvent.click(confirmButton());

    const alert = await findFailureBanner();
    expect(alert).toHaveTextContent('Select a single company before uploading the order book.');
    expect(onQueued).not.toHaveBeenCalled();
    expect(notifyImportQueued).not.toHaveBeenCalled();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
  });
});
