'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getChatbotDefaultLadder,
  getChatbotMemorySettings,
  getChatbotTierOrder,
  saveChatbotDefaultLadder,
  saveChatbotMemorySettings,
  saveChatbotTierOrder,
  type ChatbotMemorySettings,
} from '../services/chatbotConfigMockService';

export const CHATBOT_MEMORY_KEY = ['chatbot-memory-settings'];
export const CHATBOT_TIER_ORDER_KEY = ['chatbot-tier-order'];
export const CHATBOT_DEFAULT_LADDER_KEY = ['chatbot-default-ladder'];

export function useChatbotMemorySettings() {
  return useQuery({ queryKey: CHATBOT_MEMORY_KEY, queryFn: getChatbotMemorySettings });
}

export function useSaveChatbotMemorySettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChatbotMemorySettings) => saveChatbotMemorySettings(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_MEMORY_KEY });
      toast.success('Memory settings saved');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save'),
  });
}

export function useChatbotTierOrder() {
  return useQuery({ queryKey: CHATBOT_TIER_ORDER_KEY, queryFn: getChatbotTierOrder });
}

export function useSaveChatbotTierOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (order: string[]) => saveChatbotTierOrder(order),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_TIER_ORDER_KEY });
      toast.success('Tier order saved');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save'),
  });
}

export function useChatbotDefaultLadder() {
  return useQuery({ queryKey: CHATBOT_DEFAULT_LADDER_KEY, queryFn: getChatbotDefaultLadder });
}

export function useSaveChatbotDefaultLadder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (order: string[]) => saveChatbotDefaultLadder(order),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_DEFAULT_LADDER_KEY });
      toast.success('Ladder saved');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save'),
  });
}
