import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { getRuns, getRun, annotateRun } from '../services/stockBalanceService';
import type { MirrorAnnotationPayload } from '../types/stockBalance.types';

export function useStockBalanceRuns() {
  return useQuery({
    queryKey: ['stock-balance-runs'],
    queryFn: () => getRuns(1, 100),
    staleTime: 1000 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useStockBalanceRun(runId: string | null) {
  return useQuery({
    queryKey: ['stock-balance-run', runId],
    queryFn: () => {
      if (!runId) throw new Error('Run ID is required');
      return getRun(runId);
    },
    enabled: !!runId,
    retry: 1,
  });
}

export function useAnnotateStockBalanceRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateRun(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['stock-balance-runs'] });
      queryClient.invalidateQueries({ queryKey: ['stock-balance-run', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
