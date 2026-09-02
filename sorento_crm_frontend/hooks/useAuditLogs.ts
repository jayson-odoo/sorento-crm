import { useQuery } from '@tanstack/react-query';
import { getAuditLogs } from '@/services/auditService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useAuditLogs(entityType: string | null, entityId: string | null, page = 1, limit = 50) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['audit-logs', entityType, entityId, page, limit],
    queryFn: () => getAuditLogs({ entity_type: entityType!, entity_id: entityId!, page, limit }),
    enabled: !!entityType && !!entityId,
    staleTime: 60 * 1000,
  });
}
