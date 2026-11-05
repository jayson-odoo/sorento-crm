"use client";

import { useMutation } from '@tanstack/react-query';
import { useCallback } from 'react';

import {
  impersonationStore,
  useImpersonationSession,
  type ImpersonationSession,
} from '@/lib/impersonation-store';
import {
  fetchCurrentImpersonation,
  startImpersonation,
  stopImpersonation,
} from '@/services/impersonationService';

export function useImpersonation() {
  const session = useImpersonationSession();

  // Checks THIS tab's view-as against the server; never adopts the server's open row into a tab
  // that did not start it (PORTAL-IMPERSONATION-ISOLATE). Every other tab and browser of the
  // admin stays the admin.
  const hydrate = useCallback(async (): Promise<ImpersonationSession | null> => {
    const mine = impersonationStore.getState();
    if (!mine) return null;
    const current = await fetchCurrentImpersonation();
    // Matched on the session, not the target: a view-as of the same person started again
    // elsewhere is not this tab's.
    const stillOpen = current && current.sessionId === mine.sessionId ? current : null;
    // Only act if the tab still holds what we checked (a stop or a new start may have raced us).
    if (impersonationStore.getState() === mine) impersonationStore.setSession(stillOpen);
    return stillOpen;
  }, []);

  const startMutation = useMutation({
    mutationFn: (targetUserId: string) => startImpersonation(targetUserId),
    onSuccess: (s) => {
      impersonationStore.setSession(s);
    },
  });

  const stopMutation = useMutation({
    mutationFn: (sessionId: string | undefined) => stopImpersonation(sessionId),
    // Clear before the call, not after: a query answered between the server ending
    // the row and onSuccess would carry X-Impersonation-Ended while the target still
    // matched, and show "View-as ended" for a stop the user just asked for.
    onMutate: () => {
      const previous = impersonationStore.getState();
      impersonationStore.setSession(null);
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) impersonationStore.setSession(context.previous);
    },
  });

  return {
    session,
    isImpersonating: !!session,
    hydrate,
    start: startMutation.mutateAsync,
    // Names this tab's view-as, read before onMutate clears it.
    stop: () => stopMutation.mutateAsync(impersonationStore.getState()?.sessionId),
    starting: startMutation.isPending,
    stopping: stopMutation.isPending,
  };
}
