import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { HealthSummary } from '../types/health.types';

/**
 * Fetch the admin operational health summary.
 *
 * Backend contract: `GET /api/v1/system/health/summary` -> `HealthSummaryResponse`.
 * Read-only aggregation; safe to poll.
 */
export async function getHealthSummary(): Promise<HealthSummary> {
  const response = await apiFetch('/api/v1/system/health/summary');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load system health'));
  }
  return response.json();
}
