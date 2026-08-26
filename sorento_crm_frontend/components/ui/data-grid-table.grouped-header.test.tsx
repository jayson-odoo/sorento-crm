/**
 * The two-row header of a grid that has column GROUPS (AC-G4).
 *
 * TanStack puts a PLACEHOLDER above every ungrouped column so the rows line up, which
 * draws an empty band over most of the header - the reports grid had one strip of nothing
 * above seven of its eleven columns. The register this grid mirrors merges those cells
 * vertically instead, and so does this: the placeholder carries the column's real header
 * and spans both rows, and the leaf underneath it is not rendered at all.
 *
 * A flat listing has ONE header row and no placeholders, so both branches below are no-ops
 * there - which is the point of testing the flat case alongside the grouped one.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

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

type Row = { id: string; agent: string; y1: boolean; y2: boolean };

const ROWS: Row[] = [{ id: '1', agent: 'Alice', y1: true, y2: false }];

const GROUPED: ColumnDef<Row>[] = [
  { accessorKey: 'agent', id: 'agent', header: 'Sales agent', size: 140 },
  {
    id: 'delivery',
    header: 'Expected year of delivery',
    columns: [
      { accessorKey: 'y1', id: 'y1', header: '2026', size: 60 },
      { accessorKey: 'y2', id: 'y2', header: '2027', size: 60 },
    ],
  },
];

const FLAT: ColumnDef<Row>[] = [
  { accessorKey: 'agent', id: 'agent', header: 'Sales agent', size: 140 },
];

function Harness({ columns, draggable }: { columns: ColumnDef<Row>[]; draggable: boolean }) {
  const table = useReactTable({
    data: ROWS,
    columns,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={ROWS.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsDraggable: draggable }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

function headerRows(): HTMLTableRowElement[] {
  return Array.from(document.querySelectorAll('thead tr')) as HTMLTableRowElement[];
}

describe.each([
  ['draggable', true],
  ['static', false],
])('DataGridTable grouped header (%s)', (_name, draggable) => {
  it('spans a single-level header over both header rows, once', () => {
    render(<Harness columns={GROUPED} draggable={draggable} />);

    const [groupRow, leafRow] = headerRows();
    const agent = screen.getByText('Sales agent').closest('th') as HTMLTableCellElement;

    expect(agent.parentElement).toBe(groupRow);
    expect(agent.rowSpan).toBe(2);
    // The leaf row holds only the group's own members: no empty band, no repeat.
    expect(Array.from(leafRow.querySelectorAll('th')).length).toBe(2);
    expect(screen.getAllByText('Sales agent')).toHaveLength(1);
  });

  it('keeps the group header over its members', () => {
    render(<Harness columns={GROUPED} draggable={draggable} />);

    const group = screen
      .getByText('Expected year of delivery')
      .closest('th') as HTMLTableCellElement;

    expect(group.colSpan).toBe(2);
    expect(group.rowSpan).toBe(1);
    expect(screen.getByText('2026')).toBeInTheDocument();
    expect(screen.getByText('2027')).toBeInTheDocument();
  });

  it('leaves a flat listing with one header row and no span', () => {
    render(<Harness columns={FLAT} draggable={draggable} />);

    expect(headerRows()).toHaveLength(1);
    const agent = screen.getByText('Sales agent').closest('th') as HTMLTableCellElement;
    expect(agent.rowSpan).toBe(1);
    expect(agent.colSpan).toBe(1);
  });
});
