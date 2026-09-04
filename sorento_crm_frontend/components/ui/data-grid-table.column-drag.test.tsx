/**
 * Column drag-and-drop, including a pinned column (S5 fix round 2).
 *
 * The bug this pins down: `getPinningStyles` was spread AFTER dnd-kit's style
 * on every cell, so a PINNED column carried `position: sticky` while it was
 * being dragged. Sticky wins over dnd-kit's `position: relative`, the transform
 * had nowhere to apply, and the column simply did not move. The phone pin that
 * first exposed it is gone (the user chose to unpin, 2026-08-30), but a list
 * that pins a column on purpose still has to be able to reorder it.
 *
 * jsdom has no layout, so every `getBoundingClientRect` is zeros and dnd-kit's
 * collision detection has nothing to sort. The stub below gives each cell the
 * geometry its inline width already declares, which is what turns a synthetic
 * mouse drag into a real reorder.
 *
 * Which assertion catches which fault: the reorder assertions cover "a drag
 * works at all", and the MID-DRAG `position` assertion is the one that goes red
 * on the sticky regression. jsdom does not implement sticky positioning, so the
 * reorder still lands there even while a real browser has the column nailed in
 * place - the inline style is the only honest witness available.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef, type Table } from '@tanstack/react-table';

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

type Row = { id: string; name: string; total: string; status: string };

const ROWS: Row[] = [{ id: '1', name: 'Alpha', total: '10', status: 'Open' }];

const COLUMN_WIDTH = 200;

const COLUMNS: ColumnDef<Row>[] = [
  { id: 'name', accessorKey: 'name', header: 'Name', size: COLUMN_WIDTH },
  { id: 'total', accessorKey: 'total', header: 'Total', size: COLUMN_WIDTH },
  { id: 'status', accessorKey: 'status', header: 'Status', size: COLUMN_WIDTH },
];

/**
 * Lays the cells of every row out left to right at their declared width, so
 * dnd-kit's `closestCenter` has real centres to compare. Without it every rect
 * is `0,0,0,0` and the drop target is whichever droppable registered first.
 */
function makeRect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    x: left,
    y: top,
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height,
    toJSON: () => ({}),
  } as DOMRect;
}

const GRID_WIDTH = COLUMNS.length * COLUMN_WIDTH;

function stubCellGeometry() {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    if (this instanceof HTMLTableCellElement) {
      const left = this.cellIndex * COLUMN_WIDTH;
      const top = this.closest('thead') ? 0 : 40;
      return makeRect(left, top, COLUMN_WIDTH, 40);
    }
    // Everything else (the table, the scroller, the div `restrictToParentElement`
    // clamps against) is the full grid. A zero-size parent clamps every drag
    // transform to nothing, and the drag silently ends where it began.
    return makeRect(0, 0, GRID_WIDTH, 80);
  });
}

let latest: Table<Row> | null = null;

function Harness({ pinned }: { pinned?: boolean } = {}) {
  const table = useReactTable({
    data: ROWS,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
    // What a list that opts into pinning does. Nothing pins a column by itself
    // any more, on a phone or anywhere else.
    initialState: pinned ? { columnPinning: { left: ['name'], right: [] } } : undefined,
  });
  latest = table;
  return (
    <DataGrid
      table={table}
      recordCount={ROWS.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsDraggable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

/** The header cell of a column, by its visible label. */
function headerCell(label: string): HTMLTableCellElement {
  return screen.getByText(label).closest('th') as HTMLTableCellElement;
}

/** The order the header row is actually rendered in. */
function renderedOrder(): string[] {
  return Array.from(document.querySelectorAll('thead th')).map((th) =>
    (th.textContent ?? '').trim(),
  );
}

/**
 * A mouse drag from one column header to another. `MouseSensor` has a 6px
 * activation distance, so the first move only starts the drag.
 */
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

async function startDrag(fromLabel: string, toCentre: number) {
  const handle = headerCell(fromLabel).querySelector(
    '[aria-label="Drag column to reorder"]',
  ) as HTMLElement;
  const from = headerCell(fromLabel).cellIndex * COLUMN_WIDTH + COLUMN_WIDTH / 2;

  fireEvent.mouseDown(handle, { button: 0, clientX: from, clientY: 20 });
  fireEvent.mouseMove(document, { clientX: from + 10, clientY: 20 });
  await settle();
  fireEvent.mouseMove(document, { clientX: toCentre, clientY: 20 });
  await settle();
}

async function drop() {
  fireEvent.mouseUp(document);
  await settle();
}

beforeEach(() => {
  latest = null;
  stubCellGeometry();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Column drag-and-drop', () => {
  it('a drag reorders the columns', async () => {
    render(<Harness />);
    expect(renderedOrder()).toEqual(['Name', 'Total', 'Status']);

    await startDrag('Name', 2 * COLUMN_WIDTH + COLUMN_WIDTH / 2);
    await drop();

    expect(latest?.getState().columnOrder).toEqual(['total', 'status', 'name']);
    expect(renderedOrder()).toEqual(['Total', 'Status', 'Name']);
  });

  it('the PINNED column drags too - sticky must not beat the drag transform', async () => {
    render(<Harness pinned />);

    const name = headerCell('Name');
    expect(name).toHaveAttribute('data-pinned', 'left');
    expect(name.style.position).toBe('sticky');

    await startDrag('Name', 2 * COLUMN_WIDTH + COLUMN_WIDTH / 2);

    // Mid-drag: the dnd transform owns the cell, or it cannot move at all.
    const dragging = headerCell('Name');
    expect(dragging.style.position).toBe('relative');
    expect(dragging.style.transform).not.toBe('');

    await drop();

    expect(latest?.getState().columnOrder).toEqual(['total', 'status', 'name']);
    // Dropped, and the column is sticky again - the pin survived the drag.
    expect(headerCell('Name').style.position).toBe('sticky');
  });
});

/**
 * A pinned column carries the `--z-sticky-content` token (css/config.reui.css) a bare
 * `z-1`/`z-10` used to, which keeps it below the app shell's `--z-header`/`--z-sidebar` -
 * so the collapsed sidebar's hover flyout renders over a frozen column instead of under it
 * - see FulfilmentBoardMatrix and the sibling schedule matrices for the same fix on their
 * own custom pinned cells.
 *
 * The sticky HEADER carries the `-corner` step instead of that same token (S3, M5 review
 * run 1): the two used to share `--z-sticky-content`, so on any grid with
 * `columnsPinnable: true` a frozen column's own cell painted OVER the sticky header
 * instead of scrolling under it. `-corner` is reserved for a cell pinned on both axes
 * (`css/config.reui.css`), which the header effectively is - sticky on every column, not
 * just a pinned one - so it has to beat a single-axis pinned cell.
 */
describe('Sticky content stays below the app shell', () => {
  it('a pinned column carries the shared sticky-content z token, not a bare number', () => {
    render(<Harness pinned />);

    expect(headerCell('Name').style.zIndex).toBe('var(--z-sticky-content)');
  });

  it('a sticky header carries the CORNER token, above a pinned column\'s own cell', () => {
    function StickyHeaderHarness() {
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
          tableLayout={{ width: 'fixed', headerSticky: true }}
        >
          <DataGridTable />
        </DataGrid>
      );
    }

    render(<StickyHeaderHarness />);

    const headClassName = document.querySelector('thead')?.className;
    expect(headClassName).toContain('z-(--z-sticky-content-corner)');
    expect(headClassName).not.toContain('z-(--z-sticky-content)');
  });
});
