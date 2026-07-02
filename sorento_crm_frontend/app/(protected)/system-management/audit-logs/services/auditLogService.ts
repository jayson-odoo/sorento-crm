import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { AuditLogListResponse } from '../types/auditLog.types';

export type AuditLogListParams = DataGridApiFetchParams & {
  entity_type?: string;
  entity_id?: string;
  user_id?: string;
  action?: string;
};

/**
 * Fetch audit-trail entries.
 *
 * Backend contract: `GET /api/v1/audit/logs/` -> `ListResponse[AuditLogResponse]`.
 * Supported query params: entity_type, entity_id, user_id, action, page (1-based), limit.
 * (sort/dir/query are emitted by buildDataGridParams for the standard listing shape
 * but are ignored server-side — the backend orders by changed_at desc.)
 */
export async function getAuditLogs(
  params: AuditLogListParams,
): Promise<AuditLogListResponse> {
  const { entity_type, entity_id, user_id, action, ...gridParams } = params;
  const queryParams = buildDataGridParams(gridParams, {
    entity_type,
    entity_id,
    user_id,
    action,
  });
  const response = await apiFetch(`/api/v1/audit/logs/?${queryParams.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load audit logs'));
  }
  return response.json();
}
