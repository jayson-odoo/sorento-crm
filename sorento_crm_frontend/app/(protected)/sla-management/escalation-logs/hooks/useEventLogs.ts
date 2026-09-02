import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getEventLogs } from '../services/eventLogService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useEventLogs(params: DataGridApiFetchParams & { tracking_id?: string; event_type?: string; assigned_to?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['sla-event-logs', params.pageIndex, params.pageSize, params.sorting, params.tracking_id, params.event_type, params.assigned_to],
    queryFn: () => getEventLogs(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}
