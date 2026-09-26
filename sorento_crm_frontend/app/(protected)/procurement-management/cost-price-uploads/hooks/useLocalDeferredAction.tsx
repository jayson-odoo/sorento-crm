'use client';

/**
 * A client-only stand-in for `hooks/useDeferredAction.tsx`, for the two Phase 1 destructive
 * actions this lane's mock has no backend for yet: `cost_price_change_set.discard` and
 * `product_supplier_cost.delete`. The real hook posts to `/api/v1/pending-actions`, which
 * requires the action key to be registered in `app/services/record_actions.py` - that
 * registration is Phase 2 work, so posting there today would 400 at the click instead of
 * counting down.
 *
 * Same shape as `useDeferredAction`'s result (`pending`, `isPending`, `start`, `cancel`,
 * `countdown`, rendered with the same `DeferredCountdown`), so Phase 2 swaps this import for
 * the real hook with no change to the calling component. The window and the commit both run
 * in the browser only - there is no server to keep counting if the tab closes, which is the
 * one behaviour this stand-in does NOT reproduce (see PRINCIPLES.md "server, never a browser
 * being open"); acceptable for a Phase 1 mock, called out in the lane's report.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from '@/lib/toast';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import type { PendingAction } from '@/services/pendingActionService';

export interface UseLocalDeferredActionInput {
  entityType: string;
  entityId: string | null | undefined;
  verb: string;
  subject: string;
  windowSeconds?: number;
  successMessage: string;
  onCommit: () => Promise<void>;
}

export function useLocalDeferredAction(input: UseLocalDeferredActionInput) {
  const { entityType, entityId, verb, subject, windowSeconds = 10, successMessage, onCommit } = input;
  const [pending, setPending] = useState<PendingAction | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const start = useCallback(() => {
    if (!entityId || pending) return;
    cancelledRef.current = false;
    const commitAt = new Date(Date.now() + windowSeconds * 1000).toISOString().slice(0, 19);
    setPending({
      id: `local-${entityType}-${entityId}`,
      action_key: `${entityType}.pending`,
      entity_type: entityType,
      entity_id: entityId,
      commit_at: commitAt,
      window_seconds: windowSeconds,
    });
    timerRef.current = setTimeout(() => {
      if (cancelledRef.current) return;
      void onCommit()
        .then(() => toast.success(successMessage))
        .catch((error: Error) => toast.error(error.message))
        .finally(() => setPending(null));
    }, windowSeconds * 1000);
  }, [entityId, entityType, onCommit, pending, successMessage, windowSeconds]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    if (timerRef.current) clearTimeout(timerRef.current);
    setPending(null);
    toast.success('Cancelled. Nothing was applied.');
  }, []);

  return {
    pending,
    isPending: !!pending,
    start,
    cancel,
    countdown: pending ? (
      <DeferredCountdown pending={pending} verb={verb} subject={subject} onCancel={cancel} />
    ) : null,
  };
}
