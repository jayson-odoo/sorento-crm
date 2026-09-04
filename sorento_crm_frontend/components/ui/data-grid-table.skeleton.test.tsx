/**
 * The loading skeleton draws a BOUNDED number of rows, whatever the page size is.
 *
 * `Array.from({ length: pagination.pageSize })` is only safe while every caller
 * keeps `pageSize` inside array bounds, and one did not: a `paginate={false}`
 * `PanelDataGrid` used to set `Number.MAX_SAFE_INTEGER` as its page size, so the
 * skeleton branch threw `RangeError: Invalid array length` the moment the grid
 * mounted with rows still loading (M5 run 2 evidence, finding 2 - the Packing
 * Lists "Proforma invoices" tab crashed 100% of the time, on every record).
 *
 * A skeleton is a placeholder for what is about to arrive, not a faithful copy of
 * it, so the row count is capped in ONE place - `SKELETON_ROWS_MAX` - and every
 * body render path (plain, column-drag, row-drag) reads it through
 * `skeletonRowCount`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  type ColumnDef,
} from '@tanstack/react-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/packing-lists',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { DataGrid } from './data-grid';
import { DataGridTable, SKELETON_ROWS_MAX, skeletonRowCount } from './data-grid-table';

type Row = { id: string; name: string };

const COLUMNS: ColumnDef<Row>[] = [
  { id: 'name', accessorKey: 'name', header: 'Name', size: 300 },
];

function Harness({ rows, pageSize }: { rows: Row[]; pageSize: number }) {
  const table = useReactTable({
    data: rows,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    state: { pagination: { pageIndex: 0, pageSize } },
    onPaginationChange: () => {},
    pageCount: 1,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

function bodyRows(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('tbody tr'));
}

describe('skeletonRowCount', () => {
  it('caps an unbounded page size at SKELETON_ROWS_MAX', () => {
    expect(skeletonRowCount(Number.MAX_SAFE_INTEGER)).toBe(SKELETON_ROWS_MAX);
  });

  it('draws exactly the page size when the page is smaller than the cap', () => {
    expect(skeletonRowCount(3)).toBe(3);
  });

  it('falls back to the cap for a missing or nonsense page size', () => {
    expect(skeletonRowCount(undefined)).toBe(SKELETON_ROWS_MAX);
    expect(skeletonRowCount(0)).toBe(SKELETON_ROWS_MAX);
    expect(skeletonRowCount(Number.NaN)).toBe(SKELETON_ROWS_MAX);
  });
});

describe('DataGridTable loading skeleton with an unbounded page size', () => {
  it('renders without throwing and draws a bounded number of skeleton rows', () => {
    const { container } = render(<Harness rows={[]} pageSize={Number.MAX_SAFE_INTEGER} />);

    expect(bodyRows(container)).toHaveLength(SKELETON_ROWS_MAX);
  });

  it('still draws one skeleton row per row of a small page', () => {
    const { container } = render(<Harness rows={[]} pageSize={3} />);

    expect(bodyRows(container)).toHaveLength(3);
  });
});
