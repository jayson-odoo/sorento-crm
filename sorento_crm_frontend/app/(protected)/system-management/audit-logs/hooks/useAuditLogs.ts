import { useQuery } from '@tanstack/react-query';
import { getAuditLogs, type AuditLogListParams } from '../services/auditLogService';

export function useAuditLogs(params: AuditLogListParams) {
  return useQuery({
    queryKey: [
      'audit-logs',
      params.pageIndex,
      params.pageSize,
      params.entity_type,
      params.entity_id,
      params.user_id,
      params.action,
      params.changed_from,
      params.changed_to,
    ],
    queryFn: () => getAuditLogs(params),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
