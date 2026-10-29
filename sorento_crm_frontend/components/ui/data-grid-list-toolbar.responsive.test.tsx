/**
 * PORTAL-P4-REQUESTS owner hand test 2 (B): below sm the shared list toolbar shows Filters, Columns and
 * Export icon-only (label `hidden sm:inline`, name kept by aria-label + title), the search shrinks, Create
 * keeps its text. jsdom has no breakpoints, so the class contract is asserted.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';
import { DataGridListToolbar } from './data-grid-list-toolbar';
import { buildSelectColumn } from './data-grid-select-column';
import { TooltipProvider } from './tooltip';

type Row = { id: string; name: string };
const DATA: Row[] = [{ id: '1', name: 'Alpha' }];
const COLUMNS: ColumnDef<Row>[] = [
  buildSelectColumn<Row>(),
  { accessorKey: 'name', header: 'Name', meta: { headerTitle: 'Name' } },
];

function Harness(props: { toolbarProps?: Partial<React.ComponentProps<typeof DataGridListToolbar<Row>>> }) {
  const table = useReactTable({
    data: DATA, columns: COLUMNS, getRowId: (r) => r.id, enableRowSelection: true, getCoreRowModel: getCoreRowModel(),
  });
  return (
    <TooltipProvider>
      <DataGridListToolbar table={table} {...props.toolbarProps} />
    </TooltipProvider>
  );
}

const toolbarProps = {
  exportConfig: { filename: 'x.xlsx' },
  searchSlot: <input placeholder="Search rows" />,
  filters: { kind: 'custom' as const, active: false, content: <div>filter body</div> },
  primaryAction: <button type="button">Create thing</button>,
};

describe('DataGridListToolbar below sm', () => {
  for (const name of ['Filters', 'Columns', 'Export']) {
    it(`${name}: keeps its accessible name, title, and hides the label text below sm`, () => {
      render(<Harness toolbarProps={toolbarProps} />);
      const btn = screen.getByRole('button', { name });
      expect(btn).toHaveAttribute('aria-label', name);
      expect(btn).toHaveAttribute('title', name);
      const label = Array.from(btn.querySelectorAll('span')).find((s) => s.textContent?.trim() === name);
      expect(label, `no label span for ${name}`).toBeTruthy();
      expect(label).toHaveClass('hidden');
      expect(label).toHaveClass('sm:inline');
    });
  }

  it('the primary action keeps its text, never hidden', () => {
    render(<Harness toolbarProps={toolbarProps} />);
    const create = screen.getByRole('button', { name: 'Create thing' });
    expect(create).not.toHaveClass('hidden');
    expect(create.querySelector('.hidden')).toBeNull();
  });

  it('the search can shrink below sm and the desktop row classes are kept', () => {
    const { container } = render(<Harness toolbarProps={toolbarProps} />);
    const search = container.querySelector('[data-slot="data-grid-list-toolbar-search"]');
    expect(search).not.toBeNull();
    expect(search).toHaveClass('min-w-0');
    expect(search).toHaveClass('flex-1');
    const row = container.querySelector('[data-slot="data-grid-list-toolbar"]')!.firstElementChild;
    expect(row).toHaveClass('sm:flex-row');
  });
});
