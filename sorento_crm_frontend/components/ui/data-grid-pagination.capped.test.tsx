/**
 * INTLOG-SPEED - a list whose backend caps its count (Integration Log: offset + 10,000) shows
 * the total as "10,000+" and keeps Next live, because more rows exist past the window.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridPagination } from './data-grid-pagination';

vi.mock('next/navigation', () => ({
  usePathname: () => '/integration-management/integration-logs',
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string };
const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

function Harness({ total, capped, pageIndex = 0 }: { total: number; capped?: boolean; pageIndex?: number }) {
  const table = useReactTable({
    data: [{ id: '1', name: 'Alpha' }],
    columns: COLUMNS,
    getRowId: (r) => r.id,
    manualPagination: true,
    pageCount: Math.ceil(total / 50),
    initialState: { pagination: { pageIndex, pageSize: 50 } },
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid table={table} recordCount={total} tableLayout={{ width: 'fixed' }}>
      <DataGridPagination recordCountCapped={capped} />
    </DataGrid>
  );
}

describe('DataGridPagination with a capped total (INTLOG-SPEED)', () => {
  it('reads "of 10,000+" and keeps Next enabled on page 1', () => {
    render(<Harness total={10000} capped />);
    expect(screen.getByText('1 - 50 of 10,000+')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /go to next page/i })).toBeEnabled();
  });

  it('the window moves with the page: page 3 of a capped list reads "of 10,100+"', () => {
    render(<Harness total={10100} capped pageIndex={2} />);
    expect(screen.getByText('101 - 150 of 10,100+')).toBeInTheDocument();
  });

  it('an exact total under a thousand reads plainly', () => {
    render(<Harness total={120} />);
    expect(screen.getByText('1 - 50 of 120')).toBeInTheDocument();
  });
});

describe('DataGridPagination number format (one thousands format for from, to and count)', () => {
  it('formats an exact total: "1 - 50 of 1,304"', () => {
    render(<Harness total={1304} />);
    expect(screen.getByText('1 - 50 of 1,304')).toBeInTheDocument();
  });

  it('formats all three numbers on a deep capped page: "9,951 - 10,000 of 19,950+"', () => {
    render(<Harness total={19950} capped pageIndex={199} />);
    expect(screen.getByText('9,951 - 10,000 of 19,950+')).toBeInTheDocument();
  });
});
