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

/**
 * PORTAL-P4-REQUESTS L4 (hand test 3, owner a25895124 Q3 a): the primary action stays on the filter row on
 * phones for every list. Class contract (jsdom has no breakpoints): the toolbar's clusters row is a
 * wrapping ROW at every width (`flex-row flex-wrap`, never `flex-col` at the base), so Create sits beside
 * Filters / Columns / Export instead of dropping to a second row; the desktop (sm+) classes are unchanged.
 */
describe('DataGridListToolbar: the primary action stays on the filter row', () => {
  const rowOf = (container: HTMLElement) =>
    container.querySelector('[data-slot="data-grid-list-toolbar"]')!.firstElementChild as HTMLElement;

  // Lead decision (review of 13c1d4b551, owner a25895124 Q3 a): match the portal phone toolbar. Below sm the
  // search is on its own full-width line, then the icon buttons and Create share the next line (Create right).
  it('the clusters row wraps below sm and stays a row (never a column)', () => {
    const { container } = render(<Harness toolbarProps={toolbarProps} />);
    const row = rowOf(container);
    expect(row).toHaveClass('flex-row');
    expect(row).toHaveClass('flex-wrap');
    expect(row).toHaveClass('sm:flex-row');
    expect(row).not.toHaveClass('flex-nowrap');
    expect(row).not.toHaveClass('flex-col');
  });

  it('search is full width below sm and auto from sm; left cluster dissolves below sm; Create is pushed right and never shrinks', () => {
    const { container } = render(<Harness toolbarProps={toolbarProps} />);
    const row = rowOf(container);
    const [left, right] = Array.from(row.children) as HTMLElement[];
    expect(left).toHaveClass('contents');
    expect(left).toHaveClass('sm:flex');
    expect(left).not.toHaveClass('flex-1');
    expect(right).toHaveClass('shrink-0');
    expect(right.className).toMatch(/(^|\s)ml-auto(\s|$)|(^|\s)ms-auto(\s|$)/);
    expect(right.contains(screen.getByRole('button', { name: 'Create thing' }))).toBe(true);
    expect(left.contains(screen.getByRole('button', { name: 'Filters' }))).toBe(true);
    const search = container.querySelector('[data-slot="data-grid-list-toolbar-search"]');
    expect(search).toHaveClass('basis-full');
    expect(search).toHaveClass('sm:basis-auto');
    expect(search).toHaveClass('sm:flex-initial');
    expect(search).toHaveClass('min-w-0');
  });

  it('Filters and the primary action are in that one row', () => {
    const { container } = render(<Harness toolbarProps={toolbarProps} />);
    const row = rowOf(container);
    expect(row.contains(screen.getByRole('button', { name: 'Filters' }))).toBe(true);
    expect(row.contains(screen.getByRole('button', { name: 'Create thing' }))).toBe(true);
  });

  it('desktop layout classes are unchanged (sm: items-center + justify-between)', () => {
    const { container } = render(<Harness toolbarProps={toolbarProps} />);
    const row = rowOf(container);
    expect(row).toHaveClass('sm:items-center');
    expect(row).toHaveClass('sm:justify-between');
    expect(row).toHaveClass('sm:flex-wrap');
    const left = row.firstElementChild as HTMLElement;
    expect(left).toHaveClass('sm:flex-initial');
    expect(left).toHaveClass('sm:grow');
    expect(row).toHaveClass('gap-3');
    expect(row).toHaveClass('w-full');
  });
});
