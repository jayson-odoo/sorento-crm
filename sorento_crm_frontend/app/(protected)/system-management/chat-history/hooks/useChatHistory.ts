'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { exportChatHistory, getChatThread } from '../services/chatHistoryService';
import type { ChatHistoryFilters } from '../types/chatHistory.types';

export const CHAT_HISTORY_KEY = ['chat-history'] as const;

/** A contact's full conversation, centred on `anchorId` when given. Also used by the
 *  per-contact section on the contact detail page (anchorId omitted). */
export function useChatThread(contactId: string | null, anchorId?: number) {
  return useQuery({
    queryKey: [...CHAT_HISTORY_KEY, 'thread', contactId, anchorId ?? null],
    queryFn: () => getChatThread(contactId as string, anchorId),
    enabled: Boolean(contactId),
    staleTime: 15_000,
  });
}

export function useExportChatHistory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (filters: ChatHistoryFilters) => exportChatHistory(filters),
    onSuccess: () => {
      // The row lands in My Downloads as 'pending'; that drawer polls itself.
      queryClient.invalidateQueries({ queryKey: ['my-downloads'] });
      toast.success('Preparing export - it will appear in My Downloads.');
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : 'Export failed'),
  });
}
