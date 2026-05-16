import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  cancelEmailOutboxRow,
  getEmailOutbox,
  getEmailOutboxRow,
  retryEmailOutboxRow,
} from '../services/emailOutboxService';

export function useEmailOutbox(
  params: DataGridApiFetchParams & { status?: string; event_key?: string; query?: string },
) {
  return useQuery({
    queryKey: ['email-outbox', params.pageIndex, params.pageSize, params.status, params.event_key, params.query],
    queryFn: () => getEmailOutbox(params),
    staleTime: 1000 * 15,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useEmailOutboxRow(id: string | null) {
  return useQuery({
    queryKey: ['email-outbox-row', id],
    queryFn: () => getEmailOutboxRow(id as string),
    enabled: !!id,
    retry: 1,
  });
}

export function useRetryEmailOutboxRow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: retryEmailOutboxRow,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['email-outbox'] });
      toast.success('Outbox row re-queued. Drainer will pick it up shortly.');
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useCancelEmailOutboxRow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cancelEmailOutboxRow,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['email-outbox'] });
      toast.success('Outbox row cancelled.');
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
