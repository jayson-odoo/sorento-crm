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

  const hydrate = useCallback(async (): Promise<ImpersonationSession | null> => {
    const current = await fetchCurrentImpersonation();
    impersonationStore.setSession(current);
    return current;
  }, []);

  const startMutation = useMutation({
    mutationFn: (targetUserId: string) => startImpersonation(targetUserId),
    onSuccess: (s) => {
      impersonationStore.setSession(s);
    },
  });

  const stopMutation = useMutation({
    mutationFn: stopImpersonation,
    onSuccess: () => {
      impersonationStore.setSession(null);
    },
  });

  return {
    session,
    isImpersonating: !!session,
    hydrate,
    start: startMutation.mutateAsync,
    stop: stopMutation.mutateAsync,
    starting: startMutation.isPending,
    stopping: stopMutation.isPending,
  };
}
