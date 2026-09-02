/**
 * M4 list latency - a grid that still has rows dims them instead of showing a
 * skeleton.
 *
 * `LIST_QUERY_OPTIONS` keeps the previous page's rows in
 * `table.getRowModel()` while the next page loads; the grid says so by dimming
 * the body rather than unmounting it, on the house tokens.
 *
 * The gate is "no rows to show", not "loading" - and it lives HERE, in the
 * primitive, so all 186 grids inherit it. A call site that never passes
 * `isPlaceholderData` still gets the dim, because `isLoading` with rows on
 * screen means exactly the same thing to the reader. `isPlaceholderData`
 * stays as the explicit override.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

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

const DATA: Row[] = [{ id: 'p-1', name: 'Ergonomic Chair' }];

const COLUMNS: ColumnDef<Row>[] = [
  {
    id: 'name',
    accessorKey: 'name',
    header: 'Name',
    size: 400,
    meta: { skeleton: <span data-testid="cell-skeleton" /> },
  },
];

function Harness({
  isPlaceholderData,
  isLoading = false,
  rows = DATA,
}: {
  isPlaceholderData?: boolean;
  isLoading?: boolean;
  rows?: Row[];
}) {
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
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

describe('DataGridTable dims while showing a placeholder page (M4)', () => {
  it('adds the dim and transition classes while isPlaceholderData is true', () => {
    const { container } = render(<Harness isPlaceholderData />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).toContain('opacity-60');
    expect(tbody.className).toContain('transition-opacity');
    expect(tbody.className).toContain('duration-(--duration-fast)');
    expect(tbody.className).toContain('ease-(--ease-standard)');
  });

  it('adds none of them when isPlaceholderData is false and nothing is loading', () => {
    const { container } = render(<Harness isPlaceholderData={false} />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).not.toContain('opacity-60');
    expect(tbody.className).not.toContain('transition-opacity');
  });

  it('adds none of them when isPlaceholderData is omitted and nothing is loading', () => {
    const { container } = render(<Harness />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).not.toContain('opacity-60');
  });
});

describe('DataGridTable gates the body skeleton on having no rows (M4-02)', () => {
  it('dims the rows it already has while loading, with no isPlaceholderData passed', () => {
    const { container } = render(<Harness isLoading />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).toContain('opacity-60');
    expect(tbody.className).toContain('transition-opacity');
    expect(tbody.className).toContain('duration-(--duration-fast)');
    expect(tbody.className).toContain('ease-(--ease-standard)');
  });

  it('keeps the rows on screen while loading instead of replacing them with a skeleton', () => {
    render(<Harness isLoading />);

    expect(screen.getByText('Ergonomic Chair')).toBeInTheDocument();
    expect(screen.queryAllByTestId('cell-skeleton')).toHaveLength(0);
  });

  it('renders the skeleton on the FIRST load, when there are no rows yet', () => {
    render(<Harness isLoading rows={[]} />);

    expect(screen.queryAllByTestId('cell-skeleton').length).toBeGreaterThan(0);
  });

  it('keeps the skeleton while column preferences are still resolving, rows or not', () => {
    // The grid would otherwise paint those rows under the DEFAULT column layout
    // and re-lay them out a tick later, which is the flash the provider merges
    // `isColumnPreferencesLoading` into `isLoading` to avoid.
    prefsGate.isLoading = true;
    const { container } = render(<Harness isLoading={false} />);

    expect(screen.queryAllByTestId('cell-skeleton').length).toBeGreaterThan(0);
    expect(container.querySelector('tbody')!.className).not.toContain('opacity-60');
  });

  it('does not dim a first load - there is nothing on screen to dim', () => {
    const { container } = render(<Harness isLoading rows={[]} />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).not.toContain('opacity-60');
  });
});
