/**
 * S4 (SPO schedule cells, `PLAN-scm-spo-planner-feedback-3sep.md`) - the row-level hooks a
 * picker opened from a schedule cell needs: which rows fell in the clicked week (AC-D3).
 *
 * `DataGridTable`'s `<tr>` only had the boolean `rowPending` predicate before this (dims a
 * row and marks `data-pending`, see `data-grid-table.pending.test.tsx`) - `rowClassName` and
 * `rowAttributes` are the general-purpose siblings, so a caller can tint AND name a row
 * without pending's fixed opacity style.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: () => {}, replace: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: () => Promise.resolve(), isLoading: false }),
}));

type Row = { id: string; name: string };

const DATA: Row[] = [
  { id: 'r-1', name: 'First' },
  { id: 'r-2', name: 'Second' },
];

const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

function Harness({
  rowClassName,
  rowAttributes,
}: {
  rowClassName?: (row: Row) => string | undefined;
  rowAttributes?: (row: Row) => Record<string, string | undefined>;
}) {
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={DATA.length}
      isLoading={false}
      rowClassName={rowClassName}
      rowAttributes={rowAttributes}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

function rows(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('tbody tr'));
}

describe('DataGridTable rowClassName / rowAttributes (S4)', () => {
  it("adds the caller's class to exactly the row it names", () => {
    const { container } = render(
      <Harness rowClassName={(row) => (row.id === 'r-1' ? 'x' : undefined)} />,
    );

    const hit = container.querySelectorAll('tbody tr.x');
    expect(hit).toHaveLength(1);
    expect(hit[0].textContent).toContain('First');
    expect(rows(container)[1].className).not.toContain('x');
  });

  it("sets the caller's attribute on exactly the row it names", () => {
    const { container } = render(
      <Harness rowAttributes={(row) => (row.id === 'r-1' ? { 'data-bucket-hit': 'true' } : {})} />,
    );

    const [first, second] = rows(container);
    expect(first).toHaveAttribute('data-bucket-hit', 'true');
    expect(second).not.toHaveAttribute('data-bucket-hit');
  });

  it('a grid given neither prop marks nothing', () => {
    const { container } = render(<Harness />);

    for (const row of rows(container)) {
      expect(row).not.toHaveAttribute('data-bucket-hit');
      expect(row.className).not.toContain('x');
    }
  });
});
