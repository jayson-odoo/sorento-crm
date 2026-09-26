'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getContactChatbotMemory,
  getContactChatbotProfile,
  saveContactChatbotProfile,
  saveContactFact,
  type ContactChatbotSaveInput,
} from '../services/contactChatbotService';

export const contactChatbotQueryKey = (contactId: string) => ['contact-chatbot', contactId];
export const contactChatbotMemoryQueryKey = (contactId: string) => [
  'contact-chatbot-memory',
  contactId,
];

export function useContactChatbotProfile(contactId: string) {
  return useQuery({
    queryKey: contactChatbotQueryKey(contactId),
    queryFn: () => getContactChatbotProfile(contactId),
    enabled: !!contactId,
    retry: 1,
  });
}

export function useSaveContactChatbotProfile(contactId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactChatbotSaveInput) => saveContactChatbotProfile(contactId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contactChatbotQueryKey(contactId) });
      // The memory context level is the same underlying value the memory card
      // displays (own/system default) - a profile save has to refresh that read too.
      queryClient.invalidateQueries({ queryKey: contactChatbotMemoryQueryKey(contactId) });
      toast.success('Chatbot settings saved');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save'),
  });
}

/** "What the bot knows" / "Conversations" / "Open orders" (chatbot memory lane A). */
export function useContactChatbotMemory(contactId: string) {
  return useQuery({
    queryKey: contactChatbotMemoryQueryKey(contactId),
    queryFn: () => getContactChatbotMemory(contactId),
    enabled: !!contactId,
    retry: 1,
  });
}

export function useSaveContactFact(contactId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string | string[] }) =>
      saveContactFact(contactId, key, value),
    onSuccess: (memory) => {
      queryClient.setQueryData(contactChatbotMemoryQueryKey(contactId), memory);
      toast.success('Fact saved');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save'),
  });
}
