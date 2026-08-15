/**
 * ============================================================================
 * SCM - OutstandingUploadDialog (TDD: these tests are written BEFORE the
 * component, and define its contract).
 * ============================================================================
 * The upload channel for the open order book. It lives on the existing planning
 * screen (`app/(protected)/scm/reorder`) as a dialog opened from the toolbar, not
 * as a page of its own - the whole plan is computed from this data, so uploading it
 * is a planning action.
 *
 * What is pinned here, and why each one matters:
 *
 *  1. TEST, THEN UPLOAD - and choosing a file does NOTHING. No fetch fires on
 *     drop or pick; Test reads the file; Confirm queues the write. This is the
 *     captain's own complaint ("we supposed to use test just like other import"),
 *     so it is pinned on the fetch call log rather than on what renders.
 *  2. COUNTS FOR EVERY CHANGE KIND, INCLUDING `unchanged`. A diff that shows only
 *     changes is indistinguishable from one that silently failed to read the file.
 *  3. SAMPLE ROWS AS EVIDENCE. A date_moved sample shows the before date, the after
 *     date and how many days it moved - numbers alone are not checkable by eye.
 *  4. SCOPE IS SHOWN. The document numbers the file covers, plus the explicit
 *     statement that orders not in the file are untouched (the single-project
 *     export must not read as "everything else was delivered").
 *  5. PROBLEMS ARE REPORTED, NOT SWALLOWED - unmapped headers, unreadable rows and
 *     unresolvable codes each render with the row number and the offending value,
 *     and none of them blocks a file that is otherwise usable.
 *  6. ok:false + missing_columns DISABLES Confirm and names the columns.
 *  7. Confirm QUEUES: 202 -> `notifyImportQueued()` so the upload drawer opens and
 *     follows the job, the dialog closes, and `onQueued` fires. No counts are shown
 *     afterwards - the write happens on the worker, so there are none to show.
 *  7b. `unmapped_agents` renders as its OWN section, worded as the backend words it
 *     and never mixed into the rejected rows: nothing was skipped, so listing it
 *     among the failures would make a clean file read as a broken one. An empty list
 *     renders no section at all.
 *  8. The file surface is the SHARED FileDropzone (`@/components/common/FileDropzone`):
 *     a `role="button"` drop-and-click surface wrapping a hidden, aria-labelled
 *     `input[type=file]`. Asserted structurally so a hand-rolled input fails.
 *  9. A WRONG EXTENSION IS REFUSED LOCALLY. `accept=".xlsx,.xlsm"` is this importer's
 *     authoritative format list, so a `.txt` is refused instantly with a message naming
 *     the file and the accepted formats, and is NEVER sent to the server: making the
 *     user wait for a round trip to be told what the extension already said is a worse
 *     answer, and forwarding a file the shared dropzone rejected would make its filter
 *     mean nothing to the next reader. The server still gets the last word on a real
 *     workbook it cannot read (a corrupt .xlsx), which is a different path.
 *
 * The service layer is mocked - no network, and the two-step guarantee is asserted
 * on the mock call log.
 * ============================================================================
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
import { OutstandingUploadDialog } from './OutstandingUploadDialog';
import type { OutstandingPreview } from '../services/outstandingImportService';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';

// ── fixtures ────────────────────────────────────────────────────────────────
// Every count is a DISTINCT number so a `getByText` on one can never accidentally
// match another tile.

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
      {
        doc_number: 'SO397512',
        item_code: 'SRTWC9001-WH',
        location: 'WH-JB',
        qty_before: 40,
        qty_after: 40,
        date_before: '2026-08-03',
        date_after: '2026-07-27',
        days_moved: -7,
        label: 'Bayu Damansara',
      },
    ],
    closed: [
      {
        doc_number: 'SO397512',
        item_code: 'SRTWC7700-BK',
        location: 'WH-JB',
        qty_before: 18,
        qty_after: null,
        date_before: '2026-07-09',
        date_after: null,
        days_moved: null,
        label: 'Bayu Damansara',
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
  return screen.getByLabelText('Outstanding orders file') as HTMLInputElement;
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

/** The whole reported line for a row problem, however it is split into spans. */
function problemLine(match: RegExp): HTMLElement {
  const hit = screen.getByText(match);
  return (hit.closest('li') as HTMLElement | null) ?? hit;
}

