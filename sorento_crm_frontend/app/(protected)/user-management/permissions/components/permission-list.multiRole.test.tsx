/**
 * FILTER-MULTISELECT PR2: the Permissions list's Role filter takes several roles (OR within the
 * filter). The roles go comma-joined as `roleId`, one chip names them, clearing the chip drops the
 * whole filter, and no UUID is ever shown.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetchMock(...a) }));
vi.mock('../../roles/hooks/use-role-select-query', () => ({
  useRoleSelectQuery: () => ({
    data: [
      { id: '11111111-1111-4111-8111-111111111111', name: 'Sales' },
      { id: '22222222-2222-4222-8222-222222222222', name: 'Finance' },
      { id: '33333333-3333-4333-8333-333333333333', name: 'Support' },
    ],
    error: null,
    refetch: vi.fn(),
  }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/permissions',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next-auth/react', () => ({ useSession: () => ({ data: { user: { id: 'admin', email: 'admin@zzt.test' } } }) }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('./permission-edit-dialog', () => ({ default: () => null }));
vi.mock('./permission-delete-dialog', () => ({ default: () => null }));
vi.mock('./permission-group-delete-dialog', () => ({ default: () => null }));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (k: string) => ({ listing_key: k, config: null })),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
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

import PermissionList from './permission-list';

const ROW = {
  id: 'perm-1', slug: 'zzt.perm.view', name: 'ZZT Permission', description: null,
  createdAt: '2026-01-05T02:00:00', created_at: '2026-01-05T02:00:00',
};

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PermissionList />
    </QueryClientProvider>,
  );
}
const lastQuery = () => {
  const calls = apiFetchMock.mock.calls;
  const u = String(calls[calls.length - 1][0]);
  return new URLSearchParams(u.slice(u.indexOf('?') + 1));
};
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

beforeEach(() => {
  vi.clearAllMocks();
  apiFetchMock.mockImplementation(async () => ({
    ok: true,
    json: async () => ({ data: [ROW], pagination: { total: 1, page: 1, limit: 10 } }),
  }) as unknown as Response);
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

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderList();
  await screen.findByText('ZZT Permission');
  await user.click(filtersButton());
}

describe('Permissions list - multi Role filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('sends nothing when no role is chosen', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect(lastQuery().get('roleId')).toBeNull();
  });

  it('two roles go to the API comma-joined, with one chip naming both and no id', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const sales = '11111111-1111-4111-8111-111111111111';
    const finance = '22222222-2222-4222-8222-222222222222';
    await user.selectOptions(await screen.findByRole('listbox'), [sales, finance]);
    await waitFor(() => expect(lastQuery().get('roleId')).toBe(`${sales},${finance}`));
    await user.keyboard('{Escape}');
    expect(await screen.findByText('Role: Sales, Finance')).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(sales))).toBeNull();
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('three roles read as the first two and a count', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), [
      '11111111-1111-4111-8111-111111111111',
      '22222222-2222-4222-8222-222222222222',
      '33333333-3333-4333-8333-333333333333',
    ]);
    await user.keyboard('{Escape}');
    expect(await screen.findByText('Role: Sales, Finance +1')).toBeInTheDocument();
  });

  it('clearing the chip drops the whole filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), [
      '11111111-1111-4111-8111-111111111111',
      '22222222-2222-4222-8222-222222222222',
    ]);
    await user.keyboard('{Escape}');
    await user.click(await screen.findByRole('button', { name: 'Clear filter: Role: Sales, Finance' }));
    await waitFor(() => expect(lastQuery().get('roleId')).toBeNull());
    expect(screen.queryByText('Role: Sales, Finance')).toBeNull();
  });
});
