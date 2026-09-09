'use client';

import { useCallback, useRef, useState } from 'react';
import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import type { PendingAction } from '@/services/pendingActionService';

/**
 * A Phase-1-only stand-in for `useDeferredRowAction` (D7, S6), for a feature whose own
 * `action_key` is not registered in the real pending-action handler registry yet
 * (`app.services.record_actions`) - registering one is backend code, out of scope while a
 * lane is still Phase 1 mocked. This reuses the SAME `DeferredCountdown` component and
 * the SAME window shape (`PendingAction`) so the countdown reads identically on screen
 * (AC-F2: the preset is untouched, only where the timer lives differs), entirely
 * client-side: `apply()` runs at once, `cancel()` runs `undo()` if the window has not
 * lapsed, and nothing calls the server. Swapped for the real `useDeferredRowAction` in
 * Phase 2 once the action key is registered - every call site already matches its shape.
 */
export function useMockDeferredWindow(windowSeconds = 5) {
  const [pending, setPending] = useState<PendingAction | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const undoRef = useRef<(() => void) | null>(null);
  const toastIdRef = useRef<string | number | null>(null);

  const clear = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    undoRef.current = null;
    if (toastIdRef.current != null) dismissDeferredToast(toastIdRef.current);
    toastIdRef.current = null;
    setPending(null);
  }, []);

  /**
   * Applies `apply()` now, and arms a window in which `cancel()` runs `undo()` instead.
   * `toast` (verb + subject) raises the SAME toast a list row's deferred delete does
   * (`deferredToast`) - for a control with nowhere of its own to put a countdown, a
   * grid chip among them. Omitted, the caller renders its own inline countdown from
   * `pending`.
   */
  const run = useCallback(
    (input: {
      id: string;
      entityType: string;
      apply: () => void;
      undo: () => void;
      toast?: { verb: string; subject: string };
    }) => {
      clear();
      input.apply();
      undoRef.current = input.undo;
      const commitAt = new Date(Date.now() + windowSeconds * 1000).toISOString();
      const action: PendingAction = {
        id: input.id,
        action_key: `${input.entityType}.mock`,
        entity_type: input.entityType,
        entity_id: input.id,
        commit_at: commitAt,
        window_seconds: windowSeconds,
      };
      setPending(action);
      if (input.toast) {
        toastIdRef.current = deferredToast({
          pending: action,
          verb: input.toast.verb,
          subject: input.toast.subject,
          onCancel: () => cancel(),
        });
      }
      timerRef.current = setTimeout(clear, windowSeconds * 1000);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clear, windowSeconds],
  );

  const cancel = useCallback(() => {
    undoRef.current?.();
    clear();
  }, [clear]);

  return { pending, run, cancel };
}
