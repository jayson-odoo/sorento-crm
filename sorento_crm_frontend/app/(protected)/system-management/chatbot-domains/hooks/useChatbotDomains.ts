'use client';

import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  createChatbotDomain,
  listChatbotDomains,
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
 * Deferred delete (D7), server side. `chatbot_domain.delete` is a registered
 * `FormAction` (`app/services/record_actions.py`), so the countdown is parked on the
 * server: it commits when the window lapses even if the tab is closed, and Cancel
 * withdraws it. The S1 mock's client-only `setTimeout` is gone with it - that version
 * lost the delete entirely if the tab closed mid countdown.
 */
export function useChatbotDomainDeletion() {
  const deletion = useDeferredRowAction({
    actionKey: 'chatbot_domain.delete',
    entityType: 'chatbot_domain',
    successMessage: 'Domain deleted',
    invalidateKeys: [CHATBOT_DOMAINS_QUERY_KEY],
  });
  const isRowPending = useCallback(
    (id: string) => deletion.targetId === id,
    [deletion.targetId],
  );
  return { run: deletion.run, isRowPending };
}
