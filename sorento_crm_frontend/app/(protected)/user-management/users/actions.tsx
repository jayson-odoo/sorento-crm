'use client';

/**
 * The Users action set (D15): Impersonate, Send invitation email, Delete.
 *
 * One definition, three surfaces - the list row's "..." menu, the record page's
 * gear, and the record's own Sign-in section (S3 2.2) all render this array (or,
 * for the section, just call the same hook), so Impersonate is no longer
 * list-only and Delete is no longer record-only. Permissions are resolved here,
 * once: an action the user may not run is not in the array.
 *
 * Trashing asks nothing (D7): it parks `user.delete` for ten seconds and the
 * countdown takes the primary button's place, or goes to a toast when the action
 * came from a list row. The email the old dialog made you retype is gone with it.
 *
 * Sending the invitation (Q17, AC-57) is the one action here that DOES ask
 * first: it is a deliberate, off-by-default send, not a deferred window - a
 * cancelled countdown reads as "changed my mind before it happened", but this
 * would have to describe a possible email that already left.
 */

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon, Mail, Trash2, UserCog } from 'lucide-react';
import { toast } from '@/lib/toast';
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

export interface UseUserActionsOptions {
  /** Where to go once the record is gone (the record page returns to the list). */
  onDeleted?: () => void;
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export interface UseUserActionsResult extends RecordActionSet {
  /** The `user.resend_invite` entry, so the Sign-in section's own "Send
   *  invitation email" button (S3 2.2) can run the exact same handler and
   *  confirmation instead of reimplementing the "has no email" gate. */
  resendInviteAction: RecordAction | null;
}

export function useUserActions(
  user: User | undefined | null,
  { onDeleted, surface = 'inline' }: UseUserActionsOptions = {},
): UseUserActionsResult {
  const queryClient = useQueryClient();
  const { data: nextAuthSession } = useSession();
  const currentUserId = nextAuthSession?.user?.id;
  const { start: startImpersonate, starting: startingImpersonate } = useImpersonation();
  const canEdit = useHasPermission('user_management.users.edit');
  const canDelete = useHasPermission('user_management.users.delete');

  const [impersonateOpen, setImpersonateOpen] = useState(false);
  const [inviteConfirmOpen, setInviteConfirmOpen] = useState(false);
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
  });

  const sendInvitationEmail = async () => {
    if (!user) return;
    setInvitePending(true);
    try {
      const res = await apiFetch(
        `/api/user-management/users/${user.id}/resend-invite`,
        { method: 'POST' },
      );
      if (!res.ok) {
        toast.error(await extractApiError(res, 'Failed to send the invitation email.'));
        return;
      }
      const data = await res.json();
      toast.success(data.message ?? 'Invitation email sent.');
      queryClient.invalidateQueries({ queryKey: ['user-user', user.id] });
    } catch {
      toast.error('Failed to send the invitation email.');
    } finally {
      setInvitePending(false);
      setInviteConfirmOpen(false);
    }
  };

  const actions: RecordAction[] = [];
  if (!user) return { actions, dialogs: null, pending: null, resendInviteAction: null };

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

  // Hidden entirely for a user with no email - there is nowhere to send it
  // (AC-52, AC-57).
  if (canEdit && user.email) {
    actions.push({
      key: 'user.resend_invite',
      label: 'Send invitation email',
      icon: Mail,
      disabled: invitePending,
      run: () => setInviteConfirmOpen(true),
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

      {/* Send invitation email? (AC-57): Cancel is the default focus, Escape and
          closing send nothing - only "Send email" calls the endpoint. */}
      <AlertDialog open={inviteConfirmOpen} onOpenChange={setInviteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Send invitation email?</AlertDialogTitle>
            <AlertDialogDescription>
              An email with a link to set a password goes to <strong>{user.email}</strong>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel autoFocus disabled={invitePending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void sendInvitationEmail();
              }}
              disabled={invitePending}
            >
              {invitePending && <LoaderCircleIcon className="size-4 animate-spin" />}
              Send email
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );

  return {
    actions,
    dialogs,
    pending: deletion.countdown,
    // The Sign-in section's own header button (S3 2.2) runs the SAME action,
    // rather than duplicating the "has no email" gate and the confirmation.
    resendInviteAction: actions.find((a) => a.key === 'user.resend_invite') ?? null,
  };
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
