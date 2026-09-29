/**
 * Administrative Users, Roles column (owner rule 29 Sep 2026, AC-PO-1/AC-PO-2): a user with
 * several roles reads as ONE row line - the roles that fit, then "+N" - and "+N" opens a
 * popover listing every role, on top of the list, closed by Escape.
 *
 * jsdom lays the row out at width 0, so the shared `PillOverflow` shows only the first
 * pill and folds the rest behind "+N" - the fit math itself is covered by
 * `components/common/PillOverflow.test.tsx`. Every visible-pill query is scoped to the
 * cell's own test id: the hidden measuring row repeats the same labels off-screen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const fetchUsersListPageMock = vi.fn();
vi.mock('../lib/listQuery', async () => {
  const actual =
    await vi.importActual<typeof import('../lib/listQuery')>(
      '../lib/listQuery',
    );
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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

// Exposed so a test can assert the row behind a pill or a popover never opens.
const routerPush = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: routerPush }),
  usePathname: () => '/user-management/users',
  useSearchParams: () => new URLSearchParams(),
}));

// A real row renders its actions menu, which reads the signed-in user.
vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'admin', email: 'admin@zzt.test' } },
  }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import UserList from './user-list';

const MR_LOO = {
  id: 'user-loo',
  name: 'Mr Loo',
  email: 'loo@zzt.test',
  avatar: null,
  status: 'ACTIVE',
  roles: [
    { id: 'role-pm', name: 'Purchasing Manager Role' },
    { id: 'role-pe', name: 'Purchasing Executive' },
    { id: 'role-p', name: 'Purchasing' },
  ],
  createdAt: '2026-01-05T02:00:00',
  updatedAt: '2026-01-05T02:00:00',
};

const ONE_ROLE = {
  ...MR_LOO,
  id: 'user-one',
  name: 'One Role',
  email: 'one@zzt.test',
  roles: [{ id: 'role-p', name: 'Purchasing' }],
};

function renderWithClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <UserList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchUsersListPageMock.mockReset();
  routerPush.mockReset();
  fetchUsersListPageMock.mockResolvedValue({
    data: [MR_LOO, ONE_ROLE],
    pagination: { total: 2, page: 1 },
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

describe('UserList - Roles column folds to one line with "+N" (AC-PO-1, AC-PO-2)', () => {
  it('shows the first role and a "+N" chip counting the folded ones', async () => {
    renderWithClient();
    const cell = within(await screen.findByTestId('user-roles-user-loo'));

    expect(cell.getByText('Purchasing Manager Role')).toBeInTheDocument();
    expect(cell.getByText('+2')).toBeInTheDocument();
    expect(cell.queryByText('Purchasing Executive')).not.toBeInTheDocument();
    // The whole strip is one labelled group, so a screen reader names whose roles these are.
    expect(
      screen.getByRole('group', { name: 'Roles of Mr Loo' }),
    ).toBeInTheDocument();
  });

  it('shows no "+N" for a user with one role (AC-PO-6)', async () => {
    renderWithClient();
    const cell = within(await screen.findByTestId('user-roles-user-one'));

    expect(cell.getByText('Purchasing')).toBeInTheDocument();
    expect(cell.queryByText(/^\+\d+$/)).not.toBeInTheDocument();
  });

  it('"+N" opens a popover listing every role, and Escape closes it', async () => {
    renderWithClient();
    const cell = within(await screen.findByTestId('user-roles-user-loo'));

    fireEvent.click(cell.getByText('+2'));

    const popover = within(
      await screen.findByTestId('user-roles-user-loo-popover'),
    );
    expect(popover.getByText('Purchasing Manager Role')).toBeInTheDocument();
    expect(popover.getByText('Purchasing Executive')).toBeInTheDocument();
    expect(popover.getByText('Purchasing')).toBeInTheDocument();

    fireEvent.keyDown(screen.getByTestId('user-roles-user-loo-popover'), {
      key: 'Escape',
    });
    await waitFor(() =>
      expect(
        screen.queryByTestId('user-roles-user-loo-popover'),
      ).not.toBeInTheDocument(),
    );
  });

  it('neither "+N" nor an item inside the popover opens the row behind it (review must-fix)', async () => {
    renderWithClient();
    const cell = within(await screen.findByTestId('user-roles-user-loo'));

    fireEvent.click(cell.getByText('+2'));
    const popover = within(
      await screen.findByTestId('user-roles-user-loo-popover'),
    );
    // The portal moves the popover out of the row in the DOM, but React events still
    // bubble up the component tree to the row's own click handler.
    fireEvent.click(popover.getByText('Purchasing Executive'));

    expect(routerPush).not.toHaveBeenCalled();
  });

  it('"+N" is keyboard reachable: Enter opens the same popover', async () => {
    renderWithClient();
    const cell = within(await screen.findByTestId('user-roles-user-loo'));
    const more = cell.getByText('+2');
    expect(more).toHaveAttribute('tabindex', '0');

    more.focus();
    fireEvent.keyDown(more, { key: 'Enter' });

    expect(
      await screen.findByTestId('user-roles-user-loo-popover'),
    ).toBeInTheDocument();
  });
});
