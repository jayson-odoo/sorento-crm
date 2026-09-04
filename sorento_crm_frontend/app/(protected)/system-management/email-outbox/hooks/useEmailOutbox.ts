import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  bulkCancelEmailOutbox,
  bulkRetryEmailOutbox,
  cancelEmailOutboxRow,
  getEmailOutbox,
  getEmailOutboxRow,
  retryEmailOutboxRow,
  type BulkOutboxResult,
} from '../services/emailOutboxService';

function _reportBulk(res: BulkOutboxResult, verb: string) {
  if (res.failed === 0) {
    toast.success(`${res.succeeded} row${res.succeeded === 1 ? '' : 's'} ${verb}.`);
  } else if (res.succeeded === 0) {
    toast.error(`No rows ${verb} - ${res.failed} could not be (wrong state).`);
  } else {
    toast.warning(`${res.succeeded} ${verb}, ${res.failed} skipped (wrong state).`);
  }
}

export function useEmailOutbox(
  params: DataGridApiFetchParams & { status?: string; event_key?: string; query?: string },
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['email-outbox', params.pageIndex, params.pageSize, params.status, params.event_key, params.query],
    queryFn: () => getEmailOutbox(params),
    staleTime: 1000 * 15,
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

export function useBulkRetryEmailOutbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: bulkRetryEmailOutbox,
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['email-outbox'] });
      _reportBulk(res, 're-queued');
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useBulkCancelEmailOutbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: bulkCancelEmailOutbox,
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['email-outbox'] });
      _reportBulk(res, 'cancelled');
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
