/**
 * S7a - the stock-list upload dialog.
 *
 * The two-step flow itself is `useTwoStepUpload` and is already covered by the outstanding
 * and history dialogs. What is asserted here is only what is DIFFERENT about this upload,
 * and it is the dangerous part: it replaces the supplier's snapshot, so how many rows it
 * would replace has to be on screen BEFORE Confirm, and the supplier it will be applied to
 * has to be named.
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
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const previewStockList = vi.fn();
const applyStockList = vi.fn();
const testStockList = vi.fn();

vi.mock('../../services/fulfilmentService', () => ({
  previewStockList: (...a: unknown[]) => previewStockList(...a),
  applyStockList: (...a: unknown[]) => applyStockList(...a),
  testStockList: (...a: unknown[]) => testStockList(...a),
}));

vi.mock('../../reorder/services/outstandingImportService', () => ({
  getOutstandingUploadConfig: async () => ({ allowed_extensions: ['.xlsx', '.xls'] }),
}));

import { StockListUploadDialog } from './StockListUploadDialog';

const SUMMARY = {
  rows: 3,
  items_matched: 2,
  items_unmatched: 1,
  unmatched_item_codes: ['UNKNOWN-1'],
  qty_packed: 120,
  qty_unfinished: 340,
  loadable_cbm: 25.2,
  items_unmeasured: 1,
  unmeasured_item_codes: ['NOVOL-1'],
  unmapped_headers: [],
  unreadable_rows: 0,
};

function openDialog() {
  return render(
    <StockListUploadDialog
      open
      onOpenChange={() => {}}
      supplierId="sup-1"
      supplierName="Foshan Ceramics"
    />,
  );
}

/**
 * Pick the file AND press Test.
 *
 * Picking alone reads nothing: every SCM upload dialog shares one flow, and that flow
 * stopped firing a request on drop. Test is the explicit read, and it runs the preview this
 * screen renders as well as the `validate_only` verdict.
 */
async function pickFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File([new Uint8Array([1, 2, 3])], 'stock.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: /^Test$/i }));
  return file;
}

beforeEach(() => {
  previewStockList.mockReset();
  applyStockList.mockReset();
  testStockList.mockReset();
});

describe('StockListUploadDialog', () => {
  it('names the supplier the file will be applied to', () => {
    openDialog();

    expect(screen.getByText(/Foshan Ceramics/)).toBeInTheDocument();
  });

  it('says how many rows it would replace before Confirm is available', async () => {
    // The destructive half of this upload, on screen while it can still be cancelled.
    previewStockList.mockResolvedValue({
      ok: true,
      readable: true,
      missing_columns: [],
      problems: [],
      supplier_id: 'sup-1',
      supplier_name: 'Foshan Ceramics',
      rows_held_now: 42,
      sample: [],
      summary: SUMMARY,
    });
    openDialog();

    await pickFile();

    expect(await screen.findByText('Replaces')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('warns that unmeasured rows cannot be fitted to a container', async () => {
    // Singular and plural are separate strings because "1 model numbers are not in the
    // catalogue" is the kind of copy that makes a screen look unfinished.
    previewStockList.mockResolvedValue({
      ok: true,
      readable: true,
      missing_columns: [],
      problems: [],
      supplier_id: 'sup-1',
      supplier_name: 'Foshan Ceramics',
      rows_held_now: 0,
      sample: [],
      summary: SUMMARY,
    });
    openDialog();

    await pickFile();

    expect(await screen.findByText(/carries no volume/)).toBeInTheDocument();
    expect(screen.getByText(/model number is not in the catalogue/)).toBeInTheDocument();
  });

  it('uses plural copy when more than one row is affected', async () => {
    previewStockList.mockResolvedValue({
      ok: true,
      readable: true,
      missing_columns: [],
      problems: [],
      supplier_id: 'sup-1',
      supplier_name: 'Foshan Ceramics',
      rows_held_now: 0,
      sample: [],
      summary: { ...SUMMARY, items_unmeasured: 4, items_unmatched: 2 },
    });
    openDialog();

    await pickFile();

    expect(await screen.findByText(/of them carry no volume/)).toBeInTheDocument();
    expect(screen.getByText(/model numbers are not in the catalogue/)).toBeInTheDocument();
  });

  it('refuses to confirm a file it could not read, and names the column', async () => {
    previewStockList.mockResolvedValue({
      ok: false,
      readable: false,
      missing_columns: ['qty_packed'],
      problems: [],
      supplier_id: 'sup-1',
      supplier_name: 'Foshan Ceramics',
      rows_held_now: 0,
      sample: [],
      summary: {},
    });
    openDialog();

    await pickFile();

    expect(await screen.findByText(/no qty_packed column/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import stock list' })).toBeDisabled();
    expect(applyStockList).not.toHaveBeenCalled();
  });

  it('sends the supplier with the file on confirm', async () => {
    previewStockList.mockResolvedValue({
      ok: true,
      readable: true,
      missing_columns: [],
      problems: [],
      supplier_id: 'sup-1',
      supplier_name: 'Foshan Ceramics',
      rows_held_now: 0,
      sample: [],
      summary: SUMMARY,
    });
    applyStockList.mockResolvedValue({
      readable: true,
      missing_columns: [],
      supplier_id: 'sup-1',
      supplier_name: 'Foshan Ceramics',
      as_of: '2026-08-05',
      rows_written: 3,
      rows_replaced: 0,
      duplicate_models_merged: 0,
      summary: SUMMARY,
    });
    openDialog();
    const file = await pickFile();
    await screen.findByText('Replaces');

    fireEvent.click(screen.getByRole('button', { name: 'Import stock list' }));

    await waitFor(() => expect(applyStockList).toHaveBeenCalledWith(file, 'sup-1'));
    expect(await screen.findByText(/Saved 3 items/)).toBeInTheDocument();
  });
});
