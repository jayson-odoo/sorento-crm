/**
 * Fix round 2, N6 (reviewer pass at 6a7f0bcd): "Last Sign In" appeared twice on
 * the user page, in the Profile card and in the S3 Sign-in section. The Sign-in
 * section keeps it (it also says how); the Profile card no longer shows it.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UserStatus, type User } from '@/app/models/user';

vi.mock('next-auth/react', () => ({ useSession: () => ({ data: null }) }));
vi.mock('@/lib/is-superadmin', () => ({ isSuperadminUser: () => false }));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/app/providers/CompanyProvider', () => ({ useCompany: () => ({ companies: [] }) }));

import UserProfile from './user-profile';

afterEach(() => cleanup());

describe('UserProfile - no duplicate last sign-in (N6)', () => {
  it('does not show "Last Sign In", which the Sign-in section carries', () => {
    const user = {
      id: 'user-1',
      email: 'kia@zzt.test',
      name: 'Kia Yee',
      status: UserStatus.ACTIVE,
      isTrashed: false,
      lastSignInAt: '2026-02-01T03:00:00Z',
      productDiscontinuedScopes: [],
    } as unknown as User;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <UserProfile user={user} isLoading={false} />
      </QueryClientProvider>,
    );

    expect(screen.getByText('kia@zzt.test')).toBeInTheDocument();
    expect(screen.queryByText(/Last Sign In/i)).not.toBeInTheDocument();
  });
});
