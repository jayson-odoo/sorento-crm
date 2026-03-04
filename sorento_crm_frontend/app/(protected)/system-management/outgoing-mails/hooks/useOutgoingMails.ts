import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getOutgoingMails } from '../services/outgoingMailService';

export function useOutgoingMails(params: DataGridApiFetchParams & { status?: string; query?: string }) {
  return useQuery({
    queryKey: ['outgoing-mails', params.pageIndex, params.pageSize, params.status, params.query],
    queryFn: () => getOutgoingMails(params),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

