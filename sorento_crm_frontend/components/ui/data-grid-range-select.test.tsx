/**
 * GRID-DRAG-SELECT: faster ticking on every DataGrid that uses `buildSelectColumn`.
 *
 * A. Shift+click a row's box: every row between the last clicked box and this one takes the
 *    last clicked box's state (Gmail).
 * B. Press a row's box and move over other rows: the run between takes the opposite of the
 *    first box's state; moving back restores what the rows had before. Mouse and pen only,
 *    a finger keeps scrolling. A press anywhere else in the row never starts it, so text in
 *    the row stays selectable for copy.
 * D. Arrow keys move between row boxes; Shift+Arrow gives the next row the last box's state.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
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

/** Press on row `from`'s box, move over each row in `over` (on its name cell), release. */
function drag(from: number, over: number[], { release = true } = {}) {
  fireEvent.pointerDown(box(from), mouse);
  for (const n of over) fireEvent.pointerMove(screen.getByTestId(`name-r${n}`), mouse);
  if (release) {
    const last = over.length ? screen.getByTestId(`name-r${over[over.length - 1]}`) : box(from);
    fireEvent.pointerUp(last, mouse);
    // The browser's click after a press that moved lands on the common ancestor, not the box.
    fireEvent.click(over.length ? last.closest('tbody')! : box(from));
  }
}

describe('A. Shift+click ticks a range', () => {
  it('ticks every row between the last clicked box and the shift-clicked one', () => {
    render(<Harness />);
    fireEvent.click(box(2));
    fireEvent.click(box(5), { shiftKey: true });
    expect(selected()).toBe('r2,r3,r4,r5');
  });

  it('works upward too', () => {
    render(<Harness />);
    fireEvent.click(box(5));
    fireEvent.click(box(2), { shiftKey: true });
    expect(selected()).toBe('r2,r3,r4,r5');
  });

  it('unticks the range when the last clicked box was unticked', () => {
    render(<Harness initial={{ r1: true, r2: true, r3: true, r4: true, r5: true, r6: true }} />);
    fireEvent.click(box(2));
    fireEvent.click(box(4), { shiftKey: true });
    expect(selected()).toBe('r1,r5,r6');
  });

  it('keeps an already ticked target ticked instead of toggling it off', () => {
    render(<Harness initial={{ r5: true }} />);
    fireEvent.click(box(2));
    fireEvent.click(box(5), { shiftKey: true });
    expect(selected()).toBe('r2,r3,r4,r5');
  });

  it('Shift+click on the last clicked box itself toggles it like a plain click', () => {
    render(<Harness />);
    fireEvent.click(box(2));
    fireEvent.click(box(2), { shiftKey: true });
    expect(selected()).toBe('');
  });

  it('toggles just the one box when nothing was clicked before', () => {
    render(<Harness />);
    fireEvent.click(box(3), { shiftKey: true });
    expect(selected()).toBe('r3');
  });

  it('skips rows that cannot be selected', () => {
    const data = DATA.map((r) => (r.id === 'r3' ? { ...r, locked: true } : r));
    render(<Harness data={data} />);
    fireEvent.click(box(1));
    fireEvent.click(box(5), { shiftKey: true });
    expect(selected()).toBe('r1,r2,r4,r5');
  });

  it('never opens the row', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    fireEvent.click(box(1));
    fireEvent.click(box(4), { shiftKey: true });
    expect(onRowClick).not.toHaveBeenCalled();
  });
});

