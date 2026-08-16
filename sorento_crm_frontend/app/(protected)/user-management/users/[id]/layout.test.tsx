/**
 * The Activity Logs tab fetches `/api/user-management/users/{id}/logs`, which
 * proxies to `GET /system-logs/users/{user_id}` - gated on
 * `user_management.logs.view` by
 * documentation/plans/security/PLAN-user-management-read-gates.md. A role holding
 * `user_management.users.view` and not `logs.view` reaches this page, so the tab
 * must not be offered to it: clicking it can only error.
 */
import React, { Suspense } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import UserLayout from './layout';

const hasPermission = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/users/u1',
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/components/common/RecordNavigation', () => ({
  default: () => null,
}));

// Container reads the settings provider, which this test has no business standing up.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('./components/user-hero', () => ({
  default: () => null,
}));

const USER = {
  id: 'u1',
  name: 'Ada',
  email: 'ada@example.com',
  roles: [],
  is_protected: false,
};

// One stable promise: `use(params)` suspends, and a promise recreated on every
// render suspends again forever.
const PARAMS = Promise.resolve({ id: 'u1' });

async function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={null}>
          <UserLayout params={PARAMS}>
            <div>child</div>
          </UserLayout>
        </Suspense>
      </QueryClientProvider>,
    );
  });
}

beforeEach(async () => {
  // Settled before the first render, so `use(PARAMS)` never suspends mid-act.
  await PARAMS;
  hasPermission.mockReset();
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => USER,
  } as unknown as Response);
});

afterEach(() => {
  cleanup();
});

describe('user detail tabs', () => {
  it('offers the Activity Logs tab to a caller holding logs.view', async () => {
    hasPermission.mockImplementation((slug: string) => slug === 'user_management.logs.view');

    await renderLayout();

    await waitFor(() => expect(screen.getByText('Profile')).toBeTruthy());
    expect(screen.getByText('Activity Logs')).toBeTruthy();
  });

  it('hides the Activity Logs tab from a caller without logs.view', async () => {
    hasPermission.mockReturnValue(false);

    await renderLayout();

    await waitFor(() => expect(screen.getByText('Profile')).toBeTruthy());
    expect(screen.queryByText('Activity Logs')).toBeNull();
    expect(hasPermission).toHaveBeenCalledWith('user_management.logs.view');
  });
});
