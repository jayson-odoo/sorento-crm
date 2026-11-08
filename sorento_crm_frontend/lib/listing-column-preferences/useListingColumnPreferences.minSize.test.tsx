/**
 * A saved column width narrower than the column's own `minSize` restores AT the minimum
 * (crew pass on #2260, LIST-PRICE-CHANGE-UI): every saved Products layout carried
 * `list_price: 120` from before the cell gained its history icon, so the price clipped.
 * One rule for every grid, in the shared restore; TanStack's `getSize()` already clamps
 * the rendered width, and the restored state must agree with it.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { useMemo } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useListingColumnPreferences } from './useListingColumnPreferences';
import * as service from './listColumnPreferencesService';

vi.mock('./listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(),
}));

type Row = { id: string; price: number; name: string };

function Harness() {
  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      { id: 'price', accessorKey: 'price', header: 'Price', size: 170, minSize: 170 },
      { id: 'name', accessorKey: 'name', header: 'Name', size: 200 },
    ],
    [],
  );
  const data = useMemo<Row[]>(() => [{ id: 'r1', price: 1, name: 'x' }], []);
  const table = useReactTable({
    columns,
    data,
    getRowId: (r) => r.id,
    columnResizeMode: 'onChange',
    getCoreRowModel: getCoreRowModel(),
  });
  const { isLoading } = useListingColumnPreferences<Row>({ table, listingKey: 'k', debounceMs: 20 });
  return (
    <div>
      <div data-testid="ready">{isLoading ? 'loading' : 'ready'}</div>
      <div data-testid="price-state">{String(table.getState().columnSizing.price ?? '')}</div>
      <div data-testid="price-size">{table.getColumn('price')?.getSize()}</div>
      <div data-testid="name-size">{table.getColumn('name')?.getSize()}</div>
    </div>
  );
}

describe('useListingColumnPreferences - saved width below a column minimum', () => {
  beforeEach(() => vi.resetAllMocks());

  it('restores a saved width narrower than minSize at the minimum, and leaves other widths alone', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnSizing: { price: 120, name: 90 } },
    } as never);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Harness />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('name-size').textContent).toBe('90'));
    expect(screen.getByTestId('price-state').textContent).toBe('170');
    expect(screen.getByTestId('price-size').textContent).toBe('170');
  });
});
