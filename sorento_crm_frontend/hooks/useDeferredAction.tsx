'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import { pendingEntityStore } from '@/lib/pending-entity-store';
import {
  cancelPendingAction,
  createPendingAction,
  getCurrentPendingAction,
  type PendingAction,
} from '@/services/pendingActionService';

/**
 * The grace window, from the caller's side (D7, S6).
 *
 * Nothing here asks the user to confirm. `start()` parks the action on the server
 * and a countdown appears - in place, where the button was, or in a toast when the
 * action came from a list row - and the server applies it when the window lapses.
 * Cancel withdraws it while the window is open; after that the answer is the
 * server's.
 *
 * The clock is `commit_at` from the server, so a refresh does not restart it, and
 * the commit is learned by re-reading `current` rather than by trusting a local
 * timer: only the server knows whether the handler actually ran (S6-03).
 */

export interface UseDeferredActionInput {
  /** `<entity>.<verb>`, e.g. `product.delete`. The window follows the verb (S6-04). */
  actionKey: string;
  /** The registry's entity type, e.g. `product`. */
  entityType: string;
  entityId: string | null | undefined;
  /** Verb-first copy for the countdown: "Deleting" reads as "Deleting in 8s". */
  verb: string;
  /** What is being acted on, in the reader's words ("Ergonomic Chair"). */
  subject: string;
  /**
   * Where the countdown goes: `inline` hands it back as `countdown` for the caller
   * to render where the button was (a record's primary area, S6-06); `toast` puts
   * it over the list, because a row has nowhere to put it (S6-07).
   */
  surface: 'inline' | 'toast';
  /**
   * Read `current` from mount, not just after a click. A record page does, so a
   * countdown started in another tab - or by the same record's danger zone - shows
   * here too (S6-05). A list row does not: fifty rows polling for a countdown
   * nobody started is fifty requests for one click.
   */
  watchFromMount?: boolean;
  /** Said once the server has applied it. */
  successMessage: string;
  /** What the handler needs at commit time. `start()` may override it per click. */
  payload?: Record<string, unknown>;
  /** Lists to refetch once the action has committed. */
  invalidateKeys?: readonly unknown[][];
  /** Where to go afterwards - a record page cannot stay open on a deleted row. */
  onCommitted?: () => void;
  /**
   * PHASE 1 ONLY: applies the effect when the mocked window lapses (the very
   * delete the confirmation dialog used to run). Phase 2 registers the handler on
   * the server and deletes this argument at every call site.
   */
  commit?: (payload: Record<string, unknown>) => Promise<unknown>;
}

export interface UseDeferredActionResult {
  pending: PendingAction | null;
  /** True from the click until the server settles the action. */
  isPending: boolean;
  /**
   * Something ELSE is already counting down on this record. One record holds one
   * pending action, so an item that would start a second has to wait its turn
   * rather than fail on the way out.
   */
  isBlocked: boolean;
  start: (payload?: Record<string, unknown>) => void;
  cancel: () => void;
  /**
   * The countdown to render where the button was. Null while nothing is parked,
   * and null on the `toast` surface, where the toast carries it instead.
   */
  countdown: ReactNode;
}

