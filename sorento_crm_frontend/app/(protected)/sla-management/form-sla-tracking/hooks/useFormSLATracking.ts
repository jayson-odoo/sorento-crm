import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getFormSLATracking } from '../services/formSLATrackingService';

export function useFormSLATracking(params: DataGridApiFetchParams & { policy_id?: string; assigned_to?: string }) {
  return useQuery({
    queryKey: ['form-sla-tracking', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.policy_id, params.assigned_to],
    queryFn: () => getFormSLATracking(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
