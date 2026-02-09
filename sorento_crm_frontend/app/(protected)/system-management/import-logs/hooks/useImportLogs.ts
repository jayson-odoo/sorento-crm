import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getImportLogs } from '../services/importLogService';

export function useImportLogs(params: DataGridApiFetchParams & { entity_type?: string }) {
  return useQuery({
    queryKey: ['import-logs', params.pageIndex, params.pageSize, params.entity_type],
    queryFn: () => getImportLogs(params),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
