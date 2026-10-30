import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getEmbeddingSettings,
  saveEmbeddingSettings,
  type EmbeddingSettingsInput,
} from '../services/embeddingSettingsService';

export const EMBEDDING_SETTINGS_KEY = ['embedding-settings'];

export function useEmbeddingSettings() {
  return useQuery({ queryKey: EMBEDDING_SETTINGS_KEY, queryFn: getEmbeddingSettings, retry: 1 });
}

export function useSaveEmbeddingSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EmbeddingSettingsInput) => saveEmbeddingSettings(input),
    onSuccess: (_data, input) => {
      queryClient.invalidateQueries({ queryKey: EMBEDDING_SETTINGS_KEY });
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      queryClient.invalidateQueries({ queryKey: ['embeddings'] }, { cancelRefetch: false });
      toast.success(input.recordsBackfillStarted ? 'Embedding settings saved, records backfill started' : 'Embedding settings saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save settings'),
  });
}
