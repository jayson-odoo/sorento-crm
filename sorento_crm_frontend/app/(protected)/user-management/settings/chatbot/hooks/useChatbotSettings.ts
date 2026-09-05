import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getChatbotLanes,
  getChatbotSettings,
  saveChatbotSettings,
  type ChatbotSettings,
} from '../services/chatbotSettingsService';

export const CHATBOT_SETTINGS_KEY = ['chatbot-settings'];
export const CHATBOT_LANES_KEY = ['chatbot-lanes'];

export function useChatbotLanes() {
  return useQuery({
    queryKey: CHATBOT_LANES_KEY,
    queryFn: getChatbotLanes,
    retry: 1,
  });
}

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
      // The lane list carries a `built` flag derived from the business-lane switch
      // this same save may have just moved, so it is refetched rather than left
      // disabling a checkbox the owner has just enabled.
      queryClient.invalidateQueries({ queryKey: CHATBOT_LANES_KEY });
      // These columns live on the singleton the settings layout caches, so the shared
      // row has to be refetched too or the two views disagree.
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast.success('Chatbot settings saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save settings'),
  });
}
