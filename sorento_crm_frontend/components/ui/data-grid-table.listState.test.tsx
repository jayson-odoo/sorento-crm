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

function ListHarness({ rows = ROWS }: { rows?: Row[] }) {
  const table = useReactTable({
    data: rows,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
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
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    setLocationSearch('from=a2');

    render(<ListHarness />);

    const row = screen.getByText('Beta').closest('tr')!;
    expect(row).toHaveAttribute('data-returned', 'true');
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' });
    // Only the named row - not the whole page.
    expect(screen.getByText('Alpha').closest('tr')).not.toHaveAttribute('data-returned', 'true');
  });

  it('clears the highlight on the next pointerdown, anywhere', () => {
    vi.spyOn(Element.prototype, 'scrollIntoView');
    setLocationSearch('from=a2');

    render(<ListHarness />);
    expect(screen.getByText('Beta').closest('tr')).toHaveAttribute('data-returned', 'true');

    fireEvent.pointerDown(document.body);

    expect(screen.getByText('Beta').closest('tr')).not.toHaveAttribute('data-returned', 'true');
  });

  it('clears the highlight on the next keydown too, anywhere (S5/S7, M5 review run 1)', () => {
    vi.spyOn(Element.prototype, 'scrollIntoView');
    setLocationSearch('from=a2');

    render(<ListHarness />);
    expect(screen.getByText('Beta').closest('tr')).toHaveAttribute('data-returned', 'true');

    // A keyboard reader tabbing through the page never fires pointerdown at all.
    fireEvent.keyDown(document.body, { key: 'Tab' });

    expect(screen.getByText('Beta').closest('tr')).not.toHaveAttribute('data-returned', 'true');
  });

  it('is a no-op when the from id is not on the current page', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    setLocationSearch('from=not-on-this-page');

    render(<ListHarness />);

    expect(scrollIntoView).not.toHaveBeenCalled();
    for (const label of ['Alpha', 'Beta', 'Gamma']) {
      expect(screen.getByText(label).closest('tr')).not.toHaveAttribute('data-returned', 'true');
    }
  });

  it('a row that mounts AFTER the clearing event does not re-arm the highlight (S5/S7, M5 review run 1)', () => {
    // The bug this guards: `returnedFromId` used to be read PER ROW, each with its
    // OWN `cleared` state and its OWN document listener. A row that mounted after
    // the reader had already dismissed the highlight (e.g. a later page's rows, or
    // - as here - a row that simply was not on the page yet) started with
    // `cleared: false` all over again and registered a fresh listener, so it
    // highlighted and scrolled on ITS OWN mount even though the reader had already
    // moved on. Lifting the resolve to once-per-grid means every row, however late
    // it mounts, reads the SAME already-cleared value.
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    setLocationSearch('from=a2');

    const { rerender } = render(<ListHarness rows={[ROWS[0]]} />);
    // `a2` (Beta) is not on the page yet, so nothing highlights or scrolls.
    expect(scrollIntoView).not.toHaveBeenCalled();

    fireEvent.pointerDown(document.body);

    // `a2` mounts now, for the first time, AFTER the clearing event.
    rerender(<ListHarness rows={ROWS} />);

    expect(screen.getByText('Beta').closest('tr')).not.toHaveAttribute('data-returned', 'true');
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});

describe('LinkableBodyRow rewrites the list\'s own history entry before pushing (M5-07 browser Back gap)', () => {
  /**
   * A grid with pagination/sorting state that is NOT the defaults, so the
   * asserted URL proves the real table state made it through rather than
   * coincidentally matching `buildDataGridParams`'s page-1 defaults.
   */
  function PagedHarness() {
    const table = useReactTable({
      data: ROWS,
      columns: COLUMNS,
      getRowId: (r) => r.id,
      getCoreRowModel: getCoreRowModel(),
      initialState: {
        pagination: { pageIndex: 2, pageSize: 25 },
        sorting: [{ id: 'name', desc: true }],
      },
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

  it('click: replaceState fires once, before push, naming the list path + page/limit/sort/dir + from=<id>, preserving history.state', () => {
    setLocationSearch('');
    const priorState = window.history.state;
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState');

    render(<PagedHarness />);
    fireEvent.click(screen.getByText('Beta'));

    expect(replaceStateSpy).toHaveBeenCalledTimes(1);
    const [state, , url] = replaceStateSpy.mock.calls[0];
    // The existing history.state object is passed through unchanged, not
    // replaced or dropped - Next's own router state on this entry survives.
    expect(state).toBe(priorState);

    const replaced = new URL(url as string, 'http://localhost');
    expect(replaced.pathname).toBe('/order-management/orders');
    expect(replaced.searchParams.get('page')).toBe('3');
    expect(replaced.searchParams.get('limit')).toBe('25');
    expect(replaced.searchParams.get('sort')).toBe('name');
    expect(replaced.searchParams.get('dir')).toBe('desc');
    expect(replaced.searchParams.get('from')).toBe('a2');

    // Call order: the list's own entry is rewritten BEFORE the push away from it.
    expect(replaceStateSpy.mock.invocationCallOrder[0]).toBeLessThan(
      push.mock.invocationCallOrder[0],
    );
  });

  it('middle-click (new tab, window.open) does not touch the list\'s history entry', () => {
    setLocationSearch('');
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState');
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(<PagedHarness />);
    fireEvent(
      screen.getByText('Beta').closest('tr')!,
      new MouseEvent('auxclick', { bubbles: true, cancelable: true, button: 1 }),
    );

    expect(open).toHaveBeenCalledTimes(1);
    expect(replaceStateSpy).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it('keyboard Enter open rewrites the list history entry the same as a click', () => {
    setLocationSearch('');
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState');

    render(<PagedHarness />);
    const row = screen.getByText('Beta').closest('tr')!;
    fireEvent.keyDown(row, { key: 'Enter' });

    expect(replaceStateSpy).toHaveBeenCalledTimes(1);
    const url = replaceStateSpy.mock.calls[0][2] as string;
    const replaced = new URL(url, 'http://localhost');
    expect(replaced.searchParams.get('from')).toBe('a2');
    expect(push).toHaveBeenCalledTimes(1);
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
