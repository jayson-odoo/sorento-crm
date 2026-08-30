'use client';

/**
 * The Users action set (D15): Impersonate, Send invitation link, Delete.
 *
 * One definition, two surfaces - the list row's "..." menu and the record page's
 * gear both render this array, in this order, so Impersonate is no longer
 * list-only and Delete is no longer record-only. Permissions are resolved here,
 * once: an action the user may not run is not in the array.
 *
 * Trashing asks nothing (D7): it parks `user.delete` for ten seconds and the
 * countdown takes the primary button's place, or goes to a toast when the action
 * came from a list row. The email the old dialog made you retype is gone with it.
 */

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon, Mail, Trash2, UserCog } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useImpersonation } from '@/hooks/useImpersonation';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { User, UserStatus } from '@/app/models/user';
import { deleteUser } from './services/userService';

export interface UseUserActionsOptions {
  /** Where to go once the record is gone (the record page returns to the list). */
  onDeleted?: () => void;
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export function useUserActions(
  user: User | undefined | null,
  { onDeleted, surface = 'inline' }: UseUserActionsOptions = {},
): RecordActionSet {
  const queryClient = useQueryClient();
  const { data: nextAuthSession } = useSession();
  const currentUserId = nextAuthSession?.user?.id;
  const { start: startImpersonate, starting: startingImpersonate } = useImpersonation();
  const canEdit = useHasPermission('user_management.users.edit');
  const canDelete = useHasPermission('user_management.users.delete');

  const [impersonateOpen, setImpersonateOpen] = useState(false);
  const [invitePending, setInvitePending] = useState(false);

  const deletion = useDeferredAction({
    actionKey: 'user.delete',
    entityType: 'user',
    entityId: user?.id,
    verb: 'Trashing',
    subject: user?.name || user?.email || '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'User moved to the trash',
    invalidateKeys: [['user-users'], ['user-user', user?.id]],
    onCommitted: onDeleted,
    // PHASE 1: the server has no `user.delete` handler yet, so the window lapsing
    // runs the trash from here. Phase 2 registers it and drops this.
    commit: user ? () => deleteUser(user.id) : undefined,
  });

  const sendInvitationLink = async () => {
    if (!user) return;
    setInvitePending(true);
    try {
      const res = await apiFetch(
        `/api/user-management/users/${user.id}/resend-invite`,
        { method: 'POST' },
      );
      if (!res.ok) {
        toast.error(await extractApiError(res, 'Failed to send invitation link.'));
        return;
      }
      const data = await res.json();
      toast.success(data.message ?? 'Invitation link sent.');
      queryClient.invalidateQueries({ queryKey: ['user-user', user.id] });
    } catch {
      toast.error('Failed to send invitation link.');
    } finally {
      setInvitePending(false);
    }
  };

  const actions: RecordAction[] = [];
  if (!user) return { actions, dialogs: null, pending: null };

  // Impersonating yourself is a no-op, a deactivated account has nothing to
  // browse, and a protected account is off limits (the server enforces all three).
  const canImpersonate =
    !!currentUserId &&
    user.id !== currentUserId &&
    user.status === UserStatus.ACTIVE &&
    !user.isProtected;

  if (canImpersonate) {
    actions.push({
      key: 'user.impersonate',
      label: 'Impersonate user',
      icon: UserCog,
      disabled: startingImpersonate,
      run: () => setImpersonateOpen(true),
    });
  }

  if (canEdit) {
    actions.push({
      key: 'user.resend_invite',
      label: 'Send invitation link',
      icon: Mail,
      disabled: invitePending,
      run: () => void sendInvitationLink(),
    });
  }

  if (canDelete) {
    actions.push({
      key: 'user.delete',
      label: 'Trash user',
      icon: Trash2,
      kind: 'destructive',
      disabled: user.role?.isProtected || deletion.isPending || deletion.isBlocked,
      run: () => deletion.start(),
    });
  }

  const dialogs = (
    <>
      <AlertDialog open={impersonateOpen} onOpenChange={setImpersonateOpen}>
        <AlertDialogContent data-testid="impersonate-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Impersonation</AlertDialogTitle>
            <AlertDialogDescription>
              You will browse the system as{' '}
              <strong>{user.name || user.email}</strong> with their access rights.
              All records you create or modify will still be attributed to you.
              Continue?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={startingImpersonate}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="impersonate-confirm"
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await startImpersonate(user.id);
                  setImpersonateOpen(false);
                  toast.success(`Now impersonating ${user.name || user.email}`);
                  if (typeof window !== 'undefined') window.location.reload();
                } catch (err) {
                  toast.error(
                    err instanceof Error
                      ? err.message
                      : 'Failed to start impersonation',
                  );
                }
              }}
              disabled={startingImpersonate}
            >
              {startingImpersonate ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Starting...
                </>
              ) : (
                'Impersonate'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );

  return { actions, dialogs, pending: deletion.countdown };
}

/**
 * The list row's "..." cell.
 *
 * A component, not a bare call: the action set owns dialog state, and TanStack
 * renders a `cell` function through `flexRender`, so the hook needs a component
 * of its own to live in.
 */
export function UserRowActions({ user }: { user: User }) {
  const { actions, dialogs } = useUserActions(user, { surface: 'toast' });

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="user" />
      {dialogs}
    </>
  );
}
