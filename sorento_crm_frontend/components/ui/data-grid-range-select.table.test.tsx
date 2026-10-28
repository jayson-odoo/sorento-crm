/**
 * GRID-DRAG-SELECT through the grid's OWN row box (`DataGridTableRowSelect`, the second
 * selection path, used by lists that build their select column by hand) inside a real
 * DataGrid + DataGridTable. The full behaviour matrix lives in data-grid-range-select.test.tsx;
 * this proves the wiring.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable, DataGridTableRowSelect } from './data-grid-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/contacts',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Rec = { id: string; name: string };

const DATA: Rec[] = Array.from({ length: 5 }, (_, i) => ({ id: `r${i + 1}`, name: `Row ${i + 1}` }));

const COLUMNS: ColumnDef<Rec>[] = [
  { id: 'select', header: '', size: 44, cell: ({ row }) => <DataGridTableRowSelect row={row} /> },
  { id: 'name', accessorKey: 'name', header: 'Name', size: 300 },
];

function Harness({ onRowClick }: { onRowClick?: (r: Rec) => void }) {
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
    <>
      <DataGrid
        table={table}
        recordCount={DATA.length}
        isLoading={false}
        onRowClick={onRowClick}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <DataGridTable />
      </DataGrid>
      <output data-testid="selected">{Object.keys(rowSelection).sort().join(',')}</output>
    </>
  );
}

const box = (n: number) => screen.getAllByRole('checkbox', { name: 'Select row' })[n - 1];
const selected = () => screen.getByTestId('selected').textContent;
const cellOf = (n: number) => screen.getByText(`Row ${n}`);
const mouse = { pointerType: 'mouse', button: 0, buttons: 1, isPrimary: true, pointerId: 1 };

describe('DataGridTableRowSelect ranges', () => {
  it('Shift+click ticks the range', () => {
    render(<Harness />);
    fireEvent.click(box(1));
    fireEvent.click(box(4), { shiftKey: true });
    expect(selected()).toBe('r1,r2,r3,r4');
  });

  it('drag down the box column ticks the run and opens nothing', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    fireEvent.pointerDown(box(2), mouse);
    fireEvent.pointerMove(cellOf(3), mouse);
    fireEvent.pointerMove(cellOf(5), mouse);
    fireEvent.pointerUp(cellOf(5), mouse);
    fireEvent.click(cellOf(5).closest('tbody')!);
    expect(selected()).toBe('r2,r3,r4,r5');
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('a drag released on the first row does not open it', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    fireEvent.pointerDown(box(2), mouse);
    fireEvent.pointerMove(cellOf(4), mouse);
    fireEvent.pointerMove(cellOf(2), mouse);
    fireEvent.pointerUp(cellOf(2), mouse);
    fireEvent.click(cellOf(2));
    expect(selected()).toBe('r2');
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('Shift+ArrowDown extends and moves focus', () => {
    render(<Harness />);
    fireEvent.click(box(1));
    act(() => box(1).focus());
    fireEvent.keyDown(box(1), { key: 'ArrowDown', shiftKey: true });
    expect(selected()).toBe('r1,r2');
    expect(document.activeElement).toBe(box(2));
  });

  it('a plain click on a row still opens it', () => {
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);
    fireEvent.click(cellOf(3));
    expect(onRowClick).toHaveBeenCalledWith(DATA[2]);
    expect(selected()).toBe('');
  });
});
