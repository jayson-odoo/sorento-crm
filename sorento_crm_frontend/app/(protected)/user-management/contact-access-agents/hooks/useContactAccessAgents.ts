import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getContactAccessAgents } from '../services/contactAccessAgentService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useContactAccessAgents(params: DataGridApiFetchParams & { agent_id?: string; contact_id?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['contact-access-agents', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.agent_id, params.contact_id],
    queryFn: () => getContactAccessAgents(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}
