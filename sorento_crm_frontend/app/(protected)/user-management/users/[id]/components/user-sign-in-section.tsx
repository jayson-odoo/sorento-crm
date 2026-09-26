'use client';

/**
 * "Sign-in" (S3 2.2, AC-52): a read-only Card under the Profile card, reading
 * `GET /users/{id}` (S3 1.7) - email or phone, whichever WhatsApp contact is
 * linked, the last sign-in, and the two things that need the owner's action:
 * an invitation that has not gone out, and a phone that no longer matches its
 * WhatsApp contact. Editing itself stays in Edit profile; this section only
 * shows the answer.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertContent, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import { RiErrorWarningFill } from '@remixicon/react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { toast } from '@/lib/toast';
import type { User } from '@/app/models/user';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { useUserActions } from '../../actions';
// Aliased: `useNewNumber` is the service's name for the S3 contract 2.5 call,
// not a React hook - eslint's hook-name check goes by the imported binding.
import { useNewNumber as applyContactPhoneToUser } from '../../services/userService';

/** Last 4 digits only, same idea as the masking used elsewhere in this module -
 *  enough to recognise, not enough to dial (S3 2.2). */
function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '');
  if (digits.length <= 4) return phone;
  return `+${digits.slice(0, 2)} *** ${digits.slice(-4)}`;
}

function formatSignInMethod(method: string | null | undefined): string | null {
  if (!method) return null;
  const normalized = method.toLowerCase();
  if (normalized === 'email') return 'email';
  if (normalized === 'phone') return 'phone';
  if (normalized.startsWith('portal')) return 'portal link';
  return normalized;
}

const UserSignInSection = ({ user }: { user: User }) => {
  const queryClient = useQueryClient();
  const { resendInviteAction, dialogs } = useUserActions(user);
  const canEdit = useHasPermission('user_management.users.edit');
  const [applyingNewNumber, setApplyingNewNumber] = useState(false);

  const unlink = useDeferredAction({
    actionKey: 'user.unlink_contact',
    entityType: 'user',
    entityId: user.id,
    verb: 'Unlinking',
    subject: user.linkedContact?.name || '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'WhatsApp contact unlinked',
    invalidateKeys: [['user-user', user.id]],
  });

  const handleUseNewNumber = async () => {
    if (!user.linkedContact?.phone_number) return;
    setApplyingNewNumber(true);
    try {
      await applyContactPhoneToUser(user.id, user.linkedContact.phone_number);
      toast.success('Phone number updated');
      queryClient.invalidateQueries({ queryKey: ['user-user', user.id] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update the phone number');
    } finally {
      setApplyingNewNumber(false);
    }
  };

  const signInMethod = formatSignInMethod(user.lastSignInMethod);

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Sign-in</CardTitle>
        </CardHeading>
        {resendInviteAction && (
          <Button size="sm" onClick={resendInviteAction.run} disabled={resendInviteAction.disabled}>
            {resendInviteAction.label}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm [&_dt]:text-muted-foreground">
          <dt>Email</dt>
          <dd className="flex flex-wrap items-center gap-2">
            {user.email ? <span>{user.email}</span> : <span className="text-muted-foreground">No email</span>}
            {user.needsInvitation && (
              <Badge variant="warning" appearance="light">
                Invitation not sent
              </Badge>
            )}
          </dd>

          <dt>Phone</dt>
          <dd>
            {user.contactNumber ? (
              <span className="flex flex-wrap items-center gap-2">
                <span>{maskPhone(user.contactNumber)}</span>
                <Badge variant={user.phoneVerifiedAt ? 'success' : 'secondary'} appearance="light">
                  {user.phoneVerifiedAt ? 'verified' : 'not verified yet'}
                </Badge>
              </span>
            ) : (
              <span className="text-muted-foreground">
                No phone yet. Add one to allow phone sign-in.
              </span>
            )}
          </dd>

          <dt>WhatsApp contact</dt>
          <dd>
            {user.linkedContact ? (
              <Link
                href={`/user-management/contacts/${user.linkedContact.id}`}
                className="text-primary hover:underline"
              >
                {user.linkedContact.name || 'Unnamed contact'}
                {user.linkedContact.phone_number
                  ? ` · ${maskPhone(user.linkedContact.phone_number)}`
                  : ''}
              </Link>
            ) : (
              <span className="text-muted-foreground">Not linked</span>
            )}
          </dd>

          <dt>Last sign-in</dt>
          <dd>
            {user.lastSignInAt ? (
              <span>
                {formatDateTimeInMalaysia(user.lastSignInAt)}
                {signInMethod ? `, ${signInMethod}` : ''}
              </span>
            ) : (
              <span className="text-muted-foreground">Never</span>
            )}
          </dd>
        </dl>

        {user.phoneDiffersFromContact && (
          <Alert variant="warning" appearance="light" className="mt-4">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertContent>
              <AlertTitle>Needs attention: phone differs from WhatsApp contact.</AlertTitle>
              {canEdit && (
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0"
                  disabled={applyingNewNumber}
                  onClick={() => void handleUseNewNumber()}
                >
                  {applyingNewNumber ? 'Updating…' : 'Use new number'}
                </Button>
              )}
            </AlertContent>
          </Alert>
        )}

        {user.linkedContact && canEdit && (
          <div className="mt-4">
            <DeferredActionButton
              pending={unlink.pending}
              verb="Unlinking"
              onCancel={unlink.cancel}
              idle={
                <Button
                  variant="destructive"
                  onClick={() => unlink.start()}
                  disabled={unlink.isBlocked}
                >
                  Unlink WhatsApp contact
                </Button>
              }
            />
          </div>
        )}
      </CardContent>

      {dialogs}
    </Card>
  );
};

export default UserSignInSection;
