/**
 * QUOTE-ATTN-PICKER crew pass (11 Nov): the Confirm Impersonation dialog says what really happens.
 * The backend makes the target the effective user, so records are saved as them, and the audit
 * log keeps the admin (`dependencies.py` `_maybe_apply_impersonation`, `audit_logs.real_user_id`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UserStatus, type User } from '@/app/models/user';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'admin-1', email: 'admin@zzt.test' } } }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

vi.mock('@/hooks/useImpersonation', () => ({
  useImpersonation: () => ({ start: vi.fn(), starting: false }),
}));

// The deletion action lives in the same hook; stubbed inert so this file stays
// about the invite dialog alone (deletion has no test surface here).
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({
    pending: null,
    isPending: false,
    isBlocked: false,
    start: vi.fn(),
    cancel: vi.fn(),
    countdown: null,
  }),
}));

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetchMock(...a) }));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useUserActions } from './actions';

function testUser(over: Partial<User> = {}): User {
  return {
    id: 'user-1',
    email: 'kia@zzt.test',
    name: 'Kia Yee',
    status: UserStatus.ACTIVE,
    isTrashed: false,
    isProtected: false,
    ...over,
  } as unknown as User;
}

function Harness({ user }: { user: User }) {
  const { actions, dialogs } = useUserActions(user);
  const impersonate = actions.find((a) => a.key === 'user.impersonate');
  return (
    <div>
      {impersonate && (
        <button type="button" onClick={impersonate.run}>
          {impersonate.label}
        </button>
      )}
      {dialogs}
    </div>
  );
}

afterEach(() => cleanup());

describe('Confirm Impersonation copy', () => {
  it('says records are saved as the user and the audit log shows the admin', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = {
      id: 'user-1', email: 'kia@example.com', name: 'Test Salesperson A', status: UserStatus.ACTIVE,
      isTrashed: false, isProtected: false,
    } as unknown as User;
    render(
      <QueryClientProvider client={client}>
        <Harness user={user} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate user' }));
    const dialog = screen.getByTestId('impersonate-confirm-dialog');
    expect(dialog).toHaveTextContent(
      'Records you create are saved as Test Salesperson A; the audit log shows you did it.',
    );
    expect(dialog).not.toHaveTextContent('attributed to you');
  });
});
