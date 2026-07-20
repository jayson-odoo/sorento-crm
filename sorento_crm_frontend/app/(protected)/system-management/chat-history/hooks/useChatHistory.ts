'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  exportChatHistory,
  getChatMessages,
  getChatThread,
} from '../services/chatHistoryService';
import type { ChatHistoryFilters } from '../types/chatHistory.types';

export const CHAT_HISTORY_KEY = ['chat-history'] as const;

export function useChatMessages(
  filters: ChatHistoryFilters,
  opts: { limit?: number; cursor?: string | null } = {},
) {
  return useQuery({
    queryKey: [...CHAT_HISTORY_KEY, filters, opts.cursor ?? null, opts.limit ?? 50],
    queryFn: () => getChatMessages(filters, opts),
    // Keyset paging means the previous page stays valid while the next loads,
    // so holding it avoids a full-grid flash on every page step.
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });
}

export function useChatThread(contactId: string | null, anchorId?: number) {
  return useQuery({
    queryKey: [...CHAT_HISTORY_KEY, 'thread', contactId, anchorId ?? null],
    queryFn: () => getChatThread(contactId as string, anchorId),
    enabled: Boolean(contactId),
  });
}

export function useExportChatHistory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (filters: ChatHistoryFilters) => exportChatHistory(filters),
    onSuccess: () => {
      // The row lands in My Downloads as 'pending'; that drawer polls itself.
      queryClient.invalidateQueries({ queryKey: ['my-downloads'] });
      toast.success('Preparing export — it will appear in My Downloads.');
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : 'Export failed'),
  });
}
