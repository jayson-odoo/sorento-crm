import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { HealthSummary } from '../types/health.types';

/**
 * Fetch the admin operational health summary.
 *
 * Backend contract: `GET /api/v1/system/health/summary` -> `HealthSummaryResponse`.
 * Read-only aggregation; safe to poll.
 */
export async function getHealthSummary(
  range?: { date_from?: string; date_to?: string },
): Promise<HealthSummary> {
  const params = new URLSearchParams();
  if (range?.date_from) params.set('date_from', range.date_from);
  if (range?.date_to) params.set('date_to', range.date_to);
  const qs = params.toString();
  const response = await apiFetch(
    `/api/v1/system/health/summary${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load system health'));
  }
  return response.json();
}
