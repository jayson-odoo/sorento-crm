import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type Updater,
} from '@tanstack/react-table';
import { useMemo, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useListingColumnPreferences } from './useListingColumnPreferences';
import * as service from './listColumnPreferencesService';
import type { UserListColumnConfigPayload, UserListColumnConfigResponse } from './listColumnPreferencesService';

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
  suppressPersist,
  initialPageSize = 25,
  onPaginationChangeSpy,
}: {
  listingKey: string;
  debounceMs: number;
  suppressPersist?: boolean;
  initialPageSize?: number;
  onPaginationChangeSpy?: () => void;
}) {
  const { columns, data } = useMemo(makeTable, []);
  const [, setForceRerender] = useState(0);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: initialPageSize,
  });

  const table = useReactTable({
    columns,
    data,
    getRowId: (r) => r.id,
    state: {
      pagination,
    },
    onPaginationChange: (updater: Updater<PaginationState>) => {
      setPagination((old) => (typeof updater === 'function' ? updater(old) : updater));
      onPaginationChangeSpy?.();
    },
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const { resetToDefaults, isLoading } = useListingColumnPreferences<Row>({
    table,
    listingKey,
    debounceMs,
    suppressPersist,
  });

  const bVisible = table.getColumn('b')?.getIsVisible();

  return (
    <div>
      <div data-testid="b-state">{bVisible ? 'b-visible' : 'b-hidden'}</div>
      <div data-testid="ready-state">{isLoading ? 'loading' : 'ready'}</div>
      <div data-testid="page-size">{table.getState().pagination.pageSize}</div>
      <div data-testid="page-index">{table.getState().pagination.pageIndex}</div>
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
          table.setPageSize(100);
          setForceRerender((x) => x + 1);
        }}
      >
        set-page-size-100
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

  it('B1 (PR #489 review round): suppressPersist stops a column change from writing back', async () => {
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

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} suppressPersist />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('b-state').textContent).toBe('b-hidden');
    });

    act(() => {
      screen.getByText('show-b').click();
    });

    // The column DID change on screen...
    await waitFor(() => {
      expect(screen.getByTestId('b-state').textContent).toBe('b-visible');
    });
    // ...but nothing was written back to the server - the exact failure B1 names: a
    // segment-driven column change (or any other caller-driven one) must not overwrite
    // the reader's own saved layout while `suppressPersist` is on.
    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('PLAN-listing-page-size-memory Red 1: applies a saved pageSize once, at page 0', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 50 },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 50 },
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();
    const paginationSpy = vi.fn();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness
          listingKey="k"
          debounceMs={20}
          initialPageSize={25}
          onPaginationChangeSpy={paginationSpy}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('50');
    });
    expect(screen.getByTestId('page-index').textContent).toBe('0');
    expect(paginationSpy).toHaveBeenCalledTimes(1);
  });

  it('PLAN-listing-page-size-memory Red 2: ignores a saved pageSize outside the listed sizes', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 33 },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 33 },
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();
    const paginationSpy = vi.fn();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness
          listingKey="k"
          debounceMs={20}
          initialPageSize={25}
          onPaginationChangeSpy={paginationSpy}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('ready-state').textContent).toBe('ready');
    });
    expect(screen.getByTestId('page-size').textContent).toBe('25');
    expect(paginationSpy).not.toHaveBeenCalled();
  });

  it('PLAN-listing-page-size-memory Red 3: a page-size change after load writes one debounced PUT carrying only pageSize', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null, pageSize: 100 },
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} initialPageSize={25} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('ready-state').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('set-page-size-100').click();
    });

    await waitFor(() => {
      expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
    });

    const calls = vi.mocked(service.upsertUserListColumnConfig).mock.calls;
    expect(calls.length).toBe(1);
    const payload = calls[0]?.[1] as UserListColumnConfigPayload | undefined;
    expect(payload).toEqual({ pageSize: 100 });
  });

  it('PLAN-listing-page-size-memory Red 4: a page-size change before the config has loaded is not saved', async () => {
    let resolveConfig: ((value: UserListColumnConfigResponse) => void) | undefined;
    vi.mocked(service.getUserListColumnConfig).mockReturnValue(
      new Promise((resolve) => {
        resolveConfig = resolve;
      }),
    );
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 100 },
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} initialPageSize={25} />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('ready-state').textContent).toBe('loading');

    act(() => {
      screen.getByText('set-page-size-100').click();
    });

    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();

    // Let the fetch resolve so the test does not leak a pending promise/timer.
    resolveConfig?.({ listing_key: 'k', config: null });
  });

  it('PLAN-listing-page-size-memory Red 5: reset to defaults restores the mount-time page size', async () => {
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 100 },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: {},
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} initialPageSize={25} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('100');
    });

    act(() => {
      screen.getByText('reset').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('25');
    });
  });

  it('PLAN-listing-page-size-memory Red 6: suppressPersist stops a page-size change from writing back', async () => {
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

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} initialPageSize={25} suppressPersist />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('ready-state').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('set-page-size-100').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('100');
    });

    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });
});

