/**
 * GRID-DRAG-SELECT: the toolbar must not move the grid while a checkbox drag is live.
 *
 * The first tick swaps the toolbar's left cluster for the shorter "N selected" strip. On the
 * Internal Users list that lifted the table 130px, so the rows slid under a still pointer and
 * the drag ticked three rows past where the user was pointing (measured in the browser pass,
 * 27 Oct). While a drag is moving the toolbar keeps its pre-drag height, and the
 * "select all N records" banner (which would push the rows down) waits for the release.
 */
import React from 'react';
import { afterEach, beforeEach, describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';

import { DataGridListToolbar } from './data-grid-list-toolbar';
import { buildSelectColumn } from './data-grid-select-column';
import { TooltipProvider } from './tooltip';

type Rec = { id: string; name: string };
const DATA: Rec[] = [1, 2, 3].map((n) => ({ id: `r${n}`, name: `Row ${n}` }));
const COLUMNS: ColumnDef<Rec>[] = [
  buildSelectColumn<Rec>({ rowLabel: (row) => `Select ${row.original.name}` }),
  { id: 'name', accessorKey: 'name', cell: ({ row }) => <span>{row.original.name}</span> },
];

function Harness() {
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    getRowId: (r) => r.id,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <TooltipProvider>
      <DataGridListToolbar
        table={table}
        exportConfig={false}
        selectAllMatching={{ total: 10, loadedCount: 3, active: false, onSelectAll: () => {}, onClear: () => {} }}
      />
      <table>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} data-testid={`${cell.column.id}-${row.id}`}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TooltipProvider>
  );
}

const TALL = 170;
const toolbar = () => document.querySelector<HTMLElement>('[data-slot="data-grid-list-toolbar"]')!;
const box = (n: number) => screen.getByRole('checkbox', { name: `Select Row ${n}` });
const mouse = { pointerType: 'mouse', button: 0, buttons: 1, isPrimary: true, pointerId: 1 };

let restore: PropertyDescriptor | undefined;
beforeEach(() => {
  restore = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
  // jsdom has no layout: the idle toolbar measures TALL, the bulk strip 40.
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get(this: HTMLElement) {
      if (this.getAttribute('data-slot') !== 'data-grid-list-toolbar') return 0;
      return /\d+ selected/.test(this.textContent ?? '') ? 40 : TALL;
    },
  });
});
afterEach(() => {
  if (restore) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', restore);
});

describe('DataGridListToolbar during a checkbox drag', () => {
  it('keeps its pre-drag height while the drag moves, and lets go on release', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r2'), mouse);

    expect(screen.getByText('2 selected')).toBeInTheDocument();
    expect(toolbar().style.minHeight).toBe(`${TALL}px`);

    fireEvent.pointerUp(window, mouse);
    expect(toolbar().style.minHeight).toBe('');
  });

  it('a plain click keeps today\'s layout: no held height', () => {
    render(<Harness />);
    fireEvent.click(box(1));
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(toolbar().style.minHeight).toBe('');
  });

  it('holds the "select all N records" banner back until the drag is released', () => {
    render(<Harness />);
    fireEvent.pointerDown(box(1), mouse);
    fireEvent.pointerMove(screen.getByTestId('name-r3'), mouse);
    expect(screen.getByText('3 selected')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Select all 10 records' })).toBeNull();

    fireEvent.pointerUp(window, mouse);
    expect(screen.getByRole('button', { name: 'Select all 10 records' })).toBeInTheDocument();
  });
});
