/**
 * M4 list latency - `isPlaceholderData` dims the body instead of a skeleton.
 *
 * `LIST_QUERY_OPTIONS` keeps the previous page's rows in `table.getRowModel()`
 * while the next page loads; the grid says so by dimming the body rather than
 * unmounting it, on the house tokens.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string };

const DATA: Row[] = [{ id: 'p-1', name: 'Ergonomic Chair' }];

const COLUMNS: ColumnDef<Row>[] = [{ id: 'name', accessorKey: 'name', header: 'Name', size: 400 }];

function Harness({ isPlaceholderData }: { isPlaceholderData?: boolean }) {
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
      isPlaceholderData={isPlaceholderData}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

describe('DataGridTable dims while showing a placeholder page (M4)', () => {
  it('adds the dim and transition classes while isPlaceholderData is true', () => {
    const { container } = render(<Harness isPlaceholderData />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).toContain('opacity-60');
    expect(tbody.className).toContain('transition-opacity');
    expect(tbody.className).toContain('duration-(--duration-fast)');
    expect(tbody.className).toContain('ease-(--ease-standard)');
  });

  it('adds none of them when isPlaceholderData is false', () => {
    const { container } = render(<Harness isPlaceholderData={false} />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).not.toContain('opacity-60');
    expect(tbody.className).not.toContain('transition-opacity');
  });

  it('adds none of them when isPlaceholderData is omitted', () => {
    const { container } = render(<Harness />);
    const tbody = container.querySelector('tbody')!;

    expect(tbody.className).not.toContain('opacity-60');
  });
});
