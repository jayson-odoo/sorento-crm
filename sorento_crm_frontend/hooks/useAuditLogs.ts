import { useQuery } from '@tanstack/react-query';
import { getAuditLogs } from '@/services/auditService';

export function useAuditLogs(entityType: string | null, entityId: string | null, page = 1, limit = 50) {
  return useQuery({
    queryKey: ['audit-logs', entityType, entityId, page, limit],
    queryFn: () => getAuditLogs({ entity_type: entityType!, entity_id: entityId!, page, limit }),
    enabled: !!entityType && !!entityId,
    staleTime: 60 * 1000,
  });
}
