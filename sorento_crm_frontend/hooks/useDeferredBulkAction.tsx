'use client';

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import { pendingEntityStore } from '@/lib/pending-entity-store';
import {
  cancelPendingAction,
  createPendingAction,
  type PendingAction,
} from '@/services/pendingActionService';

/**
 * The grace window for a SELECTION of rows (D7, S6-07).
 *
 * Bulk delete was the last dialog left on a list, and the argument for keeping it -
 * that a selection has no single record to name, dim or cancel - turned out to be an
 * argument about the toast, not about the model. The server holds one pending action
 * per record either way, so this parks one per selected row and puts ONE countdown over
 * them: "Deleting 12 products in 10s", one Cancel that withdraws all twelve, and every
 * selected row dimmed by the same `rowPending` a single delete uses.
 *
 * No new route. The loop is a list page's worth of requests (100 rows at most) and they
 * go out together; a batch endpoint would be a second way to park an action, with its
 * own permission check and its own idempotency, for a saving of a few hundred
 * milliseconds inside a ten-second window.
 *
 * The follow-through is the store's, exactly as it is for one row: each action is
 * tracked, so navigating away still refetches the lists and un-dims the rows when the
 * windows lapse. What is different is the accounting - the store is told to say nothing
 * per row (`successMessage: null`) and to report back instead, so the reader is owed one
 * closing sentence rather than twelve.
 */

export interface DeferredBulkTarget {
  id: string;
  /** Whatever the handler needs at commit time beyond the id. */
  payload?: Record<string, unknown>;
  /**
   * Overrides the hook's `actionKey` for this one target. A selection can mix
   * two entity kinds behind ONE countdown - e.g. `Set company` running
   * `attachment.set_company` on the files it touches and
   * `attachment_directory.set_company` on the folders, both parked by the same
   * `run()` call. Omitted, the target uses the hook's own `actionKey`.
   */
  actionKey?: string;
  /** Overrides the hook's `entityType` for this one target, same reasoning. */
  entityType?: string;
}

export interface UseDeferredBulkActionInput {
  /** `<entity>.<verb>`, e.g. `product.delete`. Default for a target with no override. */
  actionKey: string;
  /** The registry's entity type, e.g. `product`. Default for a target with no override. */
  entityType: string;
  /** Verb-first copy for the countdown: "Deleting" reads as "Deleting in 8s". */
  verb?: string;
  /** Past tense, for the closing sentence: "12 products deleted". */
  pastVerb?: string;
  /** The selection in the reader's words: `(12) => '12 products'`. */
  describe: (count: number) => string;
  /** Lists to refetch once the actions have committed. */
  invalidateKeys?: readonly (readonly unknown[])[];
  /** Called once the batch is parked - where a list drops its selection. */
  onStarted?: () => void;
  /**
   * Overrides the three closing sentences instead of the default
   * "`${describe(count)} ${pastVerb}.`" template - for copy that reads
   * verb-first ("Company set: 3 folders, 12 files") rather than noun-first
   * ("12 products deleted.").
   */
  finishText?: {
    allCommitted: (count: number) => string;
    allFailed: (count: number) => string;
    partial: (committed: number, failed: number) => string;
  };
}

export interface UseDeferredBulkActionResult {
  /** Park one action per selected row, behind one countdown. */
  run: (targets: DeferredBulkTarget[]) => void;
  /** True from the click until every action is parked (or refused). */
  isStarting: boolean;
}

