'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getContactChatbotProfile, saveContactChatbotProfile } from '../services/contactChatbotService';

export const contactChatbotQueryKey = (contactId: string) => ['contact-chatbot', contactId];

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
    mutationFn: (input: { recall_enabled: boolean; language: string | null }) =>
      saveContactChatbotProfile(contactId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contactChatbotQueryKey(contactId) });
      toast.success('Chatbot settings saved');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save'),
  });
}
