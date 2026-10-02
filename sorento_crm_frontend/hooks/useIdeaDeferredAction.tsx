'use client';

import { useCallback, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import { IDEAS_KEY } from '@/hooks/useIdeas';
import type { PendingAction } from '@/services/pendingActionService';

/**
 * PHASE 1 stand-in for `useDeferredAction` (hooks/useDeferredAction.tsx) on the Ideas pages.
 *
 * The real hook parks the action on the server (`POST /api/v1/pending-actions`) and learns the
 * commit by polling; this one simulates the same grace window in the browser so the countdown,
 * its Cancel and the commit can be hand-tested against the mock service. The timer is
 * deliberately NOT cleared on unmount, because the real server commits whether or not the tab is
 * still open. Phase 2 deletes this file and the callers switch to `useDeferredAction` with
 * `entityType: 'idea' | 'idea_comment'`; the returned shape is the same subset they use.
 */
export const HARD_DELETE_WINDOW_SECONDS = 10;
export const REVERSIBLE_WINDOW_SECONDS = 5;

export interface UseIdeaDeferredActionInput {
  /** Verb-first copy: "Deleting" reads as "Deleting in 8s". */
  verb: string;
  subject: string;
  windowSeconds: number;
  surface: 'inline' | 'toast';
  successMessage: string;
  /** What the server would do at the end of the window. */
  run: () => Promise<unknown>;
  onCommitted?: () => void;
}

export function useIdeaDeferredAction(input: UseIdeaDeferredActionInput) {
  const { verb, subject, windowSeconds, surface, successMessage } = input;
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastId = useRef<string | number | null>(null);
  // The commit fires from a timer that outlives renders, so it reads the latest callbacks here.
  const latest = useRef(input);
  latest.current = input;

  const clear = useCallback(() => {
    if (toastId.current != null) dismissDeferredToast(toastId.current);
    toastId.current = null;
    timer.current = null;
    setPending(null);
  }, []);

  const cancel = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    clear();
    toast.success('Cancelled. Nothing was applied.');
  }, [clear]);

  const start = useCallback(() => {
    if (timer.current) return;
    const action: PendingAction = {
      id: `mock-${Date.now()}`,
      action_key: 'idea.mock',
      entity_type: 'idea',
      entity_id: '',
      commit_at: new Date(Date.now() + windowSeconds * 1000).toISOString(),
      window_seconds: windowSeconds,
    };
    setPending(action);
    if (surface === 'toast') {
      toastId.current = deferredToast({ pending: action, verb, subject, onCancel: cancel });
    }
    timer.current = setTimeout(async () => {
      try {
        await latest.current.run();
        queryClient.invalidateQueries({ queryKey: IDEAS_KEY });
        toast.success(successMessage);
        latest.current.onCommitted?.();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Something went wrong');
      } finally {
        clear();
      }
    }, windowSeconds * 1000);
  }, [cancel, clear, queryClient, subject, successMessage, surface, verb, windowSeconds]);

  const countdown: ReactNode =
    surface === 'inline' && pending ? (
      <DeferredCountdown pending={pending} verb={verb} onCancel={cancel} />
    ) : null;

  return { pending, isPending: !!pending, start, cancel, countdown };
}
