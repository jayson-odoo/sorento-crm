/**
 * PanelDataGrid keeps its page across a data update.
 *
 * TanStack's `autoResetPageIndex` defaults to ON whenever `manualPagination` is
 * off, and it fires on every new `data` array reference - a draft save patches
 * the board cache (new `rows` array), a Confirm refetches it (new array again),
 * and either one snapped `pageIndex` back to 0 even though the list view never
 * touched the page itself. See PLAN-panel-datagrid-keep-page.md.
 *
 * The reset itself runs off a microtask TanStack queues internally (`_queue`),
 * not synchronously inside the render that changed `rows` - so every assertion
 * after a rerender awaits one `act` tick first, the same pattern
 * `data-grid.listing-key.test.tsx` uses to settle table-internal effects.
 */
import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ColumnDef } from '@tanstack/react-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/fulfilment-planning',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { PanelDataGrid } from './PanelDataGrid';

interface Row {
  id: string;
  name: string;
}

function makeRows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `r${index + 1}`,
    name: `Line ${index + 1}`,
  }));
}

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

function panel(rows: Row[]) {
  return (
    <PanelDataGrid<Row>
      title="Lines"
      columns={COLUMNS}
      rows={rows}
      getRowId={(row) => row.id}
      listingKey="test.panel-data-grid.keep-page"
      emptyTitle="No lines"
      searchPlaceholder="Search"
      searchOf={(row) => row.name}
      pageSize={25}
    />
  );
}

// Settles the microtask TanStack schedules for `autoResetPageIndex`.
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('PanelDataGrid keeps its page across a data update', () => {
  it('stays on page 3 when rows re-render with a new array of the same length', async () => {
    const { rerender } = render(panel(makeRows(60)));
    await flush();

    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(screen.getByText('Line 60')).toBeInTheDocument();

    const updated = makeRows(60);
    updated[0] = { ...updated[0], name: 'Line 1 edited' };

    rerender(panel(updated));
    await flush();

    expect(screen.getByText('Line 60')).toBeInTheDocument();
    expect(screen.queryByText('Line 1 edited')).not.toBeInTheDocument();
  });

  it('clamps to the last page when a data update shrinks the row count', async () => {
    const { rerender } = render(panel(makeRows(60)));
    await flush();

    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(screen.getByText('Line 60')).toBeInTheDocument();

    rerender(panel(makeRows(30)));
    await flush();

    // 30 rows at pageSize 25 has only 2 pages (index 0 and 1); page index 2 no
    // longer exists, so the last page (rows 26-30) shows, never an empty table.
    expect(screen.getByText('Line 26')).toBeInTheDocument();
    expect(screen.getByText('Line 30')).toBeInTheDocument();
    expect(screen.queryByText('Line 1')).not.toBeInTheDocument();

    // The clamp painted page 2, but a stale REAL pagination state (still 2)
    // would make Previous a dead press - `previousPage()` steps relative to
    // the real state, not what is on screen. One press must land on page 1.
    fireEvent.click(screen.getByRole('button', { name: /previous page/i }));
    await flush();

    expect(screen.getByText('Line 1')).toBeInTheDocument();
  });

  it('still returns to page 1 when the search box is used', async () => {
    render(panel(makeRows(60)));
    await flush();

    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(screen.getByText('Line 60')).toBeInTheDocument();

    // The needle matches every row ("Line") rather than narrowing to one page
    // on its own - page 3 still exists after filtering, so only the search
    // box's OWN explicit reset (not the row-count clamp) can bring this back
    // to page 1. A needle that also narrowed the row count to one page would
    // pass here even with that reset deleted (SF-review B1 kill test).
    fireEvent.change(screen.getByPlaceholderText('Search'), { target: { value: 'Line' } });
    await flush();

    expect(screen.queryByText('Line 60')).not.toBeInTheDocument();
    expect(screen.getByText('Line 1')).toBeInTheDocument();
  });

  it('resets to page 1 when pageResetKey changes, and keeps the page when only rows changes with the same key', async () => {
    function Wrapper({ pageResetKey, rows }: { pageResetKey: string; rows: Row[] }) {
      return (
        <PanelDataGrid<Row>
          title="Lines"
          columns={COLUMNS}
          rows={rows}
          getRowId={(row) => row.id}
          listingKey="test.panel-data-grid.keep-page"
          emptyTitle="No lines"
          pageSize={25}
          pageResetKey={pageResetKey}
        />
      );
    }

    const { rerender } = render(<Wrapper pageResetKey="" rows={makeRows(60)} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(screen.getByText('Line 60')).toBeInTheDocument();

    // A parent-side filter changing its own key resets the page, same rows.
    rerender(<Wrapper pageResetKey="needle" rows={makeRows(60)} />);
    await flush();

    expect(screen.getByText('Line 1')).toBeInTheDocument();
    expect(screen.queryByText('Line 60')).not.toBeInTheDocument();

    // Back on page 3, a data update under the SAME key keeps the page.
    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(screen.getByText('Line 60')).toBeInTheDocument();

    const updated = makeRows(60);
    updated[0] = { ...updated[0], name: 'Line 1 edited' };
    rerender(<Wrapper pageResetKey="needle" rows={updated} />);
    await flush();

    expect(screen.getByText('Line 60')).toBeInTheDocument();
  });
});
