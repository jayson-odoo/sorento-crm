import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { RecordHistoryEvent } from '@/types/recordHistory.types';

/**
 * STANDARD-HISTORY wave 2 (AC-SH-W2-1): a sales order's History tab.
 *   GET /api/v1/project-sales/sales-orders/{pso_id}/history  (projects.projects.view)
 *   GET /api/v1/scm/sales-orders/{so_id}/history             (scm.dashboard.view)
 * Both answer `{ events: RecordHistoryEvent[] }`, newest first; 404 for an unknown id or another
 * company's order.
 */
export interface SalesOrderHistory {
  events: RecordHistoryEvent[];
}

async function read(url: string): Promise<SalesOrderHistory> {
  const response = await apiFetch(url);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the history'));
  return response.json();
}

export function getProjectSalesOrderHistory(psoId: string): Promise<SalesOrderHistory> {
  return read(`/api/v1/project-sales/sales-orders/${psoId}/history`);
}

export function getScmSalesOrderHistory(soId: string): Promise<SalesOrderHistory> {
  return read(`/api/v1/scm/sales-orders/${soId}/history`);
}
