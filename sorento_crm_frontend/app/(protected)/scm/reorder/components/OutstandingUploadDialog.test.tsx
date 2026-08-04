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
 *  1. TWO STEPS, NEVER ONE CLICK. Choosing a file previews; nothing is written
 *     until Confirm. `applyOutstandingImport` must not be called during preview.
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
 *  7. Confirm applies and reports the applied counts; a failure surfaces the
 *     extracted backend message.
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

const previewOutstandingImport = vi.fn();
const applyOutstandingImport = vi.fn();
vi.mock('../services/outstandingImportService', () => ({
  previewOutstandingImport: (...a: unknown[]) => previewOutstandingImport(...a),
  applyOutstandingImport: (...a: unknown[]) => applyOutstandingImport(...a),
}));

import { OutstandingUploadDialog } from './OutstandingUploadDialog';
import type {
  OutstandingApplyResult,
  OutstandingPreview,
} from '../services/outstandingImportService';

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

const APPLY_RESULT: OutstandingApplyResult = {
  ok: true,
  counts: PREVIEW.counts,
  applied: { added: 4, updated: 17, closed: 3, unchanged: 412 },
  scope_documents: ['SO397450', 'SO397512'],
  resolution_issues: [],
  row_problems: [],
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
  const onApplied = vi.fn();
  render(
    <OutstandingUploadDialog
      open
      onOpenChange={onOpenChange}
      kind="sales-orders"
      onApplied={onApplied}
      {...over}
    />,
  );
  return { onOpenChange, onApplied };
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

/** Choose a file through the picker and wait for the preview render to settle. */
async function chooseFile(file = xlsx()) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
  await waitFor(() => expect(previewOutstandingImport).toHaveBeenCalled());
  return file;
}

beforeEach(() => {
  previewOutstandingImport.mockReset().mockResolvedValue(preview());
  applyOutstandingImport.mockReset().mockResolvedValue(APPLY_RESULT);
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
    expect(previewOutstandingImport).not.toHaveBeenCalled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('renders nothing when closed', () => {
    renderDialog({ open: false });
    expect(screen.queryByRole('heading', { name: /Upload outstanding/i })).toBeNull();
  });
});

// ── 2. two-step flow ────────────────────────────────────────────────────────

describe('OutstandingUploadDialog - two steps, never one click', () => {
  it('previews the chosen file and writes NOTHING until the user confirms', async () => {
    renderDialog();
    const file = await chooseFile();

    expect(previewOutstandingImport).toHaveBeenCalledTimes(1);
    expect(previewOutstandingImport).toHaveBeenCalledWith('sales-orders', file);
    // The whole point of the split: preview must not touch apply.
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('previews a dropped file too, not only a picked one', async () => {
    renderDialog();
    const file = xlsx('dragged.xlsx');

    fireEvent.drop(dropSurface(), { dataTransfer: { files: [file], types: ['Files'] } });

    await waitFor(() => expect(previewOutstandingImport).toHaveBeenCalledWith('sales-orders', file));
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

    fireEvent.change(fileInput(), { target: { files: [xlsx()] } });

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
    previewOutstandingImport.mockResolvedValue(PROBLEMATIC);
    renderDialog();
    await chooseFile();

    expect(await screen.findByText(/Rows we could not read/i)).toBeInTheDocument();
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

    await screen.findByText(/Rows we could not read/i);
    expect(confirmButton()).toBeEnabled();
  });

  it('renders no problem sections when the file is clean', async () => {
    renderDialog();
    await chooseFile();

    await screen.findByText('Added');
    expect(screen.queryByText(/Columns we did not recognise/i)).toBeNull();
    expect(screen.queryByText(/Rows we could not read/i)).toBeNull();
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

    await chooseFile();

    await screen.findByText('Added');
    expect(screen.queryByRole('alert')).toBeNull();
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
    // There is no diff to confirm against, so nothing can be written.
    expect(confirmButton()).toBeDisabled();
    expect(applyOutstandingImport).not.toHaveBeenCalled();
  });

  it('is recoverable: a good workbook after the failure clears the alert and enables Confirm', async () => {
    previewOutstandingImport.mockRejectedValueOnce(
      new Error('Could not read the workbook: the file is corrupt.'),
    );
    renderDialog();
    await chooseFile(xlsx('corrupt.xlsx'));
    await screen.findByRole('alert');

    // The next pick takes the default resolved preview from beforeEach.
    fireEvent.change(fileInput(), { target: { files: [xlsx('outstanding-so.xlsx')] } });

    await screen.findByText('Added');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(confirmButton()).toBeEnabled();
  });
});

// ── 11. confirm -> apply ────────────────────────────────────────────────────

describe('OutstandingUploadDialog - confirm applies the upload', () => {
  it('applies the SAME file the preview was taken from, exactly once', async () => {
    renderDialog();
    const file = await chooseFile();

    await screen.findByText('Added');
    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyOutstandingImport).toHaveBeenCalledTimes(1));
    expect(applyOutstandingImport).toHaveBeenCalledWith('sales-orders', file);
    // Preview is not re-run on confirm.
    expect(previewOutstandingImport).toHaveBeenCalledTimes(1);
  });

  it('disables Confirm while the apply is in flight so it cannot be double-submitted', async () => {
    let release!: (r: OutstandingApplyResult) => void;
    applyOutstandingImport.mockReturnValue(
      new Promise<OutstandingApplyResult>((resolve) => {
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

    release(APPLY_RESULT);
    await screen.findByText(/Upload applied/i);
  });

  it('replaces the preview with the APPLIED counts and notifies the page', async () => {
    const { onApplied } = renderDialog();
    await chooseFile();

    await screen.findByText('Added');
    fireEvent.click(confirmButton());

    expect(await screen.findByText(/Upload applied/i)).toBeInTheDocument();
    expectCount('Added', 4);
    expectCount('Updated', 17);
    expectCount('Closed', 3);
    expectCount('Unchanged', 412);
    // The preview is gone - there is exactly one set of numbers on screen.
    expect(screen.queryByText(/Orders not in this file are untouched/i)).toBeNull();
    expect(onApplied).toHaveBeenCalledWith(APPLY_RESULT);
  });

  it('surfaces the extracted backend message when apply fails, and allows a retry', async () => {
    applyOutstandingImport.mockRejectedValue(
      new Error('The file is missing required columns: required_date'),
    );
    const { onApplied } = renderDialog();
    await chooseFile();

    await screen.findByText('Added');
    fireEvent.click(confirmButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The file is missing required columns: required_date');
    expect(onApplied).not.toHaveBeenCalled();
    await waitFor(() => expect(confirmButton()).toBeEnabled());
  });
});
