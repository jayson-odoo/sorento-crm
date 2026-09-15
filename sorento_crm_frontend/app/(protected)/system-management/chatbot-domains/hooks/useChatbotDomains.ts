'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import {
  DELETE_WINDOW_SECONDS,
  cancelChatbotDomainDelete,
  createChatbotDomain,
  listChatbotDomains,
  parkChatbotDomainDelete,
  updateChatbotDomain,
} from '../services/chatbotDomainService';
import type { ChatbotDomainInput } from '../types/chatbotDomain.types';

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
 * Deferred delete (D7), mocked - see the service file header for what changes in S5.
 * The countdown is the SAME `DeferredCountdown` presentational component and the SAME
 * toast surface (`deferredToast`) every real deferred-delete list uses; only the park
 * / cancel / commit underneath is a client-side simulation.
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

  const cancel = useCallback(
    (id: string) => {
      settle();
      cancelChatbotDomainDelete(id).then(() => toast.success('Delete cancelled'));
    },
    [settle],
  );

  const run = useCallback(
    (row: { id: string; subject: string }) => {
      setPendingId(row.id);
      parkChatbotDomainDelete(row.id).then((action) => {
        toastIdRef.current = deferredToast({
          pending: action,
          verb: 'Deleting',
          subject: row.subject,
          onCancel: () => cancel(row.id),
        });
        lapseTimer.current = setTimeout(() => {
          toastIdRef.current = null;
          setPendingId(null);
          queryClient.invalidateQueries({ queryKey: CHATBOT_DOMAINS_QUERY_KEY });
          toast.success('Domain deleted');
        }, DELETE_WINDOW_SECONDS * 1000 + 200);
      });
    },
    [cancel, queryClient],
  );

  const isRowPending = useCallback((id: string) => pendingId === id, [pendingId]);

  return { run, isRowPending };
}
