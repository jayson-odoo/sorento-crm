'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createChatbotEntityKind,
  listChatbotEntityKinds,
  updateChatbotEntityKind,
} from '../services/chatbotEntityKindService';
import type { ChatbotEntityKindInput } from '../types/chatbotEntityKind.types';

export const CHATBOT_ENTITY_KINDS_QUERY_KEY = ['chatbot-entity-kinds'];

export function useChatbotEntityKindsQuery() {
  return useQuery({
    queryKey: CHATBOT_ENTITY_KINDS_QUERY_KEY,
    queryFn: listChatbotEntityKinds,
  });
}

export function useCreateChatbotEntityKind() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChatbotEntityKindInput) => createChatbotEntityKind(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_ENTITY_KINDS_QUERY_KEY });
      toast.success('Entity kind created');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to create entity kind');
    },
  });
}

export function useUpdateChatbotEntityKind() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ code, input }: { code: string; input: ChatbotEntityKindInput }) =>
      updateChatbotEntityKind(code, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_ENTITY_KINDS_QUERY_KEY });
      toast.success('Entity kind saved');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to save entity kind');
    },
  });
}
