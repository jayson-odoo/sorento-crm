/**
 * A grid inside another grid's body renders unbounded and non-sticky.
 *
 * The rule the M5-05 defaults could not state on their own: a sticky header needs a
 * bounded scrollport to stick inside, so every grid gets one - and a grid rendered in
 * ANOTHER grid's body then opens a second scrollport inside the first. Measured on the
 * fulfilment board's cell breakdown dialog at 1440x900, that stacked four
 * `overflow-y: auto` boxes on one tab, all four overflowing at once, with the innermost
 * table's header sitting 33px above the visible top of the box clipping it. The reader's
 * report was "the header is half hidden and I can't scroll".
 *
 * Fourteen call sites already said `scrollerMaxHeight: false` by hand, one comment each.
 * The fifteenth forgot, and shipped to production. So it is a DEFAULT now, read off
 * `DataGridContext`: a grid that finds an enclosing grid renders unbounded and drops the
 * sticky header, unless the caller names a value.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import {
  useReactTable,
  getCoreRowModel,
  type ColumnDef,
} from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

type Outer = { id: string; name: string };
type Inner = { id: string; document: string };

const OUTER_ROWS: Outer[] = [{ id: 'loc-1', name: 'Site pool subtotal' }];
const INNER_ROWS: Inner[] = [
  { id: 'doc-1', document: 'SO218168' },
  { id: 'doc-2', document: 'SO374956' },
];

const INNER_COLUMNS: ColumnDef<Inner>[] = [
  { id: 'document', accessorKey: 'document', header: 'Document', size: 200 },
];

/** The grid that opens inside the outer grid's expanded row. */
function InnerGrid({
  tableLayout,
}: {
  tableLayout?: Parameters<typeof DataGrid<Inner>>[0]['tableLayout'];
}) {
  const table = useReactTable({
    data: INNER_ROWS,
    columns: INNER_COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <div data-testid="inner-grid">
      <DataGrid
        table={table}
        recordCount={INNER_ROWS.length}
        listingKey={null}
        tableLayout={tableLayout}
      >
        <DataGridTable />
      </DataGrid>
    </div>
  );
}

/**
 * The outer grid, with the inner one in `meta.expandedContent`. Rendering it always
 * (rather than behind a real row expansion) keeps the test about the CONTEXT, which is
 * the same either way - `DataGridTable` draws expanded content inside this provider.
 */
function Nested({
  innerTableLayout,
}: {
  innerTableLayout?: Parameters<typeof DataGrid<Inner>>[0]['tableLayout'];
}) {
  const columns: ColumnDef<Outer>[] = [
    {
      id: 'name',
      accessorKey: 'name',
      header: 'Location',
      size: 300,
      meta: {
        expandedContent: () => <InnerGrid tableLayout={innerTableLayout} />,
      },
    },
  ];
  const table = useReactTable({
    data: OUTER_ROWS,
    columns,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <div data-testid="outer-grid">
      <DataGrid table={table} recordCount={OUTER_ROWS.length}>
        <DataGridTable />
        {/* The expansion, rendered through the same column meta the grid uses. */}
        {columns[0].meta?.expandedContent?.(OUTER_ROWS[0])}
      </DataGrid>
    </div>
  );
}

const scrollerOf = (root: HTMLElement) =>
  root.querySelector('[data-slot="data-grid-scroller"]') as HTMLElement;
const theadOf = (root: HTMLElement) =>
  root.querySelector('thead') as HTMLElement;

describe('a grid nested in another grid renders unbounded and non-sticky', () => {
  it('gives the inner grid no bounded scrollport and no sticky header', () => {
    const { getByTestId } = render(<Nested />);
    const inner = getByTestId('inner-grid');

    expect(scrollerOf(inner).className).not.toMatch(/max-h-/);
    expect(scrollerOf(inner).className).not.toContain('overflow-y-auto');
    expect(theadOf(inner).className).not.toContain('sticky');
  });

  it('leaves the OUTER grid with both - it is the one that owns the scrollport', () => {
    const { getByTestId } = render(<Nested />);
    // The outer grid's own scroller is the first one in its subtree; the inner grid
    // renders after it, inside the same container.
    const outer = getByTestId('outer-grid');
    const outerScroller = scrollerOf(outer);
    const outerThead = theadOf(outer);

    expect(outerScroller.className).toContain('max-h-(--grid-max-h)');
    expect(outerScroller.className).toContain('overflow-y-auto');
    expect(outerThead.className).toContain('sticky');
    expect(outerThead.className).toContain('top-0');
  });

  it('a nested grid that names headerSticky keeps it', () => {
    const { getByTestId } = render(
      <Nested
        innerTableLayout={{ headerSticky: true, scrollerMaxHeight: '16rem' }}
      />,
    );
    const inner = getByTestId('inner-grid');

    expect(theadOf(inner).className).toContain('sticky');
    expect(scrollerOf(inner).className).toContain('16rem');
  });

  it('a nested grid that names only its own bound keeps a sticky header with it', () => {
    // The popover mini-table on a complaint's fulfilment orders is exactly this: it caps
    // itself at 16rem and wants the header to stay put inside that window.
    const { getByTestId } = render(
      <Nested innerTableLayout={{ scrollerMaxHeight: '16rem' }} />,
    );
    const inner = getByTestId('inner-grid');

    expect(scrollerOf(inner).className).toContain('16rem');
    expect(theadOf(inner).className).toContain('sticky');
  });

  it('an UNNESTED grid that opts its bound off drops the sticky header with it', () => {
    // Not a nesting rule, the same rule read the other way: the class claims the header
    // pins to something, and with no bounded scrollport there is nothing to pin to.
    const table = renderStandalone({ scrollerMaxHeight: false });
    expect(theadOf(table).className).not.toContain('sticky');
  });
});

function renderStandalone(
  tableLayout: Parameters<typeof DataGrid<Inner>>[0]['tableLayout'],
) {
  const { getByTestId } = render(<InnerGrid tableLayout={tableLayout} />);
  return getByTestId('inner-grid');
}
