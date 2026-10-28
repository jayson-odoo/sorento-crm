/**
 * FILTER-MULTISELECT PR 2: the Users list's Role and Status filters take several values (OR within a
 * filter). The "Add condition" builder, where a second row of the same field silently overwrote the
 * first, is gone: one multi control per field, one chip per filter, comma-joined in the URL.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
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
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

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
const lastFilters = () => {
  const calls = fetchUsersListPageMock.mock.calls;
  return calls[calls.length - 1][0].filters as Record<string, string>;
};
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

describe('Users list - multi Role and Status filters', () => {
  it('offers Role and Status as multi controls, with no condition builder', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT Person');
    await user.click(filtersButton());
    expect((await screen.findByLabelText('Role: any')).hasAttribute('multiple')).toBe(true);
    expect(screen.getByLabelText('Status: any').hasAttribute('multiple')).toBe(true);
    expect(screen.queryByText('Add condition')).toBeNull();
  });

  it('two roles go to the API comma-joined and read as one chip', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT Person');
    await user.click(filtersButton());
    await user.selectOptions(await screen.findByLabelText('Role: any'), ['role-a', 'role-b']);
    await waitFor(() => expect(lastFilters().roleId).toBe('role-a,role-b'));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
    expect(screen.getByText('Role: Sales, Finance')).toBeInTheDocument();
  });

  it('two statuses go to the API comma-joined and AND with the role', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT Person');
    await user.click(filtersButton());
    await user.selectOptions(await screen.findByLabelText('Role: any'), ['role-b']);
    await user.selectOptions(screen.getByLabelText('Status: any'), ['ACTIVE', 'INACTIVE']);
    await waitFor(() => expect(lastFilters()).toMatchObject({ roleId: 'role-b', status: 'ACTIVE,INACTIVE' }));
  });

  it('an older link with one role and one status reads back as one-value filters', async () => {
    url.search = 'roleId=role-b&status=INACTIVE';
    renderList();
    await screen.findByText('ZZT Person');
    await waitFor(() => expect(lastFilters()).toMatchObject({ roleId: 'role-b', status: 'INACTIVE' }));
    expect(screen.getByText('Role: Finance')).toBeInTheDocument();
    expect(screen.getByText('Status: Inactive')).toBeInTheDocument();
  });

  it('clearing the chip drops the whole filter', async () => {
    url.search = 'roleId=role-a%2Crole-b';
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT Person');
    await user.click(await screen.findByRole('button', { name: 'Clear filter: Role: Sales, Finance' }));
    await waitFor(() => expect(lastFilters().roleId).toBeUndefined());
  });
});
