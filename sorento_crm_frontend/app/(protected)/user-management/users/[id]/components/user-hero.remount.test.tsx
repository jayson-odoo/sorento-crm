/**
 * The edit dialog must survive a parent re-render.
 *
 * `Content` used to be defined inside UserHero's render, so every re-render of
 * UserHero (the session and company-context focus refetches cause one whenever
 * the tab regains focus) minted a new component type, React remounted the
 * subtree, and the open dialog's `useState` reset - the popup silently closed
 * when the user switched browser tabs and came back.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { User } from '@/app/models/user';
import UserHero from './user-hero';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/user-management/users/u-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/BackToList', () => ({
  useBackToListHref: () => '/user-management/users',
}));

// The gear menu's action set is not what this spec is about.
vi.mock('../../actions', () => ({
  useUserActions: () => ({ actions: [], dialogs: null, pending: null }),
}));

vi.mock('../../lib/listQuery', () => ({
  fetchUsersListPage: vi.fn(),
  usersListQueryKey: vi.fn(() => ['users-list']),
}));

// The pager fetches neighbours; keep the record card inert.
vi.mock('@/components/common/DetailActions', () => ({
  __esModule: true,
  default: ({ dialogs, primary }: { dialogs: React.ReactNode; primary: React.ReactNode }) => (
    <div>
      {primary}
      {dialogs}
    </div>
  ),
}));

vi.mock('./user-profile-edit-dialog', () => ({
  __esModule: true,
  default: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">Edit User Details</div> : null,
}));

const user = {
  id: 'u-1',
  name: 'Someone',
  email: 'someone@example.com',
} as unknown as User;

describe('UserHero edit dialog across parent re-renders', () => {
  it('stays open when the parent re-renders with the same props', () => {
    const { rerender } = render(<UserHero user={user} isLoading={false} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit user' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // What a session/company focus refetch does to this component: same props,
    // new render pass. A remount here is exactly the bug.
    rerender(<UserHero user={user} isLoading={false} />);
    rerender(<UserHero user={{ ...user } as unknown as User} isLoading={false} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
