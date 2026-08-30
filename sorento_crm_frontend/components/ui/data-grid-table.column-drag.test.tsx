/**
 * Column drag-and-drop, including the column a phone pins (S5 fix round 2).
 *
 * The bug this pins down: `getPinningStyles` was spread AFTER dnd-kit's style
 * on every cell, so a PINNED column carried `position: sticky` while it was
 * being dragged. Sticky wins over dnd-kit's `position: relative`, the transform
 * had nowhere to apply, and the column simply did not move. That is not an edge
 * case: under `sm` the grid pins the identifier column for every list, so on a
 * phone the first column a user would reach for was the one column that could
 * not be reordered.
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

function Harness() {
  const table = useReactTable({
    data: ROWS,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
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
  setMatchMedia(false);
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
    // Under sm the grid pins the first non-checkbox column by itself, so this is
    // the ordinary phone case rather than an opt-in.
    setMatchMedia(true);
    render(<Harness />);

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
