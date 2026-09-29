/**
 * The empty state of every DataGrid listing.
 *
 * The cell spans all columns, so on a grid wider than its scroll container a
 * centred message renders off-screen and the listing looks like a blank band -
 * which is exactly how a sticky filter that matches nothing used to read. jsdom
 * has no layout, so what is pinned here is the mechanism that keeps the message
 * in view: it lives in a start-aligned sticky container, not merely in the DOM.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  usePathname: () => '/some-listing',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string; note: string };

const COLUMNS: ColumnDef<Row>[] = [
  { accessorKey: 'name', header: 'Name', size: 900 },
  { accessorKey: 'note', header: 'Note', size: 900 },
];

function Harness({ emptyMessage }: { emptyMessage?: string }) {
  const table = useReactTable({
    data: [] as Row[],
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={0}
      isLoading={false}
      emptyMessage={emptyMessage}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

describe('DataGridTable empty state', () => {
  it('renders the default message', () => {
    render(<Harness />);
    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('renders a listing-supplied message', () => {
    render(<Harness emptyMessage="No stock inquiries match this filter" />);
    expect(screen.getByText('No stock inquiries match this filter')).toBeInTheDocument();
  });

  it('PR #1336: the empty state has no CTA slot; a passed action never renders', () => {
    function Smuggler() {
      const table = useReactTable({
        data: [] as Row[],
        columns: COLUMNS,
        getRowId: (r) => r.id,
        getCoreRowModel: getCoreRowModel(),
      });
      return (
        <DataGrid
          table={table}
          recordCount={0}
          isLoading={false}
          emptyMessage="No users yet"
          // @ts-expect-error the slot is gone: heading and hint only (CRM-wide rule)
          emptyAction={<button type="button">Add user</button>}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
        >
          <DataGridTable />
        </DataGrid>
      );
    }
    render(<Smuggler />);
    expect(screen.getByText('No users yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add user' })).toBeNull();
  });

  it('renders the message alone, with no button', () => {
    render(<Harness />);
    const empty = screen
      .getByText('No data available')
      .closest('[data-slot="data-grid-empty"]');
    expect(empty?.querySelectorAll('button')).toHaveLength(0);
  });

  it('keeps the message reachable on a grid wider than its scroll container', () => {
    render(<Harness />);
    const empty = screen
      .getByText('No data available')
      .closest('[data-slot="data-grid-empty"]') as HTMLElement;

    // Sticky to the start edge, so horizontal scroll never carries it away.
    expect(empty).toHaveClass('sticky');
    expect(empty).toHaveClass('start-0');
    expect(empty).toHaveClass('text-start');

    // ...and it must NOT be centred across the full (all-column) cell width, which
    // is what pushed it off-screen.
    const cell = empty.closest('td');
    expect(cell).not.toBeNull();
    expect(cell).toHaveAttribute('colspan', String(COLUMNS.length));
    expect(cell).not.toHaveClass('text-center');
  });
});