/** Assert a change-kind count tile shows `value` next to `label`. */
function expectCount(label: string, value: number) {
  const labelEl = screen.getByText(label);
  const tile = labelEl.closest('[data-slot="count-tile"]');
  if (!tile) {
    throw new Error(`"${label}" is not inside a [data-slot="count-tile"] element`);
  }
  expect(tile).toHaveTextContent(String(value));
}

/** Pick a file. Deliberately does NOT read it - that is what Test is for. */
function pickFile(file = xlsx()) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
  return file;
}

/** Pick a file AND press Test, which is what every assertion about the diff needs. */
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

    expect(
      screen.getByRole('heading', { name: /Upload outstanding sales orders/i }),
    ).toBeInTheDocument();
    expect(dropSurface()).toBeInTheDocument();
    expect(fileInput().accept).toContain('.xlsx');
    expect(confirmButton()).toBeDisabled();
    expect(testButton()).toBeDisabled();
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('renders nothing when closed', () => {
    renderDialog({ open: false });
    expect(screen.queryByRole('heading', { name: /Upload outstanding/i })).toBeNull();
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
      screen.getByRole('heading', { name: /Upload outstanding purchase orders/i }),
    ).toBeInTheDocument();

    const file = await chooseFile(xlsx('outstanding-po.xlsx'));
    expect(previewOutstandingImport).toHaveBeenCalledWith('purchase-orders', file);
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

    expect(await screen.findByText(/Reading the file/i)).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();

    release(preview());
    await waitFor(() => expect(screen.queryByText(/Reading the file/i)).toBeNull());
  });
});

// ── 4. the diff: counts for every kind ──────────────────────────────────────

describe('OutstandingUploadDialog - counts for every change kind', () => {
  it('shows every kind INCLUDING unchanged, so a half-read file is visible', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText('Added');
    expectCount('Added', 4);
    expectCount('Quantity changed', 6);
    expectCount('Date moved', 9);
    expectCount('Date and quantity changed', 2);
    expectCount('Closed', 3);
    expectCount('Unchanged', 412);
  });

  it('states how many rows the file carried', async () => {
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/500 rows/i)).toBeInTheDocument();
  });

  it('says nothing would change, and blocks Confirm, when only unchanged rows are found', async () => {
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

    expect(await screen.findByText(/Nothing would change/i)).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
  });
});

// ── 5. sample rows as evidence ──────────────────────────────────────────────

describe('OutstandingUploadDialog - sample rows are evidence, not just numbers', () => {
  it('shows a date_moved sample with the before date, the after date and the days moved', async () => {
    renderDialog();
    await chooseFile();

    // Group heading names the kind and admits it is a sample of the whole.
    expect(await screen.findByText(/Date moved \(showing 2 of 9\)/i)).toBeInTheDocument();

    // Dates render through `formatDateInMalaysia` -> dd/mm/yyyy.
    const pushed = screen.getByRole('row', { name: /SRTWC8613-RL/ });
    expect(within(pushed).getByText('01/07/2026')).toBeInTheDocument();
    expect(within(pushed).getByText('15/07/2026')).toBeInTheDocument();
    expect(within(pushed).getByText(/\+14 days/)).toBeInTheDocument();
    expect(within(pushed).getByText('SO397450')).toBeInTheDocument();

    // A pulled-in date reads as a negative move, not an unsigned one.
    const pulled = screen.getByRole('row', { name: /SRTWC9001-WH/ });
    expect(within(pulled).getByText('03/08/2026')).toBeInTheDocument();
    expect(within(pulled).getByText('27/07/2026')).toBeInTheDocument();
    expect(within(pulled).getByText(/-7 days/)).toBeInTheDocument();
  });

  it('shows a closed sample with its quantity and no after date', async () => {
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Closed \(showing 1 of 3\)/i)).toBeInTheDocument();
    const row = screen.getByRole('row', { name: /SRTWC7700-BK/ });
    expect(within(row).getByText('18')).toBeInTheDocument();
  });

  it('omits a sample group entirely when the backend sent no rows for that kind', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText(/Date moved \(showing 2 of 9\)/i);
    // `added` counted 4 but carried no samples in this payload.
    expect(screen.queryByText(/Added \(showing/i)).toBeNull();
  });
});

