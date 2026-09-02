/**
 * M4-03 - the pagination strip stays live on a placeholder page.
 *
 * Baseline: `isLoading` alone swapped BOTH the rows-per-page control and the
 * page buttons for skeleton bars, so a page/sort/filter/search change reset
 * the pager along with the grid. `LIST_QUERY_OPTIONS` keeps the previous
 * page's rows around while the next one loads, so the gate is "no rows yet",
 * not merely "loading".
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridPagination } from './data-grid-pagination';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const prefsGate = vi.hoisted(() => ({ isLoading: false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: prefsGate.isLoading }),
}));

afterEach(() => {
  prefsGate.isLoading = false;
});

type Row = { id: string; name: string };

const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

function Harness({ isLoading, rows }: { isLoading: boolean; rows: Row[] }) {
  const table = useReactTable({
    data: rows,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    manualPagination: true,
    pageCount: 3,
    initialState: { pagination: { pageIndex: 0, pageSize: 25 } },
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <>
      {/* The page the table is actually on, so a test can press Next twice and
          say where it landed rather than only that the button was enabled. */}
      <span data-testid="page-index">{table.getState().pagination.pageIndex}</span>
      <DataGrid table={table} recordCount={50} isLoading={isLoading} tableLayout={{ width: 'fixed' }}>
        <DataGridPagination />
      </DataGrid>
    </>
  );
}

describe('DataGridPagination on a placeholder page (M4-03)', () => {
  it('shows both skeletons while loading with no rows yet', () => {
    const { container } = render(<Harness isLoading rows={[]} />);

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('Rows per page')).toBeNull();
  });

  it('keeps the rows-per-page select and the page buttons live while loading WITH rows on screen', () => {
    render(<Harness isLoading rows={[{ id: '1', name: 'Alpha' }]} />);

    expect(screen.getByText('Rows per page')).toBeInTheDocument();
    const nextButton = screen.getByRole('button', { name: /go to next page/i });
    expect(nextButton).toBeEnabled();
  });

  it('a second Next press while a placeholder page is showing still works (the second press wins)', () => {
    render(<Harness isLoading rows={[{ id: '1', name: 'Alpha' }]} />);
    const nextButton = screen.getByRole('button', { name: /go to next page/i });

    fireEvent.click(nextButton);
    expect(screen.getByTestId('page-index')).toHaveTextContent('1');

    // Still loading, still showing the placeholder page - and the reader who
    // pressed again lands two pages on, not one.
    fireEvent.click(nextButton);
    expect(screen.getByTestId('page-index')).toHaveTextContent('2');
  });

  it('shows the skeleton while column preferences are still resolving, rows or not', () => {
    // The pager and the body read the same gate, so they cannot disagree about
    // what a first load is. Column preferences decide the column set, and a
    // pager drawn beside a body that is still a skeleton says the page is
    // ready when it is not.
    prefsGate.isLoading = true;
    const { container } = render(<Harness isLoading={false} rows={[{ id: '1', name: 'Alpha' }]} />);

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('Rows per page')).toBeNull();
  });

  it('renders the live controls once loading finishes', () => {
    render(<Harness isLoading={false} rows={[{ id: '1', name: 'Alpha' }]} />);

    expect(screen.getByText('Rows per page')).toBeInTheDocument();
  });
});
