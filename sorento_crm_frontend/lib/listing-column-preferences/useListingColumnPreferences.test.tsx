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
  initialPageIndex = 0,
  onPaginationChangeSpy,
}: {
  listingKey: string;
  debounceMs: number;
  suppressPersist?: boolean;
  initialPageSize?: number;
  initialPageIndex?: number;
  onPaginationChangeSpy?: () => void;
}) {
  const { columns, data } = useMemo(makeTable, []);
  const [, setForceRerender] = useState(0);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: initialPageIndex,
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
          // A driver setting pagination straight past what the Rows-per-page menu
          // ever offers - the WRITE-side counterpart to Red 2's out-of-bound READ.
          table.setPageSize(250);
          setForceRerender((x) => x + 1);
        }}
      >
        set-page-size-250
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

  it('PLAN-listing-page-size-memory Red 1: applies a saved pageSize once, resetting to page 0', async () => {
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
          // S3 (review round 1): TanStack's setPageSize keeps the TOP ROW, it does
          // NOT reset pageIndex - starting on page 3 makes `page-index === 0` below a
          // real assertion of the hook's own setPagination({ pageIndex: 0 }) call,
          // not a coincidence of already being on page 0.
          initialPageIndex={2}
          onPaginationChangeSpy={paginationSpy}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('50');
    });
    expect(screen.getByTestId('page-index').textContent).toBe('0');
    expect(paginationSpy).toHaveBeenCalledTimes(1);

    // B3 (review round 1, kill test): applying the saved size must not immediately
    // save it straight back - the value just came FROM the server.
    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('PLAN-listing-page-size-memory Red 2: ignores a saved pageSize outside the bound', async () => {
    // Review round 1 ruling: pageSize is a BOUNDED INT (1..MAX_LIST_PAGE_SIZE), not a
    // fixed list - 33 would be a VALID size now, so the out-of-bound example is a
    // value past the bound instead.
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 500 },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, pageSize: 500 },
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

  it('B4 (review round 1, kill test): a page-size change is not saved while the config never applied, even once the fetch has SETTLED', async () => {
    // Distinct from Red 4: there `isFetching` alone was still true (the fetch was
    // in flight) so removing the `!appliedRef.current` guard in the page-size save
    // effect left the test green. Here the GET rejects - `isFetching` settles to
    // false, but `saved` stays undefined (the apply effect requires it), so
    // `appliedRef.current` never becomes true either. Only the `appliedRef` guard
    // stands between a page-size change and a write here.
    vi.mocked(service.getUserListColumnConfig).mockRejectedValue(new Error('network error'));
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

    // The query has settled (rejected, retry: 0) but the hook never applied anything.
    await waitFor(() => {
      expect(service.getUserListColumnConfig).toHaveBeenCalled();
    });
    await new Promise((r) => setTimeout(r, 30)); // let the rejection settle
    expect(screen.getByTestId('ready-state').textContent).toBe('loading');

    act(() => {
      screen.getByText('set-page-size-100').click();
    });

    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('B2 (review round 1, blocker): opening a listing with no saved row writes nothing on its own', async () => {
    // The null-config branch used to return without seeding `persistedPageSizeRef`,
    // so the page-size save effect saw "nothing known-saved yet" and wrote the
    // table's own default size back on first open - a write nobody asked for.
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: null,
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1 },
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

    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('a saved row carrying ONLY a valid pageSize (no column keys) still reaches ready', async () => {
    // Plain regression guard, renamed round 2 (SF2 asked to drop the `applied` state
    // twin this covers - kept it instead, see the hook's own comment: Red 2 and B2
    // both stay stuck on 'loading' forever without it, since neither one calls any
    // `table.set*` that would otherwise trigger the re-render `isLoading` needs).
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

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={20} initialPageSize={25} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('ready-state').textContent).toBe('ready');
    });
    expect(screen.getByTestId('page-size').textContent).toBe('50');
  });

  it('B1 (review round 2, blocker SF1): a column change and a page-size change inside the same debounce window produce exactly ONE PUT carrying both', async () => {
    // Round 1's fix (two SEPARATE debounce instances, one per effect) traded one bug
    // for another: two concurrent PUTs to the SAME row, against a read-modify-write
    // route that is not concurrency-safe against itself
    // (`app/api/v1/list_query.py:296-313`) - a key could still be lost (whichever
    // request's SELECT-then-COMMIT finished last wins), or a first-ever save on a
    // listing could 500 on the row's unique constraint. Round 2: ONE shared pending
    // payload, ONE debounce, so both changes are always one write.
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: true }, columnOrder: null, pageSize: 100 },
    });
    vi.mocked(service.resetUserListColumnConfig).mockResolvedValue(undefined);

    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <TestHarness listingKey="k" debounceMs={40} initialPageSize={25} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('ready-state').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('show-b').click();
    });
    act(() => {
      screen.getByText('set-page-size-100').click();
    });

    await waitFor(() => {
      expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
    });
    // Give a would-be second PUT a chance to land before asserting there is only one.
    await new Promise((r) => setTimeout(r, 60));

    const calls = vi.mocked(service.upsertUserListColumnConfig).mock.calls;
    expect(calls.length).toBe(1);
    const payload = calls[0]?.[1] as UserListColumnConfigPayload | undefined;
    expect(payload?.columnVisibility?.b).toBe(true);
    expect(payload?.pageSize).toBe(100);
  });

  it('N1 (review round 2): a caller-driven pageSize past the bound is never saved', async () => {
    // Red 2 is the READ side of the bound (a saved out-of-bound value is ignored on
    // apply); this is the WRITE side - a pagination change this hook did not
    // originate (or a bug in a caller) driving `pageSize` past `MAX_LIST_PAGE_SIZE`
    // must not reach the server either.
    vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null },
    });
    vi.mocked(service.upsertUserListColumnConfig).mockResolvedValue({
      listing_key: 'k',
      config: { version: 1, columnVisibility: { b: false }, columnOrder: null },
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
      screen.getByText('set-page-size-250').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('250');
    });

    await new Promise((r) => setTimeout(r, 60)); // past the 20ms debounce
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('PLAN-listing-page-size-memory Red 5: reset to defaults restores the mount-time page size and page 0', async () => {
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
        <TestHarness
          listingKey="k"
          debounceMs={20}
          initialPageSize={25}
          // N2 (review round 2): start away from page 0, same reasoning as Red 1 - a
          // reset landing on page 0 only because it started there is not a real
          // assertion of `resetToDefaults`'s own `setPagination({ pageIndex: 0 })`.
          initialPageIndex={2}
        />
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
    expect(screen.getByTestId('page-index').textContent).toBe('0');

    // N2 (review round 1): flush past the debounce before the test ends, so a
    // wrongly-armed timer fires here (and is asserted on) instead of bleeding,
    // unawaited, into whichever test runs next after unmount.
    await new Promise((r) => setTimeout(r, 60));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
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

