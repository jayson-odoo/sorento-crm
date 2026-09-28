/**
 * `useUserActions` - "Send invitation email" (s3-contract.md 2.2, AC-57).
 *
 * One deliberate, off-by-default send: the action is absent for a user with
 * no email, opens a confirmation naming the address, Cancel is focused by
 * default, and Cancel/Escape/closing send nothing - only "Send email" calls
 * `POST /users/{id}/resend-invite`.
 *
 * A small harness renders the hook's own return value (the action button plus
 * its dialogs), since `useUserActions` is a hook, not a component.
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
  const invite = actions.find((a) => a.key === 'user.resend_invite');
  return (
    <div>
      {invite && (
        <button type="button" onClick={invite.run} disabled={invite.disabled}>
          {invite.label}
        </button>
      )}
      {dialogs}
    </div>
  );
}

function renderHarness(user: User) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness user={user} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({ message: 'Invitation email sent.' }),
  });
});

afterEach(() => cleanup());

describe('useUserActions - the invite action itself', () => {
  it('reads "Send invitation email"', () => {
    renderHarness(testUser());
    expect(screen.getByRole('button', { name: 'Send invitation email' })).toBeInTheDocument();
  });

  it('is absent for a user with no email', () => {
    renderHarness(testUser({ email: '' }));
    expect(screen.queryByRole('button', { name: 'Send invitation email' })).not.toBeInTheDocument();
  });
});

describe('useUserActions - the confirmation dialog', () => {
  it('opens "Send invitation email?" naming the address, Cancel focused', async () => {
    renderHarness(testUser({ email: 'kia@zzt.test' }));
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation email' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Send invitation email?');
    expect(dialog).toHaveTextContent('kia@zzt.test');

    const cancel = screen.getByRole('button', { name: 'Cancel' });
    await waitFor(() => expect(cancel).toHaveFocus());
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('Cancel sends nothing and closes', async () => {
    renderHarness(testUser());
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation email' }));
    await screen.findByRole('alertdialog');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('Escape sends nothing and closes', async () => {
    renderHarness(testUser());
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation email' }));
    await screen.findByRole('alertdialog');

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape', code: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('"Send email" calls resend-invite exactly once', async () => {
    renderHarness(testUser());
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation email' }));
    await screen.findByRole('alertdialog');

    fireEvent.click(screen.getByRole('button', { name: 'Send email' }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/user-management/users/user-1/resend-invite',
      expect.objectContaining({ method: 'POST' }),
    );

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });
});
