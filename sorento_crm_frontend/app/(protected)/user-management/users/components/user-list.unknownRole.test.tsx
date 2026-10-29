/**
 * FILTER-MULTISELECT PR2 review: an id the options do not hold (a role from an old link, or before the
 * role lookup has answered) is never shown as its own label: no UUID appears in the trigger or a chip.
 * Uses the real SearchableMultiSelect, whose trigger is what is under test.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const fetchUsersListPageMock = vi.fn();
const url = vi.hoisted(() => ({ search: '' }));
vi.mock('../lib/listQuery', async () => {
  const actual = await vi.importActual<typeof import('../lib/listQuery')>('../lib/listQuery');
  return { ...actual, fetchUsersListPage: (...args: unknown[]) => fetchUsersListPageMock(...args) };
});
vi.mock('../../roles/hooks/use-role-select-query', () => ({
  useRoleSelectQuery: () => ({
    data: [
      { id: 'role-a', name: 'Sales' },
      { id: 'role-b', name: 'Finance' },
    ],
  }),
}));
vi.mock('./user-add-dialog', () => ({ default: () => null }));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (k: string) => ({ listing_key: k, config: null })),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/users',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('next-auth/react', () => ({ useSession: () => ({ data: { user: { id: 'admin', email: 'admin@zzt.test' } } }) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import UserList from './user-list';

const ROW = {
  id: 'user-1', name: 'ZZT Person', email: 'zzt@example.test', avatar: null, status: 'ACTIVE',
  roles: [{ id: 'role-a', name: 'Sales' }], createdAt: '2026-01-05T02:00:00', updatedAt: '2026-01-05T02:00:00',
};

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UserList />
    </QueryClientProvider>,
  );
}
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

beforeEach(() => {
  vi.clearAllMocks();
  url.search = '';
  fetchUsersListPageMock.mockResolvedValue({ data: [ROW], pagination: { total: 1, page: 1 } });
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
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


const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i;
const ORPHAN = '9f1b6c52-4d1e-4a39-8a77-0c2d5e8b1f34';

describe('Users list - a role id the options do not hold', () => {
  it('shows no UUID in the chip or the Role trigger', async () => {
    url.search = `roleId=${ORPHAN}`;
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT Person');
    await user.click(filtersButton());
    await screen.findByTestId('users-filters-popover');
    expect(document.body.textContent ?? '').not.toMatch(UUID);
  });

  it('shows no UUID beside a known role either', async () => {
    url.search = `roleId=role-a%2C${ORPHAN}`;
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT Person');
    await user.click(filtersButton());
    await screen.findByTestId('users-filters-popover');
    expect(document.body.textContent ?? '').not.toMatch(UUID);
    expect(document.body.textContent ?? '').toMatch(/Sales/);
  });
});
