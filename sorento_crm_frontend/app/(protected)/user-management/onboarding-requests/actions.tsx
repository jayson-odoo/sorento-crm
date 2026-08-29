'use client';

/**
 * The Onboarding Request action set (D15).
 *
 * The list row and the record's gear render this one array, in this order, so a
 * captain does not have to open a request to revoke a link that is already out.
 * Before this the row offered a chevron and nothing else.
 *
 * Copy link is the only item that can be absent on a row: the intake URL is a
 * credential and the list payload deliberately does not carry it, so the item
 * appears where the URL does. That is the same rule as a permission-filtered
 * action - what cannot be run is not offered.
 */

import { useState } from 'react';
import { Copy, KeyRound, Link2Off, Trash2 } from 'lucide-react';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { toast } from 'sonner';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import type { OnboardingRequestStatus } from '@/components/common/onboarding/types';
import { useOnboardingRequestMutations } from './hooks/useOnboardingRequests';

/** What a list row carries; the record hands over the same plus `intake_url`. */
export interface OnboardingActionTarget {
  id: string;
  title: string;
  status: OnboardingRequestStatus;
  revoked_at: string | null;
  /** Reviewers only, and detail only - see the note above. */
  intake_url?: string | null;
  /** People on the request, for the delete confirmation. Detail only. */
  people_count?: number;
}

export interface UseOnboardingRequestActionsOptions {
  /** Where to go once the request is gone (the record page returns to the list). */
  onDeleted?: () => void;
}

export function useOnboardingRequestActions(
  request: OnboardingActionTarget | null | undefined,
  { onDeleted }: UseOnboardingRequestActionsOptions = {},
): RecordActionSet {
  const { revoke, regenerate, remove } = useOnboardingRequestMutations(request?.id ?? '');
  const { copyToClipboard } = useCopyToClipboard({
    onCopy: () => toast.success('Link copied'),
  });
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (!request) return { actions: [] };

  const linkLive = !request.revoked_at;
  const canAdministerLink = ['draft', 'sent'].includes(request.status);
  const actions: RecordAction[] = [];

  if (request.intake_url) {
    actions.push({
      key: 'onboarding.copy_link',
      label: 'Copy link',
      icon: Copy,
      disabled: !linkLive,
      run: () => copyToClipboard(request.intake_url as string),
    });
  }

  actions.push(
    {
      key: 'onboarding.revoke_link',
      label: 'Revoke link',
      icon: Link2Off,
      disabled: !linkLive || !canAdministerLink || revoke.isPending,
      run: () => revoke.mutate(),
    },
    {
      key: 'onboarding.regenerate_link',
      label: 'Issue a new link',
      icon: KeyRound,
      disabled: !canAdministerLink || regenerate.isPending,
      run: () => regenerate.mutate(),
    },
    {
      key: 'onboarding.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    },
  );

  const people = request.people_count ?? 0;

  const dialogs = (
    <ConfirmDeleteDialog
      open={deleteOpen}
      onOpenChange={setDeleteOpen}
      description={
        <>
          Delete <strong>{request.title}</strong>
          {people > 0 ? ` and its ${people} ${people === 1 ? 'person' : 'people'}` : ''}? This
          action cannot be undone.
        </>
      }
      onDelete={async () => {
        await remove.mutateAsync();
      }}
      queryKeysToInvalidate={[['onboarding-requests']]}
      successMessage="Onboarding request deleted"
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}
