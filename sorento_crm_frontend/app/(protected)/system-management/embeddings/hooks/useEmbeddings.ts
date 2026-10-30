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

/** Overview counts scan the embedding tables: polled only while the caller shows them (`poll`) in a visible tab. */
export function useEmbeddingsOverview({ poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: [...EMBEDDINGS_KEY, 'overview'],
    queryFn: getOverview,
    refetchInterval: poll ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
}

/** Refresh after a mutation by joining a fetch already in flight: aborting it leaves its query running server-side. */
function refreshEmbeddings(queryClient: ReturnType<typeof useQueryClient>) {
  return queryClient.invalidateQueries({ queryKey: EMBEDDINGS_KEY }, { cancelRefetch: false });
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
      refreshEmbeddings(queryClient);
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
      refreshEmbeddings(queryClient);
      toast.success(action === 'start' ? 'Backfill started' : 'Backfill stopping');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
