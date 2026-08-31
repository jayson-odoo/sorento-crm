'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { getInitials } from '@/lib/helpers';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import DetailActions from '@/components/common/DetailActions';
import { useBackToListHref } from '@/components/common/BackToList';
import { User } from '@/app/models/user';
import { useUserActions } from '../../actions';
import { fetchUsersListPage, usersListQueryKey } from '../../lib/listQuery';
import UserProfileEditDialog from './user-profile-edit-dialog';

interface UserProfileProps {
  user: User;
  isLoading: boolean;
}

/**
 * The record card: identity on the left, and on the right the pager, the gear
 * and the one primary button (D6). The toolbar row above carries Back alone.
 */
/**
 * Defined at module scope ON PURPOSE. As `const Content = () => ...` inside
 * UserHero's render, every parent re-render minted a NEW component type, so
 * React remounted this whole subtree - and the edit dialog's `useState` reset,
 * which is why the dialog vanished when the tab regained focus (the session
 * and company-context focus refetches re-render everything above it).
 */
const HeroLoading = () => {
  return (
    <div className="flex items-center gap-5 mb-5">
      <Skeleton className="size-14 rounded-full" />
      <div className="space-y-1">
        <Skeleton className="h-6 w-36" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-4 w-60" />
      </div>
    </div>
  );
};

const HeroContent = ({ user }: { user: User }) => {
  const router = useRouter();
  const backHref = useBackToListHref('/user-management/users');
  const [isEditDialogOpen, setEditDialogOpen] = useState(false);
  const { actions, dialogs, pending } = useUserActions(user, {
    // Deleted from the record: land where Back would have landed, on the page
    // and filters the reader left the list on.
    onDeleted: () => router.push(backHref),
  });

  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-center gap-5 min-w-0">
        <Avatar className="h-14 w-14">
          {user.avatar ? (
            <AvatarImage src={user.avatar} alt={user.name || ''} />
          ) : (
            <AvatarFallback className="text-xl">
              {getInitials(user.name || user.email)}
            </AvatarFallback>
          )}
        </Avatar>
        <div className="space-y-px min-w-0">
          <div className="font-medium text-base break-words">{user.name}</div>
          <div className="text-muted-foreground text-sm break-words">{user.email}</div>
        </div>
      </div>

      <DetailActions
        pager={{
          detailPath: '/user-management/users',
          currentId: user.id,
          listQueryKey: usersListQueryKey,
          fetchPage: fetchUsersListPage,
          ariaLabel: 'user',
        }}
        actions={actions}
        dialogs={
          <>
            {dialogs}
            <UserProfileEditDialog
              open={isEditDialogOpen}
              closeDialog={() => setEditDialogOpen(false)}
              user={user}
            />
          </>
        }
        pendingAction={pending}
        gearLabel="User options"
        primary={<Button onClick={() => setEditDialogOpen(true)}>Edit user</Button>}
      />
    </div>
  );
};

const UserHero = ({ user, isLoading }: UserProfileProps) => {
  return isLoading || !user ? <HeroLoading /> : <HeroContent user={user} />;
};

export default UserHero;
