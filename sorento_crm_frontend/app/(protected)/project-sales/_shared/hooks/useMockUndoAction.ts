'use client';

/**
 * PHASE 1 MOCK (S0, #977) for the three pending-action calls `fulfilment_planning.undo_confirm`
 * will use once S2 (#979) registers it as a `FormAction` (`WINDOW_REVERSIBLE`,
 * `projects.projects.edit`):
 *   POST /api/v1/pending-actions
 *     { action_key: 'fulfilment_planning.undo_confirm', entity_type: 'project_sales_order',
 *       entity_id, payload: { decision_id } } -> 202 { id, commit_at, window_seconds }
 *   POST /api/v1/pending-actions/{id}/cancel -> 200 before commit_at, 409 after
 *   GET /api/v1/pending-actions/current?entity_type=project_sales_order&entity_id=...
 *     -> { pending, last_outcome }
 *
 * None of that exists on the server yet - the action key is unregistered - so this hook times
 * a countdown LOCALLY instead of calling `services/pendingActionService.ts`, using the same
 * reversible window System Settings will drive for real. It holds exactly one target at a
 * time, which is all the gear can start (a disabled entry cannot be selected, and only one
 * countdown occupies the Confirm slot).
 *
 * Delete this file once S2 lands; `FulfilmentBoardPanel.tsx` then calls `useDeferredAction`
 * directly for `fulfilment_planning.undo_confirm`, exactly like every other pending action in
 * the product (see `hooks/useDeferredAction.tsx`).
 */

import * as React from 'react';
import { toast } from '@/lib/toast';
import type { PendingAction } from '@/services/pendingActionService';

/** System Settings' own reversible-window default, which the real action will read. */
const MOCK_WINDOW_SECONDS = 5;

export interface MockUndoTarget {
  /** The order's `project_sales_order_id` - what the real action's `entity_id` will be. */
  orderId: string;
  soNumber: string;
  revisionNo: number;
}

export interface UseMockUndoActionResult {
  /** The parked mock action, or null when nothing is counting down. */
  pending: PendingAction | null;
  /** Which order `pending` belongs to, for the countdown's subject line. */
  target: MockUndoTarget | null;
  /** Orders whose mocked countdown has already lapsed - the mock's stand-in for a real undo. */
  committedOrderIds: ReadonlySet<string>;
  start: (target: MockUndoTarget) => void;
  cancel: () => void;
}

export function useMockUndoAction(): UseMockUndoActionResult {
  const [target, setTarget] = React.useState<MockUndoTarget | null>(null);
  const [pending, setPending] = React.useState<PendingAction | null>(null);
  const [committedOrderIds, setCommittedOrderIds] = React.useState<ReadonlySet<string>>(
    () => new Set<string>(),
  );
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = React.useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // One countdown at a time (mock only): the real action would let a second order start its
  // own, but the Confirm slot has room for one, and nothing here needs the general case.
  const start = React.useCallback(
    (next: MockUndoTarget) => {
      if (pending) return;
      clearTimer();
      const commitAt = new Date(Date.now() + MOCK_WINDOW_SECONDS * 1000).toISOString();
      setTarget(next);
      setPending({
        id: `mock-undo-${next.orderId}`,
        action_key: 'fulfilment_planning.undo_confirm',
        entity_type: 'project_sales_order',
        entity_id: next.orderId,
        commit_at: commitAt,
        window_seconds: MOCK_WINDOW_SECONDS,
      });
      timerRef.current = setTimeout(() => {
        setPending(null);
        setCommittedOrderIds((current) => {
          const withCommitted = new Set(current);
          withCommitted.add(next.orderId);
          return withCommitted;
        });
        toast.success(`${next.soNumber} confirm undone`);
      }, MOCK_WINDOW_SECONDS * 1000);
    },
    [pending, clearTimer],
  );

  const cancel = React.useCallback(() => {
    clearTimer();
    setPending(null);
    setTarget(null);
    toast.success('Cancelled. Nothing was applied.');
  }, [clearTimer]);

  React.useEffect(() => clearTimer, [clearTimer]);

  return { pending, target, committedOrderIds, start, cancel };
}
