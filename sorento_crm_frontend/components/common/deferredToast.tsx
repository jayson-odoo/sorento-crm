'use client';

import { toast } from 'sonner';
import { DeferredCountdown } from './DeferredActionButton';
import type { PendingAction } from '@/services/pendingActionService';

export interface DeferredToastInput {
  pending: PendingAction;
  /** Verb-first copy: "Deleting" reads as "Deleting in 8s". */
  verb: string;
  /** The record the action is running on, in the reader's words. */
  subject: string;
  onCancel: () => void;
  /**
   * The toast's own id. Defaults to the parked action's, which is what makes a
   * countdown dismissable by whoever learns the action ended. A BULK delete parks one
   * action per row behind ONE countdown, so it names its own instead - the toast
   * belongs to the batch, not to whichever member happens to settle first.
   */
  id?: string;
}

/**
 * The countdown for an action started from a LIST ROW (S6-07).
 *
 * A row has nowhere to put a countdown - the record page's primary area does not
 * exist here - so the affordance travels to a toast, and the row itself dims
 * (`rowPending` on the grid) so the reader can see which record it belongs to.
 *
 * The toast holds until the action ends: `dismissDeferredToast` is called on
 * cancel and on commit. Its duration is a safety net only, in case the tab is
 * suspended long enough that nothing ever settles it.
 */
export function deferredToast(input: DeferredToastInput): string | number {
  const { pending, verb, subject, onCancel, id } = input;

  return toast.custom(
    () => (
      <DeferredCountdown
        pending={pending}
        verb={verb}
        subject={subject}
        onCancel={onCancel}
        className="w-full shadow-lg"
      />
    ),
    {
      id: id ?? `pending-action-${pending.id}`,
      duration: pending.window_seconds * 1000 + 8000,
    },
  );
}

export function dismissDeferredToast(id: string | number): void {
  toast.dismiss(id);
}
