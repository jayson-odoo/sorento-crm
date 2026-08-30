/**
 * S6-07 - the row of a record that is on its way out.
 *
 * A countdown started from a list row lives in a toast, because a row has nowhere
 * to put one. That leaves the reader with a toast that names an action and a list
 * that looks untouched, so the ROW has to say it too: it stays visible, dimmed,
 * until the window closes. Removing it early would be a lie - nothing has been
 * applied yet, and Cancel is still on the table.
 *
 * `rowPending` is how the grid learns it, because the action lives in a CELL and
 * the `<tr>` is the grid's; the two talk through `lib/pending-entity-store`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { pendingEntityKey, pendingEntityStore } from '@/lib/pending-entity-store';

type Row = { id: string; name: string };

const DATA: Row[] = [
  { id: 'p-1', name: 'Ergonomic Chair' },
  { id: 'p-2', name: 'Standing Desk' },
];

const COLUMNS: ColumnDef<Row>[] = [
  { id: 'name', accessorKey: 'name', header: 'Name', size: 400 },
];

function Harness({ rowPending }: { rowPending?: (row: Row) => boolean }) {
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
      rowPending={rowPending}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

function rows(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('tbody tr'));
}

beforeEach(() => {
  pendingEntityStore.clear('product', 'p-1');
});

describe('a row with an action parked on it (S6-07)', () => {
  it('marks itself pending and dims, while its neighbours are untouched', () => {
    const { container } = render(
      <Harness rowPending={(row) => row.id === 'p-1'} />,
    );

    const [first, second] = rows(container);
    expect(first).toHaveAttribute('data-pending', 'true');
    expect(first.className).toContain('opacity-50');
    expect(second).not.toHaveAttribute('data-pending');
    expect(second.className).not.toContain('opacity-50');
  });

  it('stays in the list: the record is not gone until the window closes', () => {
    const { container } = render(
      <Harness rowPending={(row) => row.id === 'p-1'} />,
    );

    expect(rows(container)).toHaveLength(2);
    expect(container.textContent).toContain('Ergonomic Chair');
  });

  it('a grid with no rowPending marks nothing', () => {
    const { container } = render(<Harness />);

    for (const row of rows(container)) {
      expect(row).not.toHaveAttribute('data-pending');
    }
  });

  it('the store is what a list reads, keyed by entity type and id', () => {
    pendingEntityStore.mark('product', 'p-1');
    const keys = pendingEntityStore.getKeys();

    expect(keys.has(pendingEntityKey('product', 'p-1'))).toBe(true);
    // Two entities can hold the same id; the key carries the type for that reason.
    expect(keys.has(pendingEntityKey('order', 'p-1'))).toBe(false);

    pendingEntityStore.clear('product', 'p-1');
    expect(pendingEntityStore.getKeys().size).toBe(0);
  });
});