describe('B. Drag down the checkbox column', () => {
  it('ticks the run of rows the pointer passes over', () => {
    render(<Harness />);
    drag(2, [3, 4, 5]);
    expect(selected()).toBe('r2,r3,r4,r5');
  });

  it('fills rows the pointer skipped over on a fast move', () => {
    render(<Harness />);
    drag(1, [5]);
    expect(selected()).toBe('r1,r2,r3,r4,r5');
  });

  it('works dragging upward', () => {
    render(<Harness />);
    drag(5, [4, 3]);
    expect(selected()).toBe('r3,r4,r5');
  });

  it('restores rows when the pointer moves back', () => {
    render(<Harness initial={{ r4: true }} />);
    drag(1, [5, 2]);
    expect(selected()).toBe('r1,r2,r4');
  });

  it('unticks the run when the first box was ticked', () => {
    render(<Harness initial={{ r1: true, r2: true, r3: true, r4: true, r5: true, r6: true }} />);
    drag(2, [3, 4]);
    expect(selected()).toBe('r1,r5,r6');
  });

  it('leaves rows already in the target state alone', () => {
    render(<Harness initial={{ r3: true }} />);
    drag(2, [4]);
    expect(selected()).toBe('r2,r3,r4');
  });

  it('a press that does not move is a plain click: ticks one row, once', () => {
    render(<Harness />);
    drag(3, []);
    expect(selected()).toBe('r3');
  });

  it('ending the drag back on the first box does not toggle it a second time', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(2), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r4'), mouse);
    fireEvent.pointerMove(box(2), mouse);
    fireEvent.pointerUp(box(2), mouse);
    fireEvent.click(box(2));
    expect(selected()).toBe('r2');
  });

  it('stops following the pointer after release', () => {
    render(<Harness />);
    drag(1, [2]);
    fireEvent.pointerMove(screen.getByTestId('name-r5'), mouse);
    expect(selected()).toBe('r1,r2');
  });

  it('ends on pointercancel too', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r2'), mouse);
    fireEvent.pointerCancel(window, mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r5'), mouse);
    expect(selected()).toBe('r1,r2');
  });

  it('a press on a text cell never starts a drag, so text stays selectable', () => {
    render(<Harness />);
    fireEvent.pointerDown(screen.getByTestId('name-r1'), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r4'), mouse);
    fireEvent.pointerUp(screen.getByTestId('name-r4'), mouse);
    expect(selected()).toBe('');
    expect(document.documentElement.style.userSelect).toBe('');
  });

  it('turns text selection off only while a drag is live', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r3'), mouse);
    expect(document.documentElement.style.userSelect).toBe('none');
    fireEvent.pointerUp(window, mouse);
    expect(document.documentElement.style.userSelect).toBe('');
  });

  it('a finger does not drag: moving after a touch press ticks nothing extra', () => {
    render(<Harness />);
    const touch = { ...mouse, pointerType: 'touch' };
    fireEvent.pointerDown(box(1), touch);
    fireEvent.pointerMove(screen.getByTestId('name-r4'), touch);
    fireEvent.pointerUp(screen.getByTestId('name-r4'), touch);
    expect(selected()).toBe('');
    // ...and a tap still ticks the one row.
    fireEvent.click(box(1));
    expect(selected()).toBe('r1');
  });

  it('skips rows that cannot be selected', () => {
    const data = DATA.map((r) => (r.id === 'r3' ? { ...r, locked: true } : r));
    render(<Harness data={data} />);
    drag(1, [4]);
    expect(selected()).toBe('r1,r2,r4');
  });

  it('never opens a row', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    drag(1, [3]);
    drag(5, []);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('a drag released on the first row\'s text does not open that row', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    fireEvent.pointerDown(box(2), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r4'), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r2'), mouse);
    fireEvent.pointerUp(screen.getByTestId('name-r2'), mouse);
    // Browser: press and release both inside row 2, so the click targets row 2.
    fireEvent.click(screen.getByTestId('name-r2'));
    expect(onRowClick).not.toHaveBeenCalled();
    expect(selected()).toBe('r2');
  });

  it('a right-button press does not start a drag', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), { ...mouse, button: 2, buttons: 2 });
    fireEvent.pointerMove(screen.getByTestId('name-r3'), { ...mouse, buttons: 2 });
    expect(selected()).toBe('');
  });

  it('a move with the button already up ends the drag instead of ticking on hover', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r2'), mouse);
    // Released outside the window: no pointerup ever arrives.
    fireEvent.pointerMove(screen.getByTestId('name-r4'), { ...mouse, buttons: 0 });
    fireEvent.pointerMove(screen.getByTestId('name-r5'), { ...mouse, buttons: 0 });
    expect(selected()).toBe('r1,r2');
    expect(document.documentElement.style.userSelect).toBe('');
  });

  it('leaving the window ends the drag and gives text selection back', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r3'), mouse);
    fireEvent.blur(window);
    expect(document.documentElement.style.userSelect).toBe('');
    fireEvent.pointerMove(screen.getByTestId('name-r5'), mouse);
    expect(selected()).toBe('r1,r2,r3');
  });

  it('a pointerup something else stops from bubbling still ends the drag', () => {
    render(<Harness />);
    const cell = screen.getByTestId('name-r2');
    cell.addEventListener('pointerup', (e) => e.stopPropagation());
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(cell, mouse);
    fireEvent.pointerUp(cell, mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r5'), mouse);
    expect(selected()).toBe('r1,r2');
  });

  it('puts back an inline user-select the page had before the drag', () => {
    document.documentElement.style.userSelect = 'text';
    render(<Harness />);
    drag(1, [2]);
    expect(document.documentElement.style.userSelect).toBe('text');
    document.documentElement.style.userSelect = '';
  });

  it('stays inside its own table when two grids share row ids', () => {
    render(
      <>
        <div data-testid="a"><Harness /></div>
        <div data-testid="b"><Harness /></div>
      </>,
    );
    const [a, b] = [screen.getByTestId('a'), screen.getByTestId('b')];
    const inA = within(a);
    fireEvent.pointerDown(inA.getByRole('checkbox', { name: 'Select Row 1' }), mouse);
    // Pointer wanders into grid B's row 4: grid A must not tick its own row 4.
    fireEvent.pointerMove(within(b).getByTestId('name-r4'), mouse);
    fireEvent.pointerUp(window, mouse);
    expect(inA.getByTestId('selected').textContent).toBe('');
    expect(within(b).getByTestId('selected').textContent).toBe('');
  });

  it('a drag after Shift+click starts from the dragged box', () => {
    render(<Harness />);
    fireEvent.click(box(1));
    drag(4, [5]);
    fireEvent.click(box(6), { shiftKey: true });
    // Anchor moved to where the drag ended (r5), whose state is ticked.
    expect(selected()).toBe('r1,r4,r5,r6');
  });
});

