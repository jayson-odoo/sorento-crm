import { apiFetch } from '@/lib/api';
import type { AuditLogsResponse } from '@/types/audit.types';

export async function getAuditLogs(params: {
  entity_type: string;
  entity_id: string;
  page?: number;
  limit?: number;
}): Promise<AuditLogsResponse> {
  const search = new URLSearchParams({
    entity_type: params.entity_type,
    entity_id: params.entity_id,
    page: String(params.page ?? 1),
    limit: String(params.limit ?? 50),
  });
  const response = await apiFetch(`/api/v1/audit/logs?${search.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch audit logs');
  return response.json();
}