// ── 6. scope ────────────────────────────────────────────────────────────────

describe('OutstandingUploadDialog - scope is shown', () => {
  it('lists the documents the file covers and states the rest are untouched', async () => {
    renderDialog();
    await chooseFile();

    const scope = await screen.findByRole('region', { name: /Scope/i });
    expect(within(scope).getByText('SO397450')).toBeInTheDocument();
    expect(within(scope).getByText('SO397512')).toBeInTheDocument();
    expect(scope).toHaveTextContent(/2 documents/i);
    expect(
      screen.getByText(/Orders not in this file are untouched/i),
    ).toBeInTheDocument();
  });
});

// ── 7. problem reporting ────────────────────────────────────────────────────

describe('OutstandingUploadDialog - problems are reported, not swallowed', () => {
  const PROBLEMATIC = preview({
    unmapped_headers: ['Salesman', 'Project Ref'],
    row_problems: [
      { row_number: 42, reason: 'quantity is not a number', value: 'N/A' },
      { row_number: 61, reason: 'no document number', value: '' },
    ],
    resolution_issues: [
      {
        row_number: 87,
        field: 'item_code',
        value: 'SRTWC-XXX',
        reason: 'no product with this code',
      },
      {
        row_number: 91,
        field: 'stock_location',
        value: 'WH-ZZ',
        reason: 'no warehouse with this code',
      },
    ],
  });

  it('names the columns it did not recognise', async () => {
    previewOutstandingImport.mockResolvedValue(PROBLEMATIC);
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Columns we did not recognise/i)).toBeInTheDocument();
    expect(screen.getByText('Salesman')).toBeInTheDocument();
    expect(screen.getByText('Project Ref')).toBeInTheDocument();
  });

  it('reports each unreadable row with its row number, reason and offending value', async () => {
    /**
     * The heading is "Rows that need a look", NOT "N rows skipped". This channel's row list
     * mixes rows the reader dropped with documents that imported perfectly well and only
     * lack an order type, so a skip claim would be wrong for half of it. The shared section
     * only makes that claim when it is handed a real skip count (the customer importer's B3
     * lesson), and this caller deliberately does not have one.
     */
    previewOutstandingImport.mockResolvedValue(PROBLEMATIC);
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Rows that need a look/i)).toBeInTheDocument();
    expect(screen.queryByText(/rows skipped/i)).toBeNull();
    const line = problemLine(/Row 42/);
    expect(line.textContent).toMatch(/quantity is not a number/);
    expect(line.textContent).toMatch(/N\/A/);
    expect(problemLine(/Row 61/).textContent).toMatch(/no document number/);
  });

  it('reports each unresolvable code with its row number, field and offending value', async () => {
    previewOutstandingImport.mockResolvedValue(PROBLEMATIC);
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Rows we could not match/i)).toBeInTheDocument();
    const item = problemLine(/Row 87/);
    expect(item.textContent).toMatch(/item_code/);
    expect(item.textContent).toMatch(/SRTWC-XXX/);
    expect(item.textContent).toMatch(/no product with this code/);

    const warehouse = problemLine(/Row 91/);
    expect(warehouse.textContent).toMatch(/WH-ZZ/);
    expect(warehouse.textContent).toMatch(/no warehouse with this code/);
  });

  it('still lets the user confirm - bad rows do not make a usable file unusable', async () => {
    previewOutstandingImport.mockResolvedValue(PROBLEMATIC);
    renderDialog();
    await chooseFile();

    await screen.findByText(/Rows that need a look/i);
    expect(confirmButton()).toBeEnabled();
  });

  it('renders no problem sections when the file is clean', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText('Added');
    expect(screen.queryByText(/Columns we did not recognise/i)).toBeNull();
    expect(screen.queryByText(/Rows that need a look/i)).toBeNull();
    expect(screen.queryByText(/Rows we could not match/i)).toBeNull();
  });
});

