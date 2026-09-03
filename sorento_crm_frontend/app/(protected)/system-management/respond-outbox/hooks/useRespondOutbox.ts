import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getRespondOutbox } from '../services/respondOutboxService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useRespondOutbox(
  params: DataGridApiFetchParams & {
    status?: string;
    business_table?: string;
    query?: string;
  },
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      'respond-outbox',
      params.pageIndex,
      params.pageSize,
      params.status,
      params.business_table,
      params.query,
    ],
    queryFn: () => getRespondOutbox(params),
    staleTime: 1000 * 15,
    retry: 1,
  });
}
