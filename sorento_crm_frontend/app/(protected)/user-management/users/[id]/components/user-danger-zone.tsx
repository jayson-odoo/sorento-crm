'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { User } from '@/app/models/user';
import { useForceLogoutUserMutation } from '@/hooks/useSessions';
import UserDeleteDialog from './user-delete-dialog';
import UserRestoreDialog from './user-restore-dialog';
import UserPermanentDeleteDialog from './user-permanent-delete-dialog';

const UserDangerZone = ({
  user,
  isLoading,
}: {
  user: User;
  isLoading: boolean;
}) => {
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [isRestoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [isPermanentDeleteDialogOpen, setPermanentDeleteDialogOpen] = useState(false);
  const forceLogout = useForceLogoutUserMutation();

  // Render skeleton when loading
  const Loading = () => (
    <div className="space-y-3">
      <Skeleton className="h-8 w-36" />
      <Card>
        <CardContent>
          <Skeleton className="h-7 w-40 mb-3" />
          <Skeleton className="h-6 w-full max-w-[560px] mb-4" />
          <Skeleton className="h-9 w-24" />
        </CardContent>
      </Card>
    </div>
  );

  // Content for the "Delete user" Danger Zone (trash = soft delete)
  const DeleteContent = () => (
    <div className="space-y-3">
      <h2 className="font-semibold text-destructive">Danger Zone</h2>
      <Card>
        <CardContent>
          <h3 className="font-semibold mb-3">Sign out everywhere</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Revoke every active session for this user. They will be signed out of all devices
            immediately and must log in again.
          </p>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" disabled={forceLogout.isPending}>
                {forceLogout.isPending ? 'Signing out…' : 'Sign out everywhere'}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Sign this user out of all devices?</AlertDialogTitle>
                <AlertDialogDescription>
                  {user.name || user.email} will be signed out everywhere immediately. This cannot
                  be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => forceLogout.mutate(user.id)}>
                  Sign out everywhere
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <h3 className="font-semibold mb-3">Trash user account</h3>
          <p className="text-sm text-muted-foreground mb-4">
            This will move the user to the trash. They can be restored later from the user list (Trashed only filter).
          </p>
          <Button
            variant="destructive"
            onClick={() => setDeleteDialogOpen(true)}
            disabled={user.role?.isProtected}
          >
            Trash user
          </Button>
        </CardContent>
      </Card>
      <UserDeleteDialog
        open={isDeleteDialogOpen}
        closeDialog={() => setDeleteDialogOpen(false)}
        user={user}
      />
    </div>
  );

  // Content for restoring or permanently deleting a trashed user.
  const RestoreContent = () => (
    <div className="space-y-3">
      <h2 className="font-semibold text-destructive">Trashed Account</h2>
      <Card>
        <CardContent className="space-y-4">
          <h3 className="font-semibold mb-3">Restore or permanently delete</h3>
          <p className="text-sm text-muted-foreground mb-4">
            This account is currently trashed. You can restore it or permanently delete it and all related data.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setRestoreDialogOpen(true)}>
              Restore user
            </Button>
            <Button
              variant="destructive"
              onClick={() => setPermanentDeleteDialogOpen(true)}
            >
              Permanently delete
            </Button>
          </div>
        </CardContent>
      </Card>
      <UserRestoreDialog
        open={isRestoreDialogOpen}
        closeDialog={() => setRestoreDialogOpen(false)}
        user={user}
      />
      <UserPermanentDeleteDialog
        open={isPermanentDeleteDialogOpen}
        closeDialog={() => setPermanentDeleteDialogOpen(false)}
        user={user}
      />
    </div>
  );

  // Render loading if still fetching or if user is null.
  return isLoading || !user ? (
    <Loading />
  ) : user.isTrashed ? (
    <RestoreContent />
  ) : (
    <DeleteContent />
  );
};

export default UserDangerZone;
