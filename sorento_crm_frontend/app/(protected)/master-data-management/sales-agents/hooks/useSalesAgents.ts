import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getSalesAgents,
  getSalesAgent,
  annotateSalesAgent,
} from '../services/salesAgentService';
import type { MirrorAnnotationPayload } from '../types/salesAgent.types';

export function useSalesAgents(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['sales-agents', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getSalesAgents(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSalesAgent(id: string | null) {
  return useQuery({
    queryKey: ['sales-agent', id],
    queryFn: () => {
      if (!id) throw new Error('Sales agent ID is required');
      return getSalesAgent(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateSalesAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateSalesAgent(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['sales-agents'] });
      queryClient.invalidateQueries({ queryKey: ['sales-agent', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
