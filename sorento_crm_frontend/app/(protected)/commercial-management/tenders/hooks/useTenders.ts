import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getTenders } from '../services/tenderService';

export function useTenders(params: DataGridApiFetchParams & { project_id?: string }) {
  return useQuery({
    queryKey: ['commercial-tenders', params.pageIndex, params.pageSize, params.project_id],
    queryFn: () => getTenders(params),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
