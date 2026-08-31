/**
 * The Users list search spinner stays lit past the debounce window (S7 feedback).
 *
 * `isSettling` alone only covers the 200ms `useDebouncedSearch` waits before it
 * asks the server - it goes false the instant the request goes OUT, which reads
 * as "done" while the network round trip is still running. This asserts the
 * icon keeps spinning while the query itself is fetching for the typed term,
 * and stops once the filtered page actually lands.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const fetchUsersListPageMock = vi.fn();
vi.mock('../lib/listQuery', async () => {
  const actual =
    await vi.importActual<typeof import('../lib/listQuery')>('../lib/listQuery');
  return {
    ...actual,
    fetchUsersListPage: (...args: unknown[]) => fetchUsersListPageMock(...args),
  };
});

vi.mock('../../roles/hooks/use-role-select-query', () => ({
  useRoleSelectQuery: () => ({ data: [] }),
}));

vi.mock('./user-add-dialog', () => ({
  default: () => null,
}));

// The DataGrid keeps the table in a skeleton until the column-config query
// resolves; stub it "loaded" so the toolbar (and its search box) renders.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/users',
  useSearchParams: () => new URLSearchParams(),
}));

import UserList from './user-list';

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UserList />
    </QueryClientProvider>,
  );
}

/** A promise this test resolves by hand, standing in for a slow network reply. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

beforeEach(() => {
  fetchUsersListPageMock.mockReset();
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe('UserList - search spinner (S7 feedback)', () => {
  it('keeps spinning past the debounce window until the filtered page lands', async () => {
    const emptyPage = { data: [], pagination: { total: 0, page: 1 } };
    const held = deferred<typeof emptyPage>();
    let callCount = 0;
    fetchUsersListPageMock.mockImplementation(() => {
      callCount += 1;
      // First call is the unfiltered mount fetch; the second is the search this
      // test types, and it is held open to simulate a request in flight.
      return callCount === 1 ? Promise.resolve(emptyPage) : held.promise;
    });

    renderWithClient();

    const input = await screen.findByPlaceholderText('Search users');
    await waitFor(() => expect(callCount).toBe(1));

    // Nothing to settle on an empty box - no spinner before typing.
    expect(screen.queryByText('Searching')).toBeNull();

    fireEvent.change(input, { target: { value: 'zzqqrare' } });

    // Past the 200ms debounce, the request is out but `held` has not resolved -
    // the icon must still read "searching", not have gone quiet early.
    await waitFor(() => expect(screen.getByText('Searching')).toBeInTheDocument(), {
      timeout: 1000,
    });

    held.resolve(emptyPage);

    await waitFor(() => expect(screen.queryByText('Searching')).toBeNull());
  });
});
