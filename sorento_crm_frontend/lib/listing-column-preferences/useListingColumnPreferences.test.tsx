import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { useMemo, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useListingColumnPreferences } from './useListingColumnPreferences';
import * as service from './listColumnPreferencesService';
import type { UserListColumnConfigPayload } from './listColumnPreferencesService';

vi.mock('./listColumnPreferencesService', () => {
  return {
    getUserListColumnConfig: vi.fn(),
    upsertUserListColumnConfig: vi.fn(),
    resetUserListColumnConfig: vi.fn(),
  };
});

type Row = { id: string; a: string; b: string };

function makeTable() {
  const columns = [
    {
      id: 'a',
      accessorFn: (row: Row) => row.a,
      header: 'A',
      enableHiding: true,
    },
    {
      id: 'b',
      accessorFn: (row: Row) => row.b,
      header: 'B',
      enableHiding: true,
    },
  ] satisfies ColumnDef<Row>[];

  const data: Row[] = [{ id: 'r1', a: 'A1', b: 'B1' }];

  return { columns, data };
}

function TestHarness({
  listingKey,
  debounceMs,
}: {
  listingKey: string;
  debounceMs: number;
}) {
  const { columns, data } = useMemo(makeTable, []);
  const [, setForceRerender] = useState(0);

  const table = useReactTable({
    columns,
    data,
    getRowId: (r) => r.id,
    state: {
      pagination: { pageIndex: 0, pageSize: 10 },
    },
    getCoreRowModel: getCoreRowModel(),
  });

  const { resetToDefaults } = useListingColumnPreferences<Row>({
    table,
    listingKey,
    debounceMs,
  });

  const bVisible = table.getColumn('b')?.getIsVisible();

  return (
    <div>
      <div data-testid="b-state">{bVisible ? 'b-visible' : 'b-hidden'}</div>
      <button
        onClick={() => {
          table.getColumn('b')?.toggleVisibility(true);
          setForceRerender((x) => x + 1);
        }}
      >
        show-b
      </button>
      <button
        onClick={() => {
          void resetToDefaults();
          setForceRerender((x) => x + 1);
        }}
      >
        reset
      </button>
    </div>
  );
}

describe('useListingColumnPreferences', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('applies saved column visibility and auto-saves on toggle', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: true }, columnOrder: null },
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();
    const ListingKey = 'k';

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey={ListingKey} debounceMs={20} />
      </QueryClientProvider>,
    );

    // Wait for saved config apply effect.
    await waitFor(() => {
      expect(screen.getByTestId('b-state').textContent).toBe('b-hidden');
    });

    act(() => {
      screen.getByText('show-b').click();
    });

    await waitFor(() => {
      expect(vi.mocked(service.upsertUserListColumnConfig)).toHaveBeenCalled();
    });

    const calls = vi.mocked(service.upsertUserListColumnConfig).mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const call = calls[0];
    expect(call?.[0]).toBe(ListingKey);
    const payload = call?.[1] as UserListColumnConfigPayload | undefined;
    expect(payload?.columnVisibility?.b).toBe(true);
  });

  it('resets to default visibility', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: {},
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('b-state').textContent).toBe('b-hidden');
    });

    act(() => {
      screen.getByText('reset').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('b-state').textContent).toBe('b-visible');
    });
  });
});

