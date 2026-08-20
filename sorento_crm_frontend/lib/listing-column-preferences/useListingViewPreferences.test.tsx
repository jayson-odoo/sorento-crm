import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useListingViewPreferences } from './useListingViewPreferences';
import * as service from './listColumnPreferencesService';
import type { UserListColumnConfigPayload } from './listColumnPreferencesService';

vi.mock('./listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(),
}));

const KEY = 'k';
const DEBOUNCE = 30;
const DEFAULT_SORTING = [{ id: 'created_at', desc: true }];

type Filters = { statuses: string[] };

function Harness({ filtersVersion = 1 }: { filtersVersion?: number }) {
  const { sorting, filters, setSorting, setFilters, isLoading } =
    useListingViewPreferences<Filters>({
      listingKey: KEY,
      defaultSorting: DEFAULT_SORTING,
      filtersVersion,
      debounceMs: DEBOUNCE,
    });

  return (
    <div>
      <div data-testid="loading">{isLoading ? 'loading' : 'ready'}</div>
      <div data-testid="sorting">{JSON.stringify(sorting)}</div>
      <div data-testid="filters">{JSON.stringify(filters)}</div>
      <button onClick={() => setFilters({ statuses: ['responded'] })}>set-responded</button>
      <button onClick={() => setFilters({ statuses: ['pending_purchasing'] })}>
        set-pending
      </button>
      <button onClick={() => setFilters(null)}>clear-filter</button>
      <button onClick={() => setSorting([{ id: 'inquiry_number', desc: false }])}>
        sort-by-number
      </button>
    </div>
  );
}

/**
 * Everything renders under StrictMode on purpose. Its double-invoked effects are
 * what exposed the bug this hook was rewritten for: a one-shot "skip the save my
 * own apply triggers" flag is eaten by the first invocation and the second writes.
 * A test that passes without StrictMode proves nothing about that.
 */
function renderHook(options?: { filtersVersion?: number; client?: QueryClient }) {
  const client =
    options?.client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <Harness filtersVersion={options?.filtersVersion} />
      </QueryClientProvider>
    </StrictMode>,
  );
  return client;
}

/** Long enough that a scheduled debounced write would have fired. */
async function pastTheDebounceWindow() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, DEBOUNCE * 5));
  });
}

const STORED_VIEW = {
  version: 1,
  sorting: [{ id: 'status', desc: false }],
  filters: { statuses: ['pending_purchasing'] },
  filtersVersion: 1,
};

function mockStoredConfig(config: UserListColumnConfigPayload | null) {
  vi.mocked(service.getUserListColumnConfig).mockResolvedValue({
    listing_key: KEY,
    config,
  });
  vi.mocked(service.upsertUserListColumnConfig).mockImplementation(async (_k, payload) => ({
    listing_key: KEY,
    config: { ...(config ?? {}), ...payload } as UserListColumnConfigPayload,
  }));
}

const upsert = () => vi.mocked(service.upsertUserListColumnConfig);
const lastPayload = () =>
  upsert().mock.calls[upsert().mock.calls.length - 1]?.[1] as UserListColumnConfigPayload;

describe('useListingViewPreferences', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('applies the stored sort and filter on mount (AC-B1)', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('sorting').textContent).toBe(
        JSON.stringify([{ id: 'status', desc: false }]),
      );
    });
    expect(screen.getByTestId('filters').textContent).toBe(
      JSON.stringify({ statuses: ['pending_purchasing'] }),
    );
  });

  it('gates on isLoading until the stored view has been applied (AC-B3)', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    expect(screen.getByTestId('loading').textContent).toBe('loading');
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });
  });

  it('releases the gate for a user with nothing stored (AC-B2)', async () => {
    mockStoredConfig(null);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });
    expect(screen.getByTestId('sorting').textContent).toBe(JSON.stringify(DEFAULT_SORTING));
    expect(screen.getByTestId('filters').textContent).toBe('null');
  });

  it('writes nothing for a first-time user (AC-B2)', async () => {
    mockStoredConfig(null);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });
    await pastTheDebounceWindow();

    expect(upsert()).not.toHaveBeenCalled();
  });

  it('writes nothing back for the view it just applied', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });
    await pastTheDebounceWindow();

    expect(upsert()).not.toHaveBeenCalled();
  });

  it('discards a version-mismatched filter blob WITHOUT erasing it (AC-B4)', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook({ filtersVersion: 2 });

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });
    // The stale filter is not applied, but the stored sort still is.
    expect(screen.getByTestId('filters').textContent).toBe('null');
    expect(screen.getByTestId('sorting').textContent).toBe(
      JSON.stringify([{ id: 'status', desc: false }]),
    );

    await pastTheDebounceWindow();
    // The blob survives until the user's next filter change overwrites it.
    expect(upsert()).not.toHaveBeenCalled();
  });

  it('debounce-writes a filter change with its version (AC-B6)', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('set-responded').click();
    });

    await waitFor(() => {
      expect(upsert()).toHaveBeenCalledTimes(1);
    });
    expect(upsert().mock.calls[0]?.[0]).toBe(KEY);
    expect(lastPayload().filters).toEqual({ statuses: ['responded'] });
    expect(lastPayload().filtersVersion).toBe(1);
    // The column keys belong to the other writer and are never in this body.
    expect(lastPayload()).not.toHaveProperty('columnOrder');
  });

  it('debounce-writes a sort change (AC-B5)', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('sort-by-number').click();
    });

    await waitFor(() => {
      expect(upsert()).toHaveBeenCalledTimes(1);
    });
    expect(lastPayload().sorting).toEqual([{ id: 'inquiry_number', desc: false }]);
  });

  it('clears with an explicit null, which is what the endpoint treats as a clear (AC-C2)', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('clear-filter').click();
    });

    await waitFor(() => {
      expect(upsert()).toHaveBeenCalledTimes(1);
    });
    expect(lastPayload().filters).toBeNull();
    expect(lastPayload().filtersVersion).toBeNull();
  });

  it('does not write when the view returns to its stored value', async () => {
    mockStoredConfig(STORED_VIEW);
    renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('set-responded').click();
      screen.getByText('set-pending').click();
    });
    await pastTheDebounceWindow();

    expect(upsert()).not.toHaveBeenCalled();
    expect(screen.getByTestId('filters').textContent).toBe(
      JSON.stringify({ statuses: ['pending_purchasing'] }),
    );
  });

  it('seeds the shared cache entry from the write response (AC-B7)', async () => {
    mockStoredConfig(STORED_VIEW);
    const client = renderHook();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('ready');
    });

    act(() => {
      screen.getByText('set-responded').click();
    });

    await waitFor(() => {
      const cached = client.getQueryData(['list-column-config', KEY]) as {
        config: UserListColumnConfigPayload;
      };
      expect(cached?.config?.filters).toEqual({ statuses: ['responded'] });
    });
    // Only one read of the row: the write seeds, it does not refetch.
    expect(vi.mocked(service.getUserListColumnConfig)).toHaveBeenCalledTimes(1);
  });
});
