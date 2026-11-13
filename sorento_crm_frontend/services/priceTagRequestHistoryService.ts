import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { RecordHistoryEvent } from '@/types/recordHistory.types';

/**
 * STANDARD-HISTORY wave 5 (AC-W5-6): a price tag request's History tab.
 *   GET /api/v1/dealer-kit/price-tag-requests/{request_id}/history
 *     (dealer_kit.price_tag_requests.view or .view_own)
 * Answers `{ events: RecordHistoryEvent[] }`, newest first; 404 as the request itself.
 */
export interface PriceTagRequestHistory {
  events: RecordHistoryEvent[];
}

export async function getPriceTagRequestHistory(requestId: string): Promise<PriceTagRequestHistory> {
  const response = await apiFetch(`/api/v1/dealer-kit/price-tag-requests/${requestId}/history`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the history'));
  return response.json();
}