export function useDeferredBulkAction(
  input: UseDeferredBulkActionInput,
): UseDeferredBulkActionResult {
  const {
    actionKey,
    entityType,
    verb = 'Deleting',
    pastVerb = 'deleted',
    describe,
    invalidateKeys,
    onStarted,
    finishText,
  } = input;

  const queryClient = useQueryClient();
  const [isStarting, setIsStarting] = useState(false);
  //: One batch at a time, and each batch owns a toast id of its own.
  const batchRef = useRef(0);

  const run = useCallback(
    (targets: DeferredBulkTarget[]) => {
      if (targets.length === 0 || isStarting) return;
      setIsStarting(true);
      batchRef.current += 1;
      const toastId = `pending-bulk-${entityType}-${batchRef.current}`;

      void (async () => {
        const results = await Promise.allSettled(
          targets.map((target) =>
            createPendingAction({
              actionKey: target.actionKey ?? actionKey,
              entityType: target.entityType ?? entityType,
              entityId: target.id,
              payload: target.payload,
            }),
          ),
        );
        setIsStarting(false);

        const parked: PendingAction[] = [];
        // A record already counting down its own action is REFUSED (409), and so is one
        // the reader may not touch. Skipped, counted, and named at the end - never
        // swallowed, because the row stays on the list looking untouched.
        let refused = 0;
        for (const result of results) {
          if (result.status === 'fulfilled') parked.push(result.value);
          else refused += 1;
        }

        if (parked.length === 0) {
          toast.error(`Nothing could be ${pastVerb}. ${describe(refused)} refused.`);
          return;
        }
        onStarted?.();

        // The countdown runs to the LAST window to close, so it never reaches zero
        // while an action is still parked.
        const clock = parked.reduce((latest, action) =>
          action.commit_at > latest.commit_at ? action : latest,
        );

        let committed = 0;
        let failed = refused;
        let outstanding = parked.length;
        let withdrawn = false;

        const finish = () => {
          dismissDeferredToast(toastId);
          if (finishText) {
            if (failed === 0) toast.success(finishText.allCommitted(committed));
            else if (committed === 0) toast.error(finishText.allFailed(failed));
            else toast.error(finishText.partial(committed, failed));
            return;
          }
          if (failed === 0) {
            toast.success(`${describe(committed)} ${pastVerb}.`);
          } else if (committed === 0) {
            toast.error(`${describe(failed)} could not be ${pastVerb}.`);
          } else {
            toast.error(
              `${describe(committed)} ${pastVerb}; ${failed} could not be.`,
            );
          }
        };

        for (const action of parked) {
          pendingEntityStore.track({
            id: action.id,
            // The parked action echoes back whichever entityType/actionKey it
            // was created with, per-target override included, so a mixed
            // batch dims the right kind of row for each id.
            entityType: action.entity_type,
            entityId: action.entity_id,
            actionKey: action.action_key,
            commitAt: action.commit_at,
            // The batch says one thing at the end; a row saying its own would be
            // twelve toasts for one gesture.
            successMessage: null,
            invalidateKeys: invalidateKeys ?? [],
            onSettled: (outcome) => {
              if (withdrawn) return;
              if (outcome?.status === 'committed') committed += 1;
              else failed += 1;
              outstanding -= 1;
              if (outstanding === 0) finish();
            },
          });
        }

        const cancelAll = async () => {
          if (withdrawn) return;
          withdrawn = true;
          dismissDeferredToast(toastId);
          const cancels = await Promise.allSettled(
            parked.map((action) => cancelPendingAction(action.id)),
          );
          for (const action of parked) pendingEntityStore.releaseById(action.id);
          // A cancel that arrives after its window closed loses to the commit (409), so
          // "cancelled" is not always the whole truth and the reader has to be told
          // which rows went anyway.
          const late = cancels.filter((c) => c.status === 'rejected').length;
          if (late === 0) {
            toast.success('Cancelled. Nothing was applied.');
          } else {
            toast.error(
              `Cancelled, but ${describe(late)} had already been ${pastVerb}.`,
            );
            for (const queryKey of invalidateKeys ?? []) {
              queryClient.invalidateQueries({ queryKey });
            }
          }
        };

        deferredToast({
          pending: clock,
          verb,
          subject: describe(parked.length),
          onCancel: () => void cancelAll(),
          id: toastId,
        });
      })();
    },
    [
      actionKey,
      describe,
      entityType,
      finishText,
      invalidateKeys,
      isStarting,
      onStarted,
      queryClient,
      pastVerb,
      verb,
    ],
  );

  return { run, isStarting };
}

export default useDeferredBulkAction;
