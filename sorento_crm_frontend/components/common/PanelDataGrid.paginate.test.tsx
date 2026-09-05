/**
 * `paginate={false}` renders every row, and never with a fake page size.
 *
 * SF-8's ruling is that a line table ON A DOCUMENT shows all its lines in one
 * scroll. That was first built by handing TanStack `Number.MAX_SAFE_INTEGER` as
 * the page size, which is a page size no array length can hold: the shared
 * loading skeleton draws `pageSize` rows, so every such grid threw
 * `RangeError: Invalid array length` whenever it mounted with rows and column
 * preferences still resolving (M5 run 2 evidence, finding 2).
 *
 * TanStack already has the direct mechanism: with no `getPaginationRowModel`,
 * `getRowModel()` IS the pre-pagination row model, so no slicing happens at all.
 * The two `useFieldArray` line tables have always done it that way and never hit
 * the wall.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ColumnDef } from '@tanstack/react-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/packing-lists',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const columnPrefs = { isLoading: false };
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: columnPrefs.isLoading,
  }),
}));

import { PanelDataGrid } from './PanelDataGrid';

interface Row {
  id: string;
  name: string;
}

const ROWS: Row[] = Array.from({ length: 37 }, (_, index) => ({
  id: `r${index + 1}`,
  name: `Line ${index + 1}`,
}));

const COLUMNS: ColumnDef<Row>[] = [
  {
    id: 'name',
    accessorFn: (row) => row.name,
    header: 'Name',
    cell: ({ row }) => row.original.name,
    size: 200,
    meta: { headerTitle: 'Name' },
  },
];

function renderPanel(paginate: boolean) {
  return render(
    <PanelDataGrid<Row>
      title="Lines"
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(row) => row.id}
      listingKey="test.panel-data-grid.paginate"
      emptyTitle="No lines"
      paginate={paginate}
    />,
  );
}

describe('PanelDataGrid paginate={false}', () => {
  it('renders every row and no pager', () => {
    columnPrefs.isLoading = false;
    const { container } = renderPanel(false);

    expect(container.querySelectorAll('tbody tr')).toHaveLength(37);
    expect(screen.getByText('Line 37')).toBeInTheDocument();
    expect(screen.queryByText(/Rows per page/i)).not.toBeInTheDocument();
  });

  it('does not throw while the column preferences are still resolving', () => {
    columnPrefs.isLoading = true;
    try {
      // The crash was here: the grid mounts with rows, the shared `isLoading`
      // is still true because preferences have not landed, so the skeleton
      // branch runs - and used to ask for a `Number.MAX_SAFE_INTEGER`-long array.
      expect(() => renderPanel(false)).not.toThrow();
    } finally {
      columnPrefs.isLoading = false;
    }
  });

  it('still pages by default', () => {
    columnPrefs.isLoading = false;
    const { container } = renderPanel(true);

    expect(container.querySelectorAll('tbody tr')).toHaveLength(10);
    expect(screen.queryByText('Line 37')).not.toBeInTheDocument();
  });
});
