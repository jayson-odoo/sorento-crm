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

import { Copy, KeyRound, Link2Off, Trash2 } from 'lucide-react';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { toast } from 'sonner';

import { useDeferredAction } from '@/hooks/useDeferredAction';
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
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export function useOnboardingRequestActions(
  request: OnboardingActionTarget | null | undefined,
  { onDeleted, surface = 'inline' }: UseOnboardingRequestActionsOptions = {},
): RecordActionSet {
  const { revoke, regenerate } = useOnboardingRequestMutations(request?.id ?? '');
  const { copyToClipboard } = useCopyToClipboard({
    onCopy: () => toast.success('Link copied'),
  });
  // Delete asks nothing (D7): the countdown takes the record's primary slot, or
  // the toast on a list row, and its people go with the request either way.
  const deletion = useDeferredAction({
    actionKey: 'onboarding_request.delete',
    entityType: 'onboarding_request',
    entityId: request?.id,
    verb: 'Deleting',
    subject: request?.title ?? '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Onboarding request deleted',
    invalidateKeys: [['onboarding-requests']],
    onCommitted: onDeleted,
  });

  if (!request) return { actions: [], dialogs: null, pending: null };

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
      disabled: deletion.isPending,
      run: deletion.start,
    },
  );

  return { actions, dialogs: null, pending: deletion.countdown };
}