describe('D. Keyboard on the checkbox column', () => {
  it('ArrowDown and ArrowUp move focus between row boxes', () => {
    render(<Harness />);
    act(() => box(2).focus());
    fireEvent.keyDown(box(2), { key: 'ArrowDown' });
    expect(document.activeElement).toBe(box(3));
    fireEvent.keyDown(box(3), { key: 'ArrowUp' });
    fireEvent.keyDown(box(2), { key: 'ArrowUp' });
    expect(document.activeElement).toBe(box(1));
    expect(selected()).toBe('');
  });

  it('steps over a row that cannot be selected', () => {
    const data = DATA.map((r) => (r.id === 'r3' ? { ...r, locked: true } : r));
    render(<Harness data={data} />);
    fireEvent.click(box(2));
    act(() => box(2).focus());
    fireEvent.keyDown(box(2), { key: 'ArrowDown' });
    expect(document.activeElement).toBe(box(4));
    fireEvent.keyDown(box(4), { key: 'ArrowUp', shiftKey: true });
    expect(document.activeElement).toBe(box(2));
    fireEvent.keyDown(box(2), { key: 'ArrowDown', shiftKey: true });
    expect(selected()).toBe('r2,r4');
  });

  it('stops at the ends', () => {
    render(<Harness />);
    act(() => box(6).focus());
    fireEvent.keyDown(box(6), { key: 'ArrowDown' });
    expect(document.activeElement).toBe(box(6));
  });

  it('Shift+ArrowDown gives the next row the last clicked box state', () => {
    render(<Harness />);
    fireEvent.click(box(2));
    act(() => box(2).focus());
    fireEvent.keyDown(box(2), { key: 'ArrowDown', shiftKey: true });
    fireEvent.keyDown(box(3), { key: 'ArrowDown', shiftKey: true });
    expect(selected()).toBe('r2,r3,r4');
    expect(document.activeElement).toBe(box(4));
  });

  it('Shift+Arrow with nothing clicked before ticks the current and next row', () => {
    render(<Harness />);
    act(() => box(4).focus());
    fireEvent.keyDown(box(4), { key: 'ArrowUp', shiftKey: true });
    expect(selected()).toBe('r3,r4');
  });

  it('Shift+Arrow unticks when the last clicked box was unticked', () => {
    render(<Harness initial={{ r1: true, r2: true, r3: true }} />);
    fireEvent.click(box(1));
    act(() => box(1).focus());
    fireEvent.keyDown(box(1), { key: 'ArrowDown', shiftKey: true });
    expect(selected()).toBe('r3');
  });

  it('other keys are left alone', () => {
    render(<Harness />);
    act(() => box(2).focus());
    fireEvent.keyDown(box(2), { key: 'ArrowRight' });
    expect(document.activeElement).toBe(box(2));
  });
});
