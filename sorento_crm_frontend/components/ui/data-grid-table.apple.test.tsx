/**
 * S1-05, S1-06, S1-07 - the grid on a phone, and the row as a link.
 *
 * `data-grid.tsx` had no horizontal scroll container, so a `table-fixed w-full`
 * table squeezed its columns into whatever width it was given: Stock showed one
 * column at 375, Categories crushed six, and a Complaints row could not be
 * opened at all. And 26 lists had a detail route with no way to reach it from
 * the row.
 *
 * jsdom has no layout, so what is pinned here is the mechanism: the scroller
 * exists, the table may exceed it, the row carries the list state in its href,
 * and the grid's own defaults reach the table instance.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef, type Table } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';
import { buildSelectColumn } from './data-grid-select-column';

const push = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/order-management/orders',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string; total: string };

const DATA: Row[] = [
  { id: 'a1', name: 'Alpha', total: '10' },
  { id: 'b2', name: 'Beta', total: '20' },
];

const COLUMNS: ColumnDef<Row>[] = [
  buildSelectColumn<Row>(),
  { id: 'name', accessorKey: 'name', header: 'Name', size: 900 },
  { id: 'total', accessorKey: 'total', header: 'Total', size: 900 },
  {
    id: 'actions',
    header: 'Actions',
    size: 200,
    // A real listing row is not inert text: it carries an action button and,
    // on the expanded lists, an inline editor. Both are inside the row, so the
    // row-as-link has to tell them apart from the row itself.
    cell: ({ row }) => (
      <div>
        <button type="button">Edit {row.original.name}</button>
        <input aria-label={`Note for ${row.original.name}`} defaultValue="" />
      </div>
    ),
  },
];

function setMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function Harness({
  rowHref,
  onRowClick,
  onTable,
  tableLayout,
}: {
  rowHref?: (row: Row) => string;
  onRowClick?: (row: Row) => void;
  onTable?: (table: Table<Row>) => void;
  tableLayout?: React.ComponentProps<typeof DataGrid<Row>>['tableLayout'];
}) {
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    enableRowSelection: true,
    initialState: {
      pagination: { pageIndex: 2, pageSize: 25 },
      sorting: [{ id: 'name', desc: true }],
      globalFilter: 'alp',
    },
    getCoreRowModel: getCoreRowModel(),
  });
  onTable?.(table);
  return (
    <DataGrid
      table={table}
      recordCount={DATA.length}
      isLoading={false}
      rowHref={rowHref}
      onRowClick={onRowClick}
      tableLayout={tableLayout ?? { width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

beforeEach(() => {
  push.mockClear();
  setMatchMedia(false);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe('DataGrid scrolls on a phone (S1-05)', () => {
  it('S1-05: the grid owns a horizontal scroll container, so the page never scrolls sideways', () => {
    render(<Harness />);
    const scroller = document.querySelector('[data-slot="data-grid-scroller"]');

    expect(scroller).not.toBeNull();
    expect(scroller).toHaveClass('overflow-x-auto');
    expect(scroller).toHaveClass('overscroll-x-contain');
  });

  it('S1-05: the table may exceed the container instead of squeezing its columns', () => {
    render(<Harness />);
    expect(document.querySelector('[data-slot="data-grid-table"]')).toHaveClass('min-w-max');
  });

  it('S1-05: the right edge fades only while there is more to the right', () => {
    render(<Harness />);
    const scroller = document.querySelector('[data-slot="data-grid-scroller"]');

    // jsdom reports every width as 0, i.e. "it fits", so no fade is drawn.
    expect(scroller).toHaveAttribute('data-fade', 'false');
    expect(document.querySelector('[data-slot="data-grid-fade"]')).toBeNull();
  });

  it('S1-05: under sm the first non-checkbox column is pinned left', () => {
    setMatchMedia(true);
    render(<Harness />);

    const nameHeader = screen.getByText('Name').closest('th');
    expect(nameHeader).toHaveAttribute('data-pinned', 'left');

    // The checkbox column is not the identifier, so it is not the pinned one.
    const selectHeader = screen.getByLabelText('Select all rows on this page').closest('th');
    expect(selectHeader).not.toHaveAttribute('data-pinned');
  });

  it('S1-05: at desktop width nothing is pinned', () => {
    render(<Harness />);
    expect(screen.getByText('Name').closest('th')).not.toHaveAttribute('data-pinned');
  });
});

describe('A row is a link (S1-06)', () => {
  it('S1-06: a click on the row opens the href', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent.click(screen.getByText('Alpha'));

    expect(push).toHaveBeenCalledTimes(1);
    expect(push.mock.calls[0][0]).toContain('/order-management/orders/a1');
  });

  it('S1-06: the href carries the page, limit, sort and search the list was showing', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent.click(screen.getByText('Alpha'));

    const href = push.mock.calls[0][0] as string;
    const params = new URLSearchParams(href.split('?')[1]);
    expect(params.get('page')).toBe('3');
    expect(params.get('limit')).toBe('25');
    expect(params.get('sort')).toBe('name');
    expect(params.get('dir')).toBe('desc');
    expect(params.get('query')).toBe('alp');
  });

  it('S1-06: a filter the list keeps outside the table survives on the href', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}?warehouse=HQ`} />);

    fireEvent.click(screen.getByText('Alpha'));

    const params = new URLSearchParams((push.mock.calls[0][0] as string).split('?')[1]);
    expect(params.get('warehouse')).toBe('HQ');
    expect(params.get('page')).toBe('3');
  });

  it('S1-06: the row is reachable by keyboard', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);
    const row = screen.getByText('Alpha').closest('tr')!;

    expect(row).toHaveAttribute('role', 'link');
    expect(row).toHaveAttribute('tabindex', '0');

    fireEvent.keyDown(row, { key: 'Enter' });
    expect(push).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(row, { key: ' ' });
    expect(push).toHaveBeenCalledTimes(2);
  });

  it('S1-06: a middle click opens the record in a new tab', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent(
      screen.getByText('Alpha').closest('tr')!,
      new MouseEvent('auxclick', { bubbles: true, cancelable: true, button: 1 }),
    );

    expect(open).toHaveBeenCalledTimes(1);
    expect(open.mock.calls[0][0]).toContain('/order-management/orders/a1');
    expect(push).not.toHaveBeenCalled();
  });

  it('S1-06: a control inside the row keeps its own click - the row does not steal it', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit Alpha' }));

    // Without this, every action button on all 79 action columns would have to
    // remember stopPropagation, and the one that forgot would navigate away
    // mid-action.
    expect(push).not.toHaveBeenCalled();
  });

  it('S1-06: typing in an inline cell editor does not navigate', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);
    const input = screen.getByLabelText('Note for Alpha');

    fireEvent.keyDown(input, { key: ' ' });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(push).not.toHaveBeenCalled();
  });

  it('S1-06: Space on the row checkbox ticks it without opening the record', () => {
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);
    const checkbox = screen.getAllByLabelText('Select row')[0];

    fireEvent.keyDown(checkbox, { key: ' ' });
    fireEvent.click(checkbox);

    // Ticking a row is not opening it. (The browser turns Space into the click;
    // jsdom does not, so the click is fired here as well.)
    expect(push).not.toHaveBeenCalled();
    expect(checkbox).toHaveAttribute('data-state', 'checked');
  });

  it('S1-06: a modifier click opens a new tab instead of leaving the list', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    for (const modifier of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }]) {
      fireEvent.click(screen.getByText('Alpha'), modifier);
    }

    expect(open).toHaveBeenCalledTimes(3);
    expect(push).not.toHaveBeenCalled();
  });

  it('S1-06: a new tab carries the deploy base path, which the router adds by itself', () => {
    vi.stubEnv('NEXT_PUBLIC_BASE_PATH', '/crm');
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<Harness rowHref={(row) => `/order-management/orders/${row.id}`} />);

    fireEvent.click(screen.getByText('Alpha'), { metaKey: true });
    expect(open.mock.calls[0][0]).toContain('/crm/order-management/orders/a1');

    // ...while an in-app push must NOT carry it, or the base path lands twice.
    fireEvent.click(screen.getByText('Alpha'));
    expect(push.mock.calls[0][0]).not.toContain('/crm/');
  });

  it('S1-06: a grid with neither rowHref nor onRowClick has no pointer cursor and no role', () => {
    render(<Harness />);
    const row = screen.getByText('Alpha').closest('tr')!;

    expect(row).not.toHaveClass('cursor-pointer');
    expect(row).not.toHaveAttribute('role', 'link');
  });

  it('S1-06: onRowClick still works for lists that edit in a lightbox', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);

    fireEvent.click(screen.getByText('Alpha'));

    expect(onRowClick).toHaveBeenCalledWith(DATA[0]);
    expect(push).not.toHaveBeenCalled();
  });
});

describe('DataGrid defaults (S1-07)', () => {
  it('S1-07: columnResizeMode is onChange even when the list did not ask', () => {
    let table: Table<Row> | undefined;
    render(<Harness onTable={(t) => (table = t)} />);

    expect(table!.options.columnResizeMode).toBe('onChange');
  });

  /*
    S1-07's "the header is sticky by default" clause is DEFERRED to S4.

    Turning it on here was inert and actively harmful. `overflow-x-auto` on the
    new scroller makes that div the scrollport, and it never scrolls vertically,
    so `sticky top-0` on the thead has nothing to stick against - while the 29
    lists that DO get a sticky header today (their own bounded-height ScrollArea)
    had a second, competing sticky context introduced above them. A sticky header
    needs the grid to own a bounded height, which is S4's mobile/layout work.
  */
  it('S1-07: the header is not sticky unless the list asks (S4 defers the default)', () => {
    render(<Harness />);
    expect(document.querySelector('thead')).not.toHaveClass('sticky');
  });

  it('S1-07: a list that asks for a sticky header still gets one', () => {
    render(<Harness tableLayout={{ width: 'fixed', columnsResizable: true, headerSticky: true }} />);
    const head = document.querySelector('thead');

    expect(head).toHaveClass('sticky');
    expect(head).toHaveClass('top-0');
  });

  it('S1-07: numerals are tabular so figures line up down a column', () => {
    render(<Harness />);
    expect(document.querySelector('[data-slot="data-grid-table"]')).toHaveClass('tabular-nums');
  });

  it('S1-07: the resize handle takes pointer capture', () => {
    const setPointerCapture = vi.fn();
    Element.prototype.setPointerCapture = setPointerCapture;

    render(<Harness />);
    const handle = document.querySelector('.cursor-col-resize')!;

    fireEvent.pointerDown(handle, { pointerId: 7 });

    expect(setPointerCapture).toHaveBeenCalledWith(7);
  });
});
