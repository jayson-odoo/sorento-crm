'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import {
  DELETE_WINDOW_SECONDS,
  createChatbotDomain,
  deleteChatbotDomain,
  listChatbotDomains,
  updateChatbotDomain,
} from '../services/chatbotDomainService';
import type { ChatbotDomainInput } from '../types/chatbotDomain.types';
import type { PendingAction } from '@/services/pendingActionService';

export const CHATBOT_DOMAINS_QUERY_KEY = ['chatbot-domains'];

export function useChatbotDomainsQuery() {
  return useQuery({ queryKey: CHATBOT_DOMAINS_QUERY_KEY, queryFn: listChatbotDomains });
}

export function useCreateChatbotDomain() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChatbotDomainInput) => createChatbotDomain(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_DOMAINS_QUERY_KEY });
      toast.success('Domain created');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to create domain');
    },
  });
}

export function useUpdateChatbotDomain() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: ChatbotDomainInput }) =>
      updateChatbotDomain(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_DOMAINS_QUERY_KEY });
      toast.success('Domain saved');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to save domain');
    },
  });
}

/**
 * Deferred delete (D7). The DELETE route is an immediate hard delete on the server (no
 * pending-action row for this table yet, AC-1561) - the countdown below is a CLIENT-ONLY
 * grace window with Cancel, same as S1: `run()` starts the toast countdown, and only
 * calls the real DELETE once the window lapses uncancelled. Same `DeferredCountdown`
 * presentational component and the same `deferredToast` surface every real
 * server-deferred list uses; only the park/cancel/commit underneath never leaves the tab
 * until the window lapses.
 */
export function useChatbotDomainDeletion() {
  const queryClient = useQueryClient();
  const toastIdRef = useRef<string | number | null>(null);
  const lapseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const settle = useCallback(() => {
    if (lapseTimer.current) clearTimeout(lapseTimer.current);
    lapseTimer.current = null;
    if (toastIdRef.current !== null) dismissDeferredToast(toastIdRef.current);
    toastIdRef.current = null;
    setPendingId(null);
  }, []);

  useEffect(() => () => settle(), [settle]);

  const cancel = useCallback(() => {
    settle();
    toast.success('Delete cancelled');
  }, [settle]);

  const run = useCallback(
    (row: { id: string; subject: string }) => {
      setPendingId(row.id);
      const commitAt = new Date(Date.now() + DELETE_WINDOW_SECONDS * 1000).toISOString();
      const pending: PendingAction = {
        id: `chatbot_domain.delete:${row.id}`,
        action_key: 'chatbot_domain.delete',
        entity_type: 'chatbot_domain',
        entity_id: row.id,
        commit_at: commitAt,
        window_seconds: DELETE_WINDOW_SECONDS,
      };
      toastIdRef.current = deferredToast({
        pending,
        verb: 'Deleting',
        subject: row.subject,
        onCancel: cancel,
      });
      lapseTimer.current = setTimeout(() => {
        toastIdRef.current = null;
        setPendingId(null);
        deleteChatbotDomain(row.id)
          .then(() => {
            queryClient.invalidateQueries({ queryKey: CHATBOT_DOMAINS_QUERY_KEY });
            toast.success('Domain deleted');
          })
          .catch((error: unknown) => {
            toast.error(error instanceof Error ? error.message : 'Failed to delete domain');
          });
      }, DELETE_WINDOW_SECONDS * 1000 + 200);
    },
    [cancel, queryClient],
  );

  const isRowPending = useCallback((id: string) => pendingId === id, [pendingId]);

  return { run, isRowPending };
}
