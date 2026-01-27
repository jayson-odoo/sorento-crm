import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getEventLogs } from '../services/eventLogService';

export function useEventLogs(params: DataGridApiFetchParams & { tracking_id?: string; event_type?: string; assigned_to?: string }) {
  return useQuery({
    queryKey: ['sla-event-logs', params.pageIndex, params.pageSize, params.sorting, params.tracking_id, params.event_type, params.assigned_to],
    queryFn: () => getEventLogs(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
