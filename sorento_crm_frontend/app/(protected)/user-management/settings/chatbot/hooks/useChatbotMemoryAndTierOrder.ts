'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getChatbotMemorySettings,
  getChatbotTierOrder,
  saveChatbotMemorySettings,
  saveChatbotTierOrder,
  type ChatbotMemorySettings,
} from '../services/chatbotSettingsService';

/**
 * Settings > Chatbot > Memory + Tier order cards (chatbot turn re-architecture, AC-1513,
 * AC-1561). Their own hook file, separate from `useChatbotSettings.ts` - that module is
 * wholesale-mocked by `page.test.tsx` (`vi.mock('./hooks/useChatbotSettings', () => ({
 * useChatbotSettings: ..., useSaveChatbotSettings: ... }))`, exactly the four
 * switch/domain keys), and a second export there would need that mock touched to keep
 * working. Both cards save independently of the Switches card's Save button - same
 * PUT /settings/general route, a partial body each.
 */

export const CHATBOT_MEMORY_KEY = ['chatbot-memory-settings'];
export const CHATBOT_TIER_ORDER_KEY = ['chatbot-tier-order'];

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