export function useDeferredAction(
  input: UseDeferredActionInput,
): UseDeferredActionResult {
  const {
    actionKey,
    entityType,
    entityId,
    verb,
    subject,
    surface,
    watchFromMount = false,
    successMessage,
    payload,
    invalidateKeys,
    onCommitted,
    commit,
  } = input;

  const queryClient = useQueryClient();
  const queryKey = ['pending-action-current', entityType, entityId];

  const [watching, setWatching] = useState(watchFromMount);

  const { data } = useQuery({
    queryKey,
    queryFn: () => getCurrentPendingAction(entityType, entityId as string),
    enabled: watching && !!entityId,
    // Only while something is parked, and often enough that a 5s window does not
    // spend a fifth of itself looking finished.
    refetchInterval: (query) => (query.state.data?.pending ? 500 : false),
  });

  // `current` answers for the RECORD, so a page holding two deferred actions -
  // Delete and Mark as delivered - would otherwise have both of them counting
  // down the other one's window, under the wrong verb.
  const parked = data?.pending ?? null;
  const pending = parked?.action_key === actionKey ? parked : null;
  const toastIdRef = useRef<string | number | null>(null);
  const lastPendingIdRef = useRef<string | null>(null);
  /** Only the surface that STARTED the action reports how it ended. */
  const startedIdRef = useRef<string | null>(null);

  const cancelMutation = useMutation({
    mutationFn: (id: string) => cancelPendingAction(id),
    onSuccess: () => {
      startedIdRef.current = null;
      toast.success('Cancelled. Nothing was applied.');
      queryClient.invalidateQueries({ queryKey });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const startMutation = useMutation({
    mutationFn: (override?: Record<string, unknown>) =>
      createPendingAction({
        actionKey,
        entityType,
        entityId: entityId as string,
        payload: override ?? payload,
        commit: commit && ((): Promise<unknown> => commit(override ?? payload ?? {})),
      }),
    onSuccess: (action) => {
      startedIdRef.current = action.id;
      setWatching(true);
      // The countdown is on screen before the next read comes back: the window is
      // ten seconds, and a second of "nothing happened" is where a second click
      // comes from.
      queryClient.setQueryData(queryKey, { pending: action, last_outcome: null });
      pendingEntityStore.mark(entityType, action.entity_id);
      if (surface === 'toast') {
        toastIdRef.current = deferredToast({
          pending: action,
          verb,
          subject,
          onCancel: () => cancelMutation.mutate(action.id),
        });
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /** Take back what the action put on screen. */
  const clearAffordances = useCallback(() => {
    if (entityId) pendingEntityStore.clear(entityType, entityId);
    if (toastIdRef.current !== null) {
      dismissDeferredToast(toastIdRef.current);
      toastIdRef.current = null;
    }
  }, [entityId, entityType]);

  // The window closes on the SERVER. The first the client hears of it is `pending`
  // going null on the next read, and what happened next is in `last_outcome`: a
  // handler that failed left the record alone and has to say so, because a
  // countdown that simply disappears reads exactly like success (S6-03).
  useEffect(() => {
    const currentId = pending?.id ?? null;
    const previousId = lastPendingIdRef.current;
    lastPendingIdRef.current = currentId;
    if (!previousId || currentId) return;

    clearAffordances();
    if (!watchFromMount) setWatching(false);

    const outcome = data?.last_outcome;
    if (!outcome || outcome.id !== previousId) return;
    if (startedIdRef.current !== previousId) return;
    startedIdRef.current = null;

    if (outcome.status === 'committed') {
      toast.success(successMessage);
      for (const key of invalidateKeys ?? []) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      onCommitted?.();
    } else if (outcome.status === 'failed') {
      toast.error(outcome.error_text || 'The action could not be applied.');
    }
  }, [
    pending,
    data,
    watchFromMount,
    successMessage,
    invalidateKeys,
    onCommitted,
    queryClient,
    clearAffordances,
  ]);

  // A row that scrolls out of the grid, or a record page left mid-window, must not
  // leave a dimmed row and a live toast behind. The action itself is the server's
  // and carries on regardless - which is the whole point of the model (S6-08).
  useEffect(() => () => clearAffordances(), [clearAffordances]);

  const start = useCallback(
    (override?: Record<string, unknown>) => {
      if (!entityId || parked || startMutation.isPending) return;
      startMutation.mutate(override);
    },
    [entityId, parked, startMutation],
  );

  const cancel = useCallback(() => {
    if (pending) cancelMutation.mutate(pending.id);
  }, [pending, cancelMutation]);

  return {
    pending,
    isPending: !!pending || startMutation.isPending,
    isBlocked: !!parked && !pending,
    start,
    cancel,
    countdown:
      surface === 'inline' && pending ? (
        <DeferredCountdown
          pending={pending}
          verb={verb}
          onCancel={cancel}
          cancelling={cancelMutation.isPending}
        />
      ) : null,
  };
}

export default useDeferredAction;
