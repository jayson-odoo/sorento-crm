import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getChatbotMediaSettings,
  saveChatbotMediaSettings,
  type ChatbotMediaSettings,
} from '../services/chatbotMediaSettingsService';

export const CHATBOT_MEDIA_SETTINGS_KEY = ['chatbot-media-settings'];

export function useChatbotMediaSettings() {
  return useQuery({
    queryKey: CHATBOT_MEDIA_SETTINGS_KEY,
    queryFn: getChatbotMediaSettings,
    retry: 1,
  });
}

export function useSaveChatbotMediaSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChatbotMediaSettings) => saveChatbotMediaSettings(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_MEDIA_SETTINGS_KEY });
      // These columns live on the same singleton the settings layout caches, so the
      // shared row has to be refetched too or the two views disagree.
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast.success('Chatbot media settings saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save settings'),
  });
}
