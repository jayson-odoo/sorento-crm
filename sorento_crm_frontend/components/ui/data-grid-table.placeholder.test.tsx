/**
 * M4 list latency - a grid that still has rows dims them instead of showing a
 * skeleton.
 *
 * The first version of this file drove `isPlaceholderData` as a boolean prop,
 * and passed while every real list was broken: with `keepPreviousData`,
 * TanStack reports the window as `isLoading: false, isFetching: true,
 * isPlaceholderData: true`, so the primitive's `isLoading && rows.length > 0`
 * clause is false for its whole duration and nothing dimmed. A prop-level
 * harness cannot see that, because it never asks the query what it reports.
 *
 * So the first suite below runs the real thing: a `useQuery` with
 * `...LIST_QUERY_OPTIONS` inside a `QueryClientProvider`, paged by changing the
 * query key, with the second page held open on a deferred promise. The dim is
 * asserted DURING that window and gone after it.
 *
 * The second suite keeps the `isLoading`-with-rows case: that clause still
 * serves the grids whose call site feeds `isLoading || isFetching`, and the
 * skeleton gate ("no rows to show", not "loading") lives in the primitive so
 * all 186 grids inherit it.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
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

const PAGE_ONE: Row[] = [{ id: 'p-1', name: 'Ergonomic Chair' }];
const PAGE_TWO: Row[] = [{ id: 'p-2', name: 'Standing Desk' }];
const DATA = PAGE_ONE;

const COLUMNS: ColumnDef<Row>[] = [
  {
    id: 'name',
    accessorKey: 'name',
    header: 'Name',
    size: 400,
    meta: { skeleton: <span data-testid="cell-skeleton" /> },
  },
];

const EMPTY: Row[] = [];

/** A list exactly as the app builds one: paged query key, LIST_QUERY_OPTIONS, one grid. */
function ListHarness({ pageTwo }: { pageTwo: Promise<Row[]> }) {
  const [page, setPage] = React.useState(0);
  const { data, isLoading, isPlaceholderData } = useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['rows', page],
    queryFn: () => (page === 0 ? Promise.resolve(PAGE_ONE) : pageTwo),
  });

  const table = useReactTable({
    data: data ?? EMPTY,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    manualPagination: true,
    pageCount: 2,
    initialState: { pagination: { pageIndex: 0, pageSize: 25 } },
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <>
      <button type="button" onClick={() => setPage(1)}>
        Next
      </button>
      <DataGrid
        table={table}
        recordCount={2}
        isLoading={isLoading}
        isPlaceholderData={isPlaceholderData}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <DataGridTable />
      </DataGrid>
    </>
  );
}

function renderList(pageTwo: Promise<Row[]>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ListHarness pageTwo={pageTwo} />
    </QueryClientProvider>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('a real LIST_QUERY_OPTIONS query dims the grid while its next page loads (M4-02)', () => {
  it('dims during the placeholder window and undims once the page arrives', async () => {
    const next = deferred<Row[]>();
    const { container } = renderList(next.promise);
    const tbody = () => container.querySelector('tbody')!;

    await screen.findByText('Ergonomic Chair');
    expect(tbody().className).not.toContain('opacity-60');

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    // The window itself: previous rows on screen, no skeleton, body dimmed on
    // the house tokens. `isLoading` is false throughout, which is the whole
    // reason the flag has to be forwarded.
    await waitFor(() => expect(tbody().className).toContain('opacity-60'));
    expect(tbody().className).toContain('transition-opacity');
    expect(tbody().className).toContain('duration-(--duration-fast)');
    expect(tbody().className).toContain('ease-(--ease-standard)');
    expect(screen.getByText('Ergonomic Chair')).toBeInTheDocument();
    expect(screen.queryAllByTestId('cell-skeleton')).toHaveLength(0);

    next.resolve(PAGE_TWO);

    await screen.findByText('Standing Desk');
    await waitFor(() => expect(tbody().className).not.toContain('opacity-60'));
  });

  it('does not dim the first load - there is nothing on screen to dim yet', async () => {
    const { container } = renderList(new Promise<Row[]>(() => {}));

    expect(container.querySelector('tbody')!.className).not.toContain('opacity-60');
    expect(screen.queryAllByTestId('cell-skeleton').length).toBeGreaterThan(0);

    await screen.findByText('Ergonomic Chair');
  });
});

function Harness({
  isLoading = false,
  rows = DATA,
}: {
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
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

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
