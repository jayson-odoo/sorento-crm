/**
 * Cross-Entity Activity Timeline — feature service.
 *
 * Backend contract: `GET /api/v1/audit/activity` — a human-readable, label-
 * resolved view over the `audit_logs` table (the raw listing lives at
 * `GET /api/v1/audit/logs/`). Auth-only, same as the Audit Logs page.
 *
 * Query params:
 *   entity_type   repeatable FE type(s): complaint | order | user | supplier |
 *                 promotion | form | ticket | stock_inquiry | purchase_request | product
 *   action        created | updated | deleted (backend maps to INSERT/UPDATE/DELETE)
 *   user_id       actor filter (users.id)
 *   date_from     yyyy-MM-dd inclusive (compared on changed_at)
 *   date_to       yyyy-MM-dd inclusive
 *   q             free text over entity_id + description
 *   trace_id      one grouped multi-row action
 *   page          1-based
 *   limit         default 50
 *
 * Response (200) — the FE consumes exactly this shape:
 *   {
 *     items: ActivityItem[],   // entity_label + entity_href are BE-resolved, never UUIDs
 *     actors: { id, name }[],  // distinct actors in the window -> user filter
 *     pagination: { page, limit, total }
 *   }
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ActivityFeedResponse,
  ActivityFilters,
} from '../types/activity.types';

export interface GetActivityFeedParams extends ActivityFilters {
  page?: number;
  limit?: number;
}

export async function getActivityFeed(
  params: GetActivityFeedParams,
): Promise<ActivityFeedResponse> {
  const { page = 1, limit = 50, ...filters } = params;

  const sp = new URLSearchParams();
  sp.set('page', String(page));
  sp.set('limit', String(limit));
  for (const type of filters.entity_types) {
    sp.append('entity_type', type);
  }
  if (filters.action) sp.set('action', filters.action);
  if (filters.user_id) sp.set('user_id', filters.user_id);
  if (filters.date_from) sp.set('date_from', filters.date_from);
  if (filters.date_to) sp.set('date_to', filters.date_to);
  if (filters.q) sp.set('q', filters.q.trim());
  if (filters.trace_id) sp.set('trace_id', filters.trace_id);

  const response = await apiFetch(`/api/v1/audit/activity?${sp.toString()}`);
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to load activity timeline'),
    );
  }
  return response.json();
}
