/**
 * GRID-DRAG-SELECT B-touch (AC-T1..T6): press and hold a row box for 500 ms, then drag.
 * A finger that moves more than 8px before the hold fires is a scroll. On touch the browser
 * captures the pointer to the pressed box, so every pointermove targets that box and the row
 * under the finger comes from document.elementFromPoint (stubbed here: row n sits at y = n*100).
 */
import React from 'react';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';

import { buildSelectColumn } from './data-grid-select-column';

type Rec = { id: string; name: string; locked?: boolean };

const DATA: Rec[] = Array.from({ length: 6 }, (_, index) => ({
  id: `r${index + 1}`,
  name: `Row ${index + 1}`,
}));

function Harness({
  data = DATA,
  initial = {},
  onRowClick,
}: {
  data?: Rec[];
  initial?: RowSelectionState;
  onRowClick?: (id: string) => void;
}) {
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>(initial);
  const columns = React.useMemo<ColumnDef<Rec>[]>(
    () => [
      buildSelectColumn<Rec>({
        rowLabel: (row) => `Select ${row.original.name}`,
        enableRow: (row) => !row.original.locked,
      }),
      { id: 'name', accessorKey: 'name', cell: ({ row }) => <span>{row.original.name}</span> },
    ],
    [],
  );
  const table = useReactTable({
    data,
    columns,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    // Real lists pass the same predicate here as `enableRow` (react-table reads this one).
    enableRowSelection: (row) => !row.original.locked,
  });
  return (
    <div>
      <table>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} data-testid={`tr-${row.id}`} onClick={() => onRowClick?.(row.id)}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} data-testid={`${cell.column.id}-${row.id}`}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <output data-testid="selected">
        {table
          .getSelectedRowModel()
          .rows.map((row) => row.id)
          .join(',')}
      </output>
    </div>
  );
}

const box = (n: number) => screen.getByRole('checkbox', { name: `Select Row ${n}` });
const selected = () => screen.getByTestId('selected').textContent;
const mouse = { pointerType: 'mouse', button: 0, buttons: 1, isPrimary: true, pointerId: 1 };


const touch = { pointerType: 'touch', button: 0, buttons: 1, isPrimary: true, pointerId: 7 };
const ROW_Y = (n: number) => n * 100;
const original = (document as unknown as { elementFromPoint?: unknown }).elementFromPoint;

beforeEach(() => {
  vi.useFakeTimers();
  (document as unknown as { elementFromPoint: unknown }).elementFromPoint = (_x: number, y: number) =>
    screen.queryByTestId(`name-r${Math.round(y / 100)}`);
});
afterEach(() => {
  vi.useRealTimers();
  (document as unknown as { elementFromPoint: unknown }).elementFromPoint = original;
});

const hold = (ms = 600) => act(() => void vi.advanceTimersByTime(ms));
/** Touch pointermove: target is ALWAYS the pressed box, position is another row's. */
const moveTo = (pressed: number, row: number, x = 10) =>
  fireEvent.pointerMove(box(pressed), { ...touch, clientX: x, clientY: ROW_Y(row) });
const pressBox = (n: number) =>
  fireEvent.pointerDown(box(n), { ...touch, clientX: 10, clientY: ROW_Y(n) });
const release = (n: number) => {
  fireEvent.pointerUp(box(n), touch);
  fireEvent.click(box(n).closest('tbody')!);
};
/** Cancelable touchmove on the box; returns true when the page was allowed to scroll. */
const touchMoveAllowed = (n: number) => fireEvent.touchMove(box(n), { cancelable: true, touches: [] });