// ── 8. unusable file: ok:false + missing_columns ────────────────────────────

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

    expect(await screen.findByText(/missing required columns/i)).toBeInTheDocument();
    expect(screen.getAllByText(/required_date/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/qty_outstanding/).length).toBeGreaterThan(0);
    expect(confirmButton()).toBeDisabled();
  });

  it('never offers counts or scope for a file it could not read', async () => {
    previewOutstandingImport.mockResolvedValue(UNUSABLE);
    renderDialog();
    await chooseFile();

    await screen.findByText(/missing required columns/i);
    expect(screen.queryByText('Unchanged')).toBeNull();
    expect(screen.queryByText(/Orders not in this file are untouched/i)).toBeNull();
  });
});

// ── 9. refused locally: wrong extension, or over the ceiling ────────────────

describe('OutstandingUploadDialog - the wrong kind of file is refused here', () => {
  it('refuses a non-workbook on the spot and never sends it to the server', async () => {
    renderDialog();

    fireEvent.change(fileInput(), { target: { files: [txt('notes.txt')] } });

    const alert = await screen.findByRole('alert');
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

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('enormous.xlsx');
    expect(alert).toHaveTextContent('25 MB');
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(confirmButton()).toBeDisabled();
  });

  it('clears the refusal as soon as a usable workbook is chosen', async () => {
    renderDialog();
    fireEvent.change(fileInput(), { target: { files: [txt('notes.txt')] } });
    await screen.findByRole('alert');

    pickFile();

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(confirmButton()).toBeEnabled();
  });
});

// ── 10. the server still gets the last word on a real workbook ──────────────
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

    const alert = await screen.findByRole('alert');
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
    await screen.findByRole('alert');

    // The next Test takes the default resolved preview from beforeEach.
    await chooseFile(xlsx('outstanding-so.xlsx'));

    await screen.findByText('Added');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(confirmButton()).toBeEnabled();
  });
});

// ── 11. confirm -> apply ────────────────────────────────────────────────────

describe('OutstandingUploadDialog - confirm queues the upload', () => {
  it('queues the SAME file that was tested, exactly once', async () => {
    renderDialog();
    const file = await chooseFile();

    await screen.findByText('Added');
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

    await screen.findByText('Added');
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

    await screen.findByText('Added');
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

    await screen.findByText('Added');
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

    await screen.findByText('Added');
    fireEvent.click(confirmButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Select a single company before uploading the order book.');
    expect(onQueued).not.toHaveBeenCalled();
    expect(notifyImportQueued).not.toHaveBeenCalled();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
  });
});

// ── 12. the agents this upload would create ─────────────────────────────────
// AC-6.4 / AC-3.3. The backend has returned `unmapped_agents` on both responses since S2
// and no screen read it, so an upload invented master rows the operator was never told
// about. Its own section, never merged into the rejected rows.

describe('OutstandingUploadDialog - agents with no demand class', () => {
  const WITH_AGENTS = preview({
    unmapped_agents: [
      {
        code: 'SEAN III',
        is_new: true,
        reason:
          'new agent, unclassified: this upload is the first thing to name this agent code, ' +
          'so the master row is being created with no demand class',
      },
      {
        code: 'LCL',
        is_new: false,
        reason:
          'this agent carries no demand class, so it cannot classify an order that states ' +
          'nothing else',
      },
    ],
  });

  it('names each agent and says what is wrong with it, in the backend own words', async () => {
    previewOutstandingImport.mockResolvedValue(WITH_AGENTS);
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Agents with no demand class/i)).toBeInTheDocument();
    expect(screen.getByText('SEAN III')).toBeInTheDocument();
    expect(screen.getByText('LCL')).toBeInTheDocument();
    expect(screen.getByText(/new agent, unclassified/i)).toBeInTheDocument();
  });

  it('keeps them OUT of the rejected rows - nothing was skipped', async () => {
    previewOutstandingImport.mockResolvedValue(WITH_AGENTS);
    renderDialog();
    await chooseFile();

    await screen.findByText(/Agents with no demand class/i);
    expect(screen.queryByText(/rows skipped/i)).toBeNull();
    expect(screen.queryByText(/Rows that need a look/i)).toBeNull();
    // A clean file with a new agent is still confirmable.
    expect(confirmButton()).toBeEnabled();
  });

  it('renders no section at all when every agent carries a class', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText('Added');
    expect(screen.queryByText(/Agents with no demand class/i)).toBeNull();
  });
});
