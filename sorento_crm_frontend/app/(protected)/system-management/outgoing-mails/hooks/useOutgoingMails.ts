import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getOutgoingMails } from '../services/outgoingMailService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useOutgoingMails(params: DataGridApiFetchParams & { status?: string; query?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['outgoing-mails', params.pageIndex, params.pageSize, params.status, params.query],
    queryFn: () => getOutgoingMails(params),
    staleTime: 1000 * 30,
    retry: 1,
  });
}

