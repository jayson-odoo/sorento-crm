/**
 * M5-05 - the two absolute list rules, as DataGrid DEFAULTS.
 *
 * Sticky header: `data-grid.tsx` defaultProps.tableLayout.headerSticky flips
 * true, so a list gets a sticky `<thead>` without naming the prop. That needs a
 * BOUNDED scroller under it, or the header has nothing to stick inside -
 * `DataGridScroller` (`data-grid-table.tsx`) gets a default max-height class,
 * driven by the `--grid-max-h` token (`css/config.reui.css`), and stays the
 * ONE scroll container for both axes. `tableLayout.scrollerMaxHeight` lets a
 * list override (a Tailwind class string) or opt out (`false`) per list.
 *
 * Movable columns: `columnsMovable` flips true (31 lists already opted in) -
 * it only adds "Move to Left/Right" entries to the column header's own
 * dropdown menu (`data-grid-column-header.tsx`), which brings no DnD provider
 * requirement of its own, unlike the in-header drag path gated by
 * `columnsDraggable` (already true by default).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid, useDataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string };

const DATA: Row[] = [
  { id: 'p-1', name: 'Ergonomic Chair' },
  { id: 'p-2', name: 'Standing Desk' },
  { id: 'p-3', name: 'Task Lamp' },
];

const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

/** Renders nothing visible; exposes what the grid resolved for its layout probe. */
function LayoutProbe() {
  const { props } = useDataGrid();
  return (
    <span
      data-testid="layout-probe"
      data-columns-movable={String(Boolean(props.tableLayout?.columnsMovable))}
      data-columns-resizable={String(Boolean(props.tableLayout?.columnsResizable))}
    />
  );
}

function Harness({
  tableLayout,
}: {
  tableLayout?: Parameters<typeof DataGrid<Row>>[0]['tableLayout'];
}) {
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid table={table} recordCount={DATA.length} isLoading={false} tableLayout={tableLayout}>
      <LayoutProbe />
      <DataGridTable />
    </DataGrid>
  );
}

describe('DataGrid defaults the two absolute list rules (M5-05)', () => {
  it('makes the header sticky by default, with no tableLayout prop', () => {
    const { container } = render(<Harness />);
    const thead = container.querySelector('thead')!;

    expect(thead.className).toContain('sticky');
    expect(thead.className).toContain('top-0');
  });

  it('sticks the header on the CORNER z-step, not the one a pinned body cell uses (S3)', () => {
    // A pinned column's own cell uses `--z-sticky-content` (`data-grid-table.tsx`
    // `getPinningStyles`). If the header used the same step, a frozen column on any of
    // the 30 grids with `columnsPinnable: true` would paint over the sticky header
    // instead of scrolling under it.
    const { container } = render(<Harness />);
    const thead = container.querySelector('thead')!;

    expect(thead.className).toContain('z-(--z-sticky-content-corner)');
    expect(thead.className).not.toContain('z-(--z-sticky-content)');
  });

  it('resolves columnsMovable and columnsResizable true with no tableLayout prop', () => {
    render(<Harness />);
    const probe = screen.getByTestId('layout-probe');

    expect(probe.getAttribute('data-columns-movable')).toBe('true');
    expect(probe.getAttribute('data-columns-resizable')).toBe('true');
  });

  it('bounds the scroller height by default and keeps it the vertical scrollport', () => {
    const { container } = render(<Harness />);
    const scroller = container.querySelector('[data-slot="data-grid-scroller"]')!;

    expect(scroller.className).toContain('max-h-(--grid-max-h)');
    expect(scroller.className).toContain('overflow-y-auto');
    // still the horizontal scrollport - S1-05 has one scroller per grid, not two.
    expect(scroller.className).toContain('overflow-x-auto');
  });

  it('a list can opt both defaults off per list', () => {
    const { container } = render(
      <Harness tableLayout={{ headerSticky: false, scrollerMaxHeight: false }} />,
    );
    const thead = container.querySelector('thead')!;
    const scroller = container.querySelector('[data-slot="data-grid-scroller"]')!;

    expect(thead.className).not.toContain('sticky');
    expect(scroller.className).not.toContain('max-h-(--grid-max-h)');
    expect(scroller.className).not.toContain('overflow-y-auto');
  });

  it('a list can override the scroller max-height with its own class', () => {
    const { container } = render(
      <Harness tableLayout={{ scrollerMaxHeight: 'max-h-[calc(100vh-14rem)]' }} />,
    );
    const scroller = container.querySelector('[data-slot="data-grid-scroller"]')!;

    expect(scroller.className).toContain('max-h-[calc(100vh-14rem)]');
    expect(scroller.className).not.toContain('max-h-(--grid-max-h)');
  });
});
