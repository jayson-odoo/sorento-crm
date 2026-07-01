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
    ],
    queryFn: () => getAuditLogs(params),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
