/**
 * PM-SIMPLIFY: a PO's progress and an area's delivery date.
 *
 *   GET /purchase-orders/{po_id}/progress
 *   PUT /delivery-phases/{phase_id}/date
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  AreaDateChangeBody,
  AreaDateChangeResult,
  POProgress,
} from '../types/poProgress.types';

const BASE = '/api/v1/project-sales';

export async function getPurchaseOrderProgress(poId: string): Promise<POProgress> {
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/progress`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load what is left to deliver'));
  return response.json();
}

export async function changeAreaDate(
  phaseId: string,
  body: AreaDateChangeBody,
): Promise<AreaDateChangeResult> {
  const response = await apiFetch(`${BASE}/delivery-phases/${phaseId}/date`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to move the delivery date'));
  return response.json();
}
