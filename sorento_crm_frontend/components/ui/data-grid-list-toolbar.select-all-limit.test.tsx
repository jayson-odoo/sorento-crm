/**
 * GRID-DRAG-SELECT AC-C1/AC-C2: the toolbar's "select all matching" wording when the
 * list caps what it will fetch (`selectAllMatching.limit`).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';

import { DataGridListToolbar } from './data-grid-list-toolbar';
import { buildSelectColumn } from './data-grid-select-column';
import { TooltipProvider } from './tooltip';

type Rec = { id: string; name: string };
const DATA: Rec[] = [1, 2, 3].map((n) => ({ id: `r${n}`, name: `Row ${n}` }));
const COLUMNS: ColumnDef<Rec>[] = [
  buildSelectColumn<Rec>({ rowLabel: (row) => `Select ${row.original.name}` }),
  { id: 'name', accessorKey: 'name' },
];

function Harness({ total, limit, active }: { total: number; limit?: number; active: boolean }) {
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    state: { rowSelection: { r1: true, r2: true, r3: true } },
    getRowId: (r) => r.id,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <TooltipProvider>
      <DataGridListToolbar
        table={table}
        exportConfig={false}
        selectAllMatching={{ total, limit, loadedCount: 3, active, onSelectAll: () => {}, onClear: () => {} }}
      />
    </TooltipProvider>
  );
}

describe('selectAllMatching.limit wording', () => {
  it('over the limit, offers the first 1,000', () => {
    render(<Harness total={1248} limit={1000} active={false} />);
    expect(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' })).toBeInTheDocument();
  });

  it('over the limit and active, says 1,000 selected and which records', () => {
    render(<Harness total={1248} limit={1000} active />);
    expect(screen.getByText('1,000 selected')).toBeInTheDocument();
    expect(screen.getByText('First 1,000 of 1,248 matching records are selected.')).toBeInTheDocument();
  });

  it('under the limit, offers all of them', () => {
    render(<Harness total={120} limit={1000} active={false} />);
    expect(screen.getByRole('button', { name: 'Select all 120 records' })).toBeInTheDocument();
  });

  it('under the limit and active, says All 120 selected', () => {
    render(<Harness total={120} limit={1000} active />);
    expect(screen.getByText('All 120 selected')).toBeInTheDocument();
  });

  it('with no limit, keeps today\'s wording', () => {
    const { unmount } = render(<Harness total={1248} active={false} />);
    expect(screen.getByRole('button', { name: 'Select all 1248 records' })).toBeInTheDocument();
    unmount();
    render(<Harness total={1248} active />);
    expect(screen.getByText('All 1248 selected')).toBeInTheDocument();
    expect(screen.getByText(/records matching the current filters are selected\./)).toBeInTheDocument();
  });
});
