/**
 * The Users list search box keeps focus while typing.
 *
 * `DataGridToolbar` used to be defined INSIDE `UserList`'s render body. The
 * search box's own value lived in the parent (`useDebouncedSearch`), so every
 * keystroke re-rendered `UserList`, which created a brand new `DataGridToolbar`
 * function - a new component TYPE, from React's point of view - and React
 * unmounted and remounted the whole toolbar to match, taking the focused input
 * with it. `/user-management/contact-access-agents` never had this bug because
 * its toolbar is built inline in the parent's return, not as a nested
 * component. The fix hoists the toolbar (`UsersToolbar`) to module scope so it
 * keeps one stable identity across re-renders.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
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
// resolves; stub it "loaded" so real rows render synchronously in jsdom.
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

beforeEach(() => {
  fetchUsersListPageMock.mockReset();
  fetchUsersListPageMock.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1 },
  });
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

describe('UserList - search box focus', () => {
  it('keeps focus across two keystrokes', async () => {
    renderWithClient();

    const input = await screen.findByPlaceholderText('Search users');
    input.focus();
    expect(document.activeElement).toBe(input);

    fireEvent.change(input, { target: { value: 'j' } });
    expect(document.activeElement).toBe(input);

    fireEvent.change(input, { target: { value: 'jo' } });
    expect(document.activeElement).toBe(input);

    expect(input).toHaveValue('jo');
  });
});
