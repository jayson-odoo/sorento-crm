/**
 * PullCompareTab - Phase 3 fix round red tests (captain's fix-round brief, V-1).
 *
 * `useComparePull` is mocked at the hook module (component -> hook, per layering) so the
 * mutation resolves synchronously with whatever fixture a test hands it, in the REAL backend
 * response shape (`app/services/autocount_pull_compare.py` + the route's own `summary`):
 * `{ summary: { filename, compared_at, total, matched, different, only_in_excel, only_in_pull,
 * qty_total_excel, qty_total_pull }, differences: [{ item_code, field, excel, pull }],
 * only_in_excel: [...codes], only_in_pull: [...codes] }`.
 *
 * `lib/excel-utils` is mocked too so the differences-download assertions read the call the
 * component made rather than a real generated file.
 *
 * Two real defects this file pins, both already present in `PullCompareTab.tsx`:
 *  - `summaryHeadline`'s `ok` check is `matched === total && differences.length === 0` only -
 *    it never looks at `only_in_excel` / `only_in_pull`, so a batch missing rows entirely (no
 *    per-field difference, just an absence) still gets called "100% match" - V-1b.
 *  - the differences grid reads `row.original.your_excel` / `row.original.autocount_pull`,
 *    keys the real backend has never sent (it sends `excel` / `pull`) - so every cell in those
 *    two columns is blank in production - V-1c/V-1d.
 *  - `handleDownloadDifferences` names the exported file `autocount-pull-${jobId}-differences.
 *    xlsx` - a UUID in a filename the user sees, the cursor rule's own "no UUIDs in the FE UI" -
 *    V-1d.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const useComparePull = vi.fn();
vi.mock('../hooks/useAutocountPull', () => ({
  useComparePull: (...a: unknown[]) => useComparePull(...a),
}));

const generateExcelFile = vi.fn();
const parseExcelFile = vi.fn();
vi.mock('@/lib/excel-utils', () => ({
  generateExcelFile: (...a: unknown[]) => generateExcelFile(...a),
  parseExcelFile: (...a: unknown[]) => parseExcelFile(...a),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// DataGrid fetches column preferences under `useListingColumnPreferences`; unmocked, jsdom
// never answers it, so the grid stays on its loading skeleton forever and no row renders
// (`project_datagrid_jsdom_rows_mockable.md` - it is not a jsdom limitation, just this fetch).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { PullCompareTab } from './PullCompareTab';

const JOB_ID = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';

function xlsxFile(name = 'check.xlsx') {
  return new File(['x'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

/** The hidden input inside the shared FileDropzone. */
function fileInput(): HTMLInputElement {
  return screen.getByLabelText('Excel file to compare') as HTMLInputElement;
}

async function dropFile(rows: Record<string, unknown>[] = [{ 'Item Code': 'X' }]) {
  parseExcelFile.mockResolvedValueOnce(rows);
  fireEvent.change(fileInput(), { target: { files: [xlsxFile()] } });
  await waitFor(() => expect(parseExcelFile).toHaveBeenCalled());
}

/** The differences DataGrid needs a QueryClient (`useListingColumnPreferences`) even
 *  though this tab does not itself use react-query for that grid's data. */
function renderTab(entity: 'products' | 'stock_balances' = 'products') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(PullCompareTab, { jobId: JOB_ID, entity }),
    ),
  );
}

function mutateReturning(result: unknown) {
  return {
    mutate: (
      _vars: unknown,
      opts?: { onSuccess?: (data: unknown) => void },
    ) => {
      opts?.onSuccess?.(result);
    },
    isPending: false,
  };
}

beforeEach(() => {
  useComparePull.mockReset();
  generateExcelFile.mockReset();
  parseExcelFile.mockReset();
});

describe('PullCompareTab - headline (captain ruling, Phase 3 fix round)', () => {
  it('V-1a: all matched and both only_in counts 0 -> "100% match", the counts, and the file name', async () => {
    useComparePull.mockReturnValue(
      mutateReturning({
        summary: {
          filename: 'check.xlsx', compared_at: '2026-09-20T00:00:00Z',
          total: 10, matched: 10, different: 0, only_in_excel: 0, only_in_pull: 0,
        },
        differences: [], only_in_excel: [], only_in_pull: [],
      }),
    );

    renderTab();
    await dropFile();

    expect(screen.getByText(/100% match/i)).toBeInTheDocument();
    // The FileDropzone's own picked-file chip ALSO renders the bare filename, so pin the
    // whole composed sentence (unique to the headline) rather than the filename alone.
    expect(screen.getByText(/10 of 10 items agree with check\.xlsx/)).toBeInTheDocument();
  });

  it('V-1b: matched == total but only_in_pull > 0 -> NOT a 100% match headline', async () => {
    useComparePull.mockReturnValue(
      mutateReturning({
        summary: {
          filename: 'partial.xlsx', compared_at: '2026-09-20T00:00:00Z',
          total: 9, matched: 9, different: 0, only_in_excel: 0, only_in_pull: 1,
        },
        differences: [], only_in_excel: [], only_in_pull: [`${JOB_ID}-ONLY-PULL`],
      }),
    );

    renderTab();
    await dropFile();

    expect(screen.queryByText(/100% match/i)).not.toBeInTheDocument();
  });
});

describe('PullCompareTab - differences grid (captain ruling, Phase 3 fix round, V-1c)', () => {
  it('shows the excel and pull VALUES for a differing field', async () => {
    useComparePull.mockReturnValue(
      mutateReturning({
        summary: {
          filename: 'diff.xlsx', compared_at: '2026-09-20T00:00:00Z',
          total: 1, matched: 0, different: 1, only_in_excel: 0, only_in_pull: 0,
        },
        differences: [
          { item_code: 'SRT-1', field: 'price', excel: '10.00', pull: '12.00' },
        ],
        only_in_excel: [], only_in_pull: [],
      }),
    );

    renderTab();
    await dropFile();

    expect(await screen.findByText('10.00')).toBeInTheDocument();
    expect(screen.getByText('12.00')).toBeInTheDocument();
  });
});

describe('PullCompareTab - differences export (captain ruling, Phase 3 fix round, V-1d)', () => {
  it('exports rows carrying the excel/pull values, filename without the job id', async () => {
    useComparePull.mockReturnValue(
      mutateReturning({
        summary: {
          filename: 'diff.xlsx', compared_at: '2026-09-20T00:00:00Z',
          total: 1, matched: 0, different: 1, only_in_excel: 0, only_in_pull: 0,
        },
        differences: [
          { item_code: 'SRT-1', field: 'price', excel: '10.00', pull: '12.00' },
        ],
        only_in_excel: [], only_in_pull: [],
      }),
    );

    renderTab();
    await dropFile();
    await screen.findByText('10.00');

    fireEvent.click(screen.getByRole('button', { name: /Download differences/i }));

    expect(generateExcelFile).toHaveBeenCalledTimes(1);
    const [rows, cols, filename] = generateExcelFile.mock.calls[0];

    expect(filename).not.toContain(JOB_ID);

    const colKeys: string[] = (cols as Array<{ key: string }>).map((c) => c.key);
    // The columns must read keys the REAL backend row actually carries (`excel`/`pull`),
    // not `your_excel`/`autocount_pull` - otherwise every exported cell is blank.
    expect(colKeys).toContain('excel');
    expect(colKeys).toContain('pull');
    expect((rows as Array<Record<string, unknown>>)[0].excel).toBe('10.00');
    expect((rows as Array<Record<string, unknown>>)[0].pull).toBe('12.00');
  });
});
