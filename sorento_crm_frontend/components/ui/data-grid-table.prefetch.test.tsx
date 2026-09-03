/**
 * M4-06 - hovering a clickable `DataGrid` row prefetches its detail route.
 *
 * A viewport prefetch would fetch a page's worth of detail chunks (up to 100
 * rows) the reader never opens, so the trigger is `onPointerEnter`, once per
 * href (see `hooks/usePrefetchOnce.ts`).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

const push = vi.fn();
const prefetch = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/order-management/orders',
  useRouter: () => ({ push, prefetch }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string };

const DATA: Row[] = [
  { id: 'a1', name: 'Alpha' },
  { id: 'b2', name: 'Beta' },
];

const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

function Harness({ rowHref }: { rowHref?: (row: Row) => string }) {
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={DATA.length}
      isLoading={false}
      rowHref={rowHref}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

beforeEach(() => {
  push.mockClear();
  prefetch.mockClear();
});

describe('a linkable row prefetches on hover (M4-06)', () => {
  it('prefetches the href on pointer enter', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent.pointerEnter(screen.getByText('Alpha').closest('tr')!);

    expect(prefetch).toHaveBeenCalledTimes(1);
    expect(prefetch.mock.calls[0][0]).toContain('/order-management/orders/a1');
  });

  it('prefetches the SAME href only once across repeated hovers', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);
    const row = screen.getByText('Alpha').closest('tr')!;

    fireEvent.pointerEnter(row);
    fireEvent.pointerEnter(row);
    fireEvent.pointerEnter(row);

    expect(prefetch).toHaveBeenCalledTimes(1);
  });

  it('prefetches each row href independently', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent.pointerEnter(screen.getByText('Alpha').closest('tr')!);
    fireEvent.pointerEnter(screen.getByText('Beta').closest('tr')!);

    expect(prefetch).toHaveBeenCalledTimes(2);
  });

  it('does nothing when the row is not a link', () => {
    render(<Harness />);

    fireEvent.pointerEnter(screen.getByText('Alpha').closest('tr')!);

    expect(prefetch).not.toHaveBeenCalled();
  });
});
