/**
 * What `listingKey` means on the shared DataGrid.
 *
 * Omitted, the grid still persists column order under the PATHNAME - that fallback is
 * deliberate and every listing that never passed a key depends on it, so it is asserted
 * here rather than left to be "cleaned up" by whoever reads the prop as optional.
 *
 * `null` is the opt-out: nothing is fetched, nothing is applied, nothing is saved. A grid
 * whose columns are DATA needs it (the stock-debt board's columns are the calendar): a row
 * saved under the pathname is re-applied against whatever columns exist the moment it
 * arrives, which reorders the screen and warns about ids that do not exist yet.
 */
import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, waitFor } from '@testing-library/react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/widgets',
}));

vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(),
}));

import { getUserListColumnConfig } from '@/lib/listing-column-preferences/listColumnPreferencesService';
import { DataGrid } from './data-grid';

type Row = { id: string; agent: string; value: number };

const ROWS: Row[] = [{ id: '1', agent: 'Alice', value: 1 }];

const COLUMNS: ColumnDef<Row>[] = [
  { accessorKey: 'agent', id: 'agent', header: 'Sales agent' },
  { accessorKey: 'value', id: 'value', header: 'Project value' },
];

const orderCalls: string[][] = [];

function Harness({ listingKey }: { listingKey?: string | null }) {
  const [columnOrder, setColumnOrder] = useState<string[]>([]);

  const table = useReactTable({
    data: ROWS,
    columns: COLUMNS,
    getRowId: (row) => row.id,
    state: { columnOrder },
    onColumnOrderChange: (updater) => {
      const next = typeof updater === 'function' ? updater(columnOrder) : updater;
      orderCalls.push(next);
      setColumnOrder(next);
    },
    getCoreRowModel: getCoreRowModel(),
  });

  return <DataGrid table={table} recordCount={ROWS.length} listingKey={listingKey} />;
}

function renderGrid(listingKey?: string | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Harness listingKey={listingKey} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  orderCalls.length = 0;
  vi.mocked(getUserListColumnConfig).mockResolvedValue({
    listing_key: '/widgets',
    config: { version: 1, columnOrder: ['value', 'agent'] },
  });
});

describe('DataGrid listingKey', () => {
  it('persists under the pathname when no key is given', async () => {
    renderGrid();

    await waitFor(() => expect(getUserListColumnConfig).toHaveBeenCalledWith('/widgets'));
    await waitFor(() => expect(orderCalls).toContainEqual(['value', 'agent']));
  });

  it('reads, applies and writes nothing when the key is null', async () => {
    renderGrid(null);

    // Nothing to wait on by design, so settle the effects and then assert the silence.
    await act(async () => {
      await Promise.resolve();
    });

    expect(getUserListColumnConfig).not.toHaveBeenCalled();
    expect(orderCalls).toEqual([]);
  });
});
