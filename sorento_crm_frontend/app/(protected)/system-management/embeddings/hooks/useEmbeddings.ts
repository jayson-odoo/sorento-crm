import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  embedMissing,
  getLookupWords,
  getOverview,
  recordsBackfill,
  tryPhrase,
} from '../services/embeddingsService';
import type { BackfillAction } from '../types/embeddings.types';

export const EMBEDDINGS_KEY = ['embeddings'] as const;

export function useEmbeddingsOverview() {
  return useQuery({
    queryKey: [...EMBEDDINGS_KEY, 'overview'],
    queryFn: getOverview,
    refetchInterval: 30_000,
  });
}

export function useLookupWords(list: string) {
  return useQuery({
    queryKey: [...EMBEDDINGS_KEY, 'words', list],
    queryFn: () => getLookupWords(list),
  });
}

export function useTryPhrase() {
  return useMutation({
    mutationFn: (phrase: string) => tryPhrase(phrase),
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useEmbedMissing() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => embedMissing(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: EMBEDDINGS_KEY });
      toast.success('Embedding started');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRecordsBackfill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ action }: { action: BackfillAction }) => recordsBackfill(action),
    onSuccess: (_data, { action }) => {
      queryClient.invalidateQueries({ queryKey: EMBEDDINGS_KEY });
      toast.success(action === 'start' ? 'Backfill started' : 'Backfill stopping');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
