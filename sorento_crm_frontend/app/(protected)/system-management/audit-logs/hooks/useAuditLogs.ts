import { useQuery } from '@tanstack/react-query';
import { getAuditLogs, type AuditLogListParams } from '../services/auditLogService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useAuditLogs(params: AuditLogListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
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
    retry: 1,
  });
}
