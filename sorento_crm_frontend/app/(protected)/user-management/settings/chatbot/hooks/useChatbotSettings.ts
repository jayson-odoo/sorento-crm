import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getChatbotSettings,
  saveChatbotSettings,
  type ChatbotSettings,
} from '../services/chatbotSettingsService';

export const CHATBOT_SETTINGS_KEY = ['chatbot-settings'];

export function useChatbotSettings() {
  return useQuery({
    queryKey: CHATBOT_SETTINGS_KEY,
    queryFn: getChatbotSettings,
    retry: 1,
  });
}

export function useSaveChatbotSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChatbotSettings) => saveChatbotSettings(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_SETTINGS_KEY });
      // These columns live on the singleton the settings layout caches, so the shared
      // row has to be refetched too or the two views disagree.
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast.success('Chatbot settings saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save settings'),
  });
}
