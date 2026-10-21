/**
 * BARCODE-IMPORT: the dialog renders the server's per-row resolution and Apply posts the file.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const generateExcelFile = vi.fn().mockResolvedValue(undefined);
vi.mock('@/lib/excel-utils', () => ({
  generateExcelFile: (...a: unknown[]) => generateExcelFile(...a),
}));

const previewBarcodeImport = vi.fn();
const applyBarcodeImport = vi.fn();

vi.mock('../services/productBarcodeImportService', () => ({
  BARCODE_IMPORT_ACCEPT: '.xlsx,.csv',
  previewBarcodeImport: (...a: unknown[]) => previewBarcodeImport(...a),
  applyBarcodeImport: (...a: unknown[]) => applyBarcodeImport(...a),
}));

import { BarcodeImportDialog } from './BarcodeImportDialog';

const COUNTS = {
  new: 1,
  change: 1,
  same: 1,
  unknown_code: 1,
  ambiguous_code: 0,
  repeated_code: 0,
  blank_barcode: 0,
  too_long: 1,
  duplicate: 1,
  not_ean13: 1,
  scientific: 0,
};

const BASE_OUTCOME = {
  readable: true,
  missing_columns: [],
  code_column: 'Item Code',
  barcode_column: 'EAN',
  total_rows: 5,
  counts: COUNTS,
  rows: [
    {
      row: 2,
      product_code: 'SRT-A',
      product_name: 'Basin A',
      old_barcode: null,
      new_barcode: '9555123400011',
      status: 'new',
      warnings: ['duplicate'],
      repeated_of_row: null,
    },
    {
      row: 3,
      product_code: 'SRT-B',
      product_name: 'Basin B',
      old_barcode: '9555123400028',
      new_barcode: '9555123400035',
      status: 'change',
      warnings: [],
      repeated_of_row: null,
    },
    {
      row: 4,
      product_code: 'SRT-C',
      product_name: 'Basin C',
      old_barcode: '123',
      new_barcode: '123',
      status: 'same',
      warnings: ['not_ean13'],
      repeated_of_row: null,
    },
    {
      row: 5,
      product_code: 'NOPE',
      product_name: null,
      old_barcode: null,
      new_barcode: '9555123400042',
      status: 'unknown_code',
      warnings: [],
      repeated_of_row: null,
    },
    {
      row: 6,
      product_code: 'SRT-D',
      product_name: 'Basin D',
      old_barcode: null,
      new_barcode: 'X'.repeat(101),
      status: 'too_long',
      warnings: [],
      repeated_of_row: null,
    },
    {
      row: 7,
      product_code: 'SRT-E',
      product_name: 'Basin E',
      old_barcode: null,
      new_barcode: '9555123400066',
      status: 'new',
      warnings: [],
      repeated_of_row: null,
    },
  ],
};

const OUTCOME = {
  ...BASE_OUTCOME,
  note_column: 'Note',
  preview_token: 'tok-1',
  rows: BASE_OUTCOME.rows.map((r) => ({
    ...r,
    duplicate_of: r.product_code === 'SRT-A' ? ['SRT-A-OLD'] : [],
    note: r.product_code === 'SRT-A' ? 'Same barcode as SRT-A-OLD' : null,
  })),
};

function openDialog() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <BarcodeImportDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

function pickAndTest() {
  const input = document.querySelector(
    'input[type="file"]',
  ) as HTMLInputElement;
  const file = new File([new Uint8Array([1, 2, 3])], 'barcodes.xlsx');
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: /^Test$/i }));
  return file;
}

beforeEach(() => {
  previewBarcodeImport.mockReset();
  applyBarcodeImport.mockReset();
});

describe('BarcodeImportDialog', () => {
  it('reads nothing until Test, then shows columns, statuses and warnings', async () => {
    previewBarcodeImport.mockResolvedValue(OUTCOME);
    openDialog();
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'b.xlsx')] } });
    expect(previewBarcodeImport).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /^Test$/i }));

    expect(await screen.findByText('Item Code')).toBeInTheDocument();
    expect(screen.getByText('EAN')).toBeInTheDocument();
    for (const label of ['Unknown code', 'Duplicate', 'Not EAN-13 valid']) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(2); // tile + badge
    }
    expect(screen.getByText('Too long')).toBeInTheDocument(); // badge
    expect(screen.getByText('Too long or E+')).toBeInTheDocument(); // tile
    expect(screen.getAllByText('New').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('9555123400028')).toBeInTheDocument(); // old value of the Change row
    expect(
      screen.getByRole('button', { name: 'Apply 2 barcodes' }),
    ).toBeEnabled();
  });

  it('Apply posts the same file and reports how many were written', async () => {
    previewBarcodeImport.mockResolvedValue(OUTCOME);
    applyBarcodeImport.mockResolvedValue({ ...OUTCOME, applied: 2 });
    openDialog();
    const file = pickAndTest();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Apply 2 barcodes' }),
    );

    await waitFor(() =>
      expect(applyBarcodeImport).toHaveBeenCalledWith(file, 'tok-1'),
    );
    expect(await screen.findByText(/products? updated/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Test$/i }),
    ).not.toBeInTheDocument();
  });

  it('a file with nothing to write cannot be applied', async () => {
    previewBarcodeImport.mockResolvedValue({
      ...OUTCOME,
      counts: { ...COUNTS, new: 0, change: 0 },
    });
    openDialog();
    pickAndTest();
    expect(
      await screen.findByRole('button', { name: 'Apply 0 barcodes' }),
    ).toBeDisabled();
  });

  it('names the missing column of an unreadable file', async () => {
    previewBarcodeImport.mockResolvedValue({
      ...OUTCOME,
      readable: false,
      missing_columns: ['barcode'],
      rows: [],
    });
    openDialog();
    pickAndTest();
    expect(
      await screen.findByText(/No barcode column found/),
    ).toBeInTheDocument();
  });
});

describe('BarcodeImportDialog template', () => {
  it('downloads a two-column template', async () => {
    openDialog();
    fireEvent.click(screen.getByRole('button', { name: /Download template/i }));
    await waitFor(() => expect(generateExcelFile).toHaveBeenCalled());
    const [, columns, filename] = generateExcelFile.mock.calls[0];
    expect((columns as { label: string }[]).map((c) => c.label)).toEqual([
      'Product Code',
      'Barcode',
    ]);
    expect(filename).toBe('barcode_import_template.xlsx');
  });
});

describe('BarcodeImportDialog crew audit round', () => {
  it('lists only rows needing attention until Show all is on', async () => {
    previewBarcodeImport.mockResolvedValue(OUTCOME);
    openDialog();
    pickAndTest();
    expect(await screen.findByText('SRT-A')).toBeInTheDocument(); // New + Duplicate
    expect(screen.getByText('SRT-B')).toBeInTheDocument(); // Change
    expect(screen.getByText('SRT-C')).toBeInTheDocument(); // Same + Not EAN-13
    expect(screen.getByText('NOPE')).toBeInTheDocument(); // Unknown code
    expect(screen.queryByText('SRT-E')).toBeNull(); // plain New
    fireEvent.click(screen.getByRole('switch'));
    expect(await screen.findByText('SRT-E')).toBeInTheDocument();
  });

  it('shows the note and the codes sharing a duplicate barcode', async () => {
    previewBarcodeImport.mockResolvedValue(OUTCOME);
    openDialog();
    pickAndTest();
    expect(await screen.findByText('Also on SRT-A-OLD')).toBeInTheDocument();
    expect(screen.getByText('Same barcode as SRT-A-OLD')).toBeInTheDocument();
  });

  it('cannot apply before a Test of the chosen file', () => {
    openDialog();
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'b.xlsx')] } });
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  });

  it('locks Cancel while the apply runs', async () => {
    previewBarcodeImport.mockResolvedValue(OUTCOME);
    let finish: (v: unknown) => void = () => {};
    applyBarcodeImport.mockReturnValue(new Promise((r) => (finish = r)));
    openDialog();
    pickAndTest();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Apply 2 barcodes' }),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled(),
    );
    finish({ ...OUTCOME, applied: 2 });
    expect(await screen.findByText(/products? updated/)).toBeInTheDocument();
  });
});
