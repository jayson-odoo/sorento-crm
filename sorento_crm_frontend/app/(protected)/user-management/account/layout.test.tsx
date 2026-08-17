/**
 * The My account Logs tab fetches `/api/user-management/account/logs`, which
 * proxies to `GET /system-logs/` - gated on `user_management.logs.view` by
 * documentation/plans/security/PLAN-user-management-read-gates.md. A role holding
 * `account.view` without `logs.view` reaches this page, so the tab must not be
 * offered to it: clicking it can only error. Twin of the user-detail Activity
 * Logs tab, same treatment.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import Layout from './layout';

const hasPermission = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/account',
  useRouter: () => ({ push: vi.fn() }),
}));

// Container reads the settings provider, which this test has no business standing up.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const ACCOUNT = {
  id: 'u1',
  name: 'Ada',
  email: 'ada@example.com',
  roles: [{ name: 'Director' }],
  avatar: null,
};

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Layout>
        <div>child</div>
      </Layout>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hasPermission.mockReset();
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ACCOUNT,
  } as unknown as Response);
});

afterEach(() => {
  cleanup();
});

describe('my account tabs', () => {
  it('offers the Logs tab to a caller holding logs.view', async () => {
    hasPermission.mockImplementation((slug: string) => slug === 'user_management.logs.view');

    renderLayout();

    await waitFor(() => expect(screen.getByText('Profile')).toBeTruthy());
    expect(screen.getByText('Logs')).toBeTruthy();
  });

  it('hides the Logs tab from a caller without logs.view', async () => {
    hasPermission.mockReturnValue(false);

    renderLayout();

    await waitFor(() => expect(screen.getByText('Profile')).toBeTruthy());
    expect(screen.getByText('Security')).toBeTruthy();
    expect(screen.queryByText('Logs')).toBeNull();
    expect(hasPermission).toHaveBeenCalledWith('user_management.logs.view');
  });
});
