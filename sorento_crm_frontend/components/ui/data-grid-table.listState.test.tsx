/**
 * M5-07 - Back to list restores the row (user ruling, absolute).
 *
 * `appendListState` names the row on the way OUT (the detail href), and
 * `DataGridTable` reads that name back on the way IN (list mount). Both sides
 * have to resolve the SAME id for a given row, in this order:
 *
 *   1. `row.id`, when the table itself resolves row identity (`getRowId` is
 *      set) - the caller's own stable key, so it wins over anything else.
 *   2. `row.original.id`, the record's own id field.
 *   3. the last path segment of the row's href - what every `rowHref` in this
 *      app already embeds (`/module/entity/${id}`), for the rare row whose
 *      shape carries neither.
 *
 * `useHrefWithListState` (`BackToList.tsx`) already forwards the WHOLE search
 * string unchanged, so Back, the post-delete push and Edit all carry `from`
 * for free - the last test below is the one assertion that stays true.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';
import { useHrefWithListState } from '@/components/common/BackToList';

const push = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  usePathname: () => '/order-management/orders',
  useRouter: () => ({ push, prefetch: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

/**
 * `DataGridTable` reads `from` off `window.location.search` directly (not
 * `next/navigation`'s `useSearchParams()` - see the comment on
 * `useReturnedRowId` in `data-grid-table.tsx` for why), so these tests drive
 * the real browser URL rather than the `next/navigation` mock.
 */
function setLocationSearch(qs: string) {
  window.history.pushState({}, '', qs ? `/order-management/orders?${qs}` : '/order-management/orders');
}

beforeEach(() => {
  search = '';
  push.mockClear();
  setLocationSearch('');
});

afterEach(() => {
  vi.restoreAllMocks();
  setLocationSearch('');
});

function harness<TData extends object>({
  data,
  columns,
  getRowId,
  rowHref,
}: {
  data: TData[];
  columns: ColumnDef<TData>[];
  getRowId?: (row: TData) => string;
  rowHref: (row: TData) => string;
}) {
  function Harness() {
    const table = useReactTable({
      data,
      columns,
      getRowId,
      getCoreRowModel: getCoreRowModel(),
    });
    return (
      <DataGrid
        table={table}
        recordCount={data.length}
        isLoading={false}
        rowHref={rowHref}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <DataGridTable />
      </DataGrid>
    );
  }
  return Harness;
}

describe('appendListState names the row on the way out (M5-07)', () => {
  it('uses row.id when the table resolves row identity via getRowId', () => {
    type Row = { pk: string; name: string };
    const DATA: Row[] = [{ pk: 'x1', name: 'Alpha' }];
    const Harness = harness<Row>({
      data: DATA,
      columns: [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }],
      getRowId: (r) => `gid-${r.pk}`,
      rowHref: (r) => `/foo/${r.pk}`,
    });
    render(<Harness />);

    fireEvent.click(screen.getByText('Alpha'));

    const href = push.mock.calls[0][0] as string;
    expect(new URLSearchParams(href.split('?')[1]).get('from')).toBe('gid-x1');
  });

  it('falls back to row.original.id when the table has no getRowId', () => {
    type Row = { id: string; name: string };
    const DATA: Row[] = [{ id: 'orig-1', name: 'Alpha' }];
    const Harness = harness<Row>({
      data: DATA,
      columns: [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }],
      rowHref: (r) => `/foo/${r.id}`,
    });
    render(<Harness />);

    fireEvent.click(screen.getByText('Alpha'));

    const href = push.mock.calls[0][0] as string;
    expect(new URLSearchParams(href.split('?')[1]).get('from')).toBe('orig-1');
  });

  it('falls back to the href\'s own last path segment with neither getRowId nor an id field', () => {
    type Row = { code: string; name: string };
    const DATA: Row[] = [{ code: 'C9', name: 'Alpha' }];
    const Harness = harness<Row>({
      data: DATA,
      columns: [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }],
      rowHref: (r) => `/foo/${r.code}`,
    });
    render(<Harness />);

    fireEvent.click(screen.getByText('Alpha'));

    const href = push.mock.calls[0][0] as string;
    expect(new URLSearchParams(href.split('?')[1]).get('from')).toBe('C9');
  });
});

type Row = { id: string; name: string };
const ROWS: Row[] = [
  { id: 'a1', name: 'Alpha' },
  { id: 'a2', name: 'Beta' },
  { id: 'a3', name: 'Gamma' },
];
const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

function ListHarness() {
  const table = useReactTable({
    data: ROWS,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={ROWS.length}
      isLoading={false}
      rowHref={(r) => `/order-management/orders/${r.id}`}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

describe('DataGridTable restores the row on the way in (M5-07)', () => {
  it('scrolls the matching row into view and marks it returned, on mount', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    setLocationSearch('from=a2');

    render(<ListHarness />);

    const row = screen.getByText('Beta').closest('tr')!;
    expect(row).toHaveAttribute('data-returned', 'true');
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' });
    // Only the named row - not the whole page.
    expect(screen.getByText('Alpha').closest('tr')).not.toHaveAttribute('data-returned', 'true');
  });

  it('clears the highlight on the next pointerdown, anywhere', () => {
    Element.prototype.scrollIntoView = vi.fn();
    setLocationSearch('from=a2');

    render(<ListHarness />);
    expect(screen.getByText('Beta').closest('tr')).toHaveAttribute('data-returned', 'true');

    fireEvent.pointerDown(document.body);

    expect(screen.getByText('Beta').closest('tr')).not.toHaveAttribute('data-returned', 'true');
  });

  it('is a no-op when the from id is not on the current page', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    setLocationSearch('from=not-on-this-page');

    render(<ListHarness />);

    expect(scrollIntoView).not.toHaveBeenCalled();
    for (const label of ['Alpha', 'Beta', 'Gamma']) {
      expect(screen.getByText(label).closest('tr')).not.toHaveAttribute('data-returned', 'true');
    }
  });
});

describe('useHrefWithListState forwards from unchanged (M5-07)', () => {
  it('carries `from` through to Back/Edit/post-delete hrefs, since it forwards the whole query string', () => {
    search = 'page=2&limit=50&from=row-38';

    function Probe() {
      const href = useHrefWithListState('/order-management/orders');
      return <span data-testid="href">{href}</span>;
    }
    render(<Probe />);

    expect(screen.getByTestId('href').textContent).toBe(
      '/order-management/orders?page=2&limit=50&from=row-38',
    );
  });
});