describe('B-touch. Press and hold, then drag', () => {
  it('AC-T3: a held press then moving over rows ticks the run', () => {
    render(<Harness />);
    pressBox(2);
    hold(600);
    for (const n of [3, 4, 5]) moveTo(2, n);
    expect(selected()).toBe('r2,r3,r4,r5');
    release(5);
    expect(selected()).toBe('r2,r3,r4,r5');
  });

  it('AC-T3: nothing starts before the 500 ms hold is up', () => {
    render(<Harness />);
    pressBox(2);
    hold(300);
    moveTo(2, 4);
    hold(300);
    moveTo(2, 5);
    // the early move at 300 ms was only 200px away: that is a scroll, so no drag at all
    expect(selected()).toBe('');
  });

  it('AC-T3: the first box pressed decides tick vs untick', () => {
    render(<Harness initial={{ r1: true, r2: true, r3: true, r4: true, r5: true, r6: true }} />);
    pressBox(2);
    hold();
    moveTo(2, 3);
    moveTo(2, 4);
    expect(selected()).toBe('r1,r5,r6');
  });

  it('AC-T3: moving back restores the rows the finger leaves', () => {
    render(<Harness initial={{ r4: true }} />);
    pressBox(1);
    hold();
    moveTo(1, 5);
    moveTo(1, 2);
    expect(selected()).toBe('r1,r2,r4');
  });

  it('AC-T3: the click after a held drag is swallowed: no double toggle, no row open', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    pressBox(2);
    hold();
    moveTo(2, 4);
    release(2);
    expect(selected()).toBe('r2,r3,r4');
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('AC-T3: stops following the finger after release', () => {
    render(<Harness />);
    pressBox(1);
    hold();
    moveTo(1, 2);
    fireEvent.pointerUp(box(1), touch);
    moveTo(1, 5);
    expect(selected()).toBe('r1,r2');
  });

  it('AC-T4: moving more than 8px before the hold fires is a scroll, even after the timer would have', () => {
    render(<Harness />);
    pressBox(1);
    fireEvent.pointerMove(box(1), { ...touch, clientX: 10, clientY: ROW_Y(1) + 12 });
    hold(700);
    moveTo(1, 4);
    expect(selected()).toBe('');
    expect(document.documentElement.style.userSelect).toBe('');
  });

  it('AC-T1: a swipe over rows ticks nothing', () => {
    render(<Harness />);
    pressBox(1);
    for (const n of [2, 3, 4]) moveTo(1, n);
    fireEvent.pointerUp(box(1), touch);
    hold(700);
    expect(selected()).toBe('');
  });

  it('AC-T4: up to 8px of jitter keeps the hold alive', () => {
    render(<Harness />);
    pressBox(1);
    fireEvent.pointerMove(box(1), { ...touch, clientX: 13, clientY: ROW_Y(1) });
    hold();
    moveTo(1, 3);
    expect(selected()).toBe('r1,r2,r3');
  });

  it('AC-T2/T6: a tap (down and up inside 500 ms, then click) ticks exactly one row', () => {
    render(<Harness />);
    pressBox(3);
    hold(200);
    fireEvent.pointerUp(box(3), touch);
    fireEvent.click(box(3));
    hold(700);
    expect(selected()).toBe('r3');
  });

  it('AC-T5: scrolling is locked only while the held drag is live', () => {
    render(<Harness />);
    pressBox(2);
    // before the hold fires the page scrolls freely
    expect(touchMoveAllowed(2)).toBe(true);
    hold();
    moveTo(2, 3);
    // fireEvent returns false when preventDefault was called
    expect(touchMoveAllowed(2)).toBe(false);
    release(2);
    expect(touchMoveAllowed(2)).toBe(true);
  });

  it('AC-T5: the Android long-press menu is suppressed while a touch press is held', () => {
    render(<Harness />);
    pressBox(2);
    hold();
    const allowed = fireEvent.contextMenu(box(2));
    expect(allowed).toBe(false);
  });

  it('turns text selection off only while a held drag is live', () => {
    render(<Harness />);
    pressBox(1);
    expect(document.documentElement.style.userSelect).toBe('');
    hold();
    moveTo(1, 2);
    expect(document.documentElement.style.userSelect).toBe('none');
    release(1);
    expect(document.documentElement.style.userSelect).toBe('');
  });
});
