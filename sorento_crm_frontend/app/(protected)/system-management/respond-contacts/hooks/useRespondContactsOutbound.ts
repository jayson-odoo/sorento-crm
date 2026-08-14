import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { RESPOND_CONTACTS_OUTBOUND_KEY } from '@/hooks/useRespondContactOutbound';
import { getRespondContactsOutbound } from '../services/respondContactOutboundService';
import type { OutboundFilter } from '../types/respondContactOutbound.types';

// The write side is shared with the contacts / contact-access-agents grids, which
// flip the same column: `@/hooks/useRespondContactOutbound`. Re-exported here so
// this screen keeps its single import.
export { RESPOND_CONTACTS_OUTBOUND_KEY };
export { useRespondContactOutboundMutations } from '@/hooks/useRespondContactOutbound';

export function useRespondContactsOutbound(
  params: DataGridApiFetchParams & { outbound?: OutboundFilter },
) {
  return useQuery({
    queryKey: [
      RESPOND_CONTACTS_OUTBOUND_KEY,
      params.pageIndex,
      params.pageSize,
      params.searchQuery,
      params.outbound,
    ],
    queryFn: () => getRespondContactsOutbound(params),
    staleTime: 1000 * 15,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
