/**
 * Cross-Entity Activity Timeline — feature service.
 *
 * ============================================================================
 * PHASE-1 PROTOTYPE — MOCK ONLY. No backend call is made yet.
 * This file resolves against the local `__mocks__` fixture and simulates
 * loading / empty / error states via a `mockState` knob so the UI can be
 * signed off before any endpoint exists (three-phase rule).
 * ============================================================================
 *
 * ---------------------------------------------------------------------------
 * PROPOSED REAL API CONTRACT (Phase-2 backend work)
 * ---------------------------------------------------------------------------
 * A dedicated, timeline-shaped endpoint over the existing `audit_logs` table.
 * The raw-row listing already lives at `GET /api/v1/audit/logs/`; this feed
 * layers grouping + label resolution on top, so a NEW endpoint is cleaner
 * than overloading the raw one:
 *
 *   GET /api/v1/audit/activity
 *
 * Query params:
 *   entity_types  string[]  repeatable; e.g. ?entity_types=complaint&entity_types=order
 *   action        string    one of created|updated|deleted
 *                           (backend maps INSERT/CREATE → created)
 *   user_id       string    actor filter (users.id)
 *   date_from     string    yyyy-MM-dd inclusive (compared on changed_at, MYT day)
 *   date_to       string    yyyy-MM-dd inclusive
 *   q             string    free-text over resolved entity_label + description + summary
 *   trace_id      string    return only rows in one grouped action
 *   page          number    1-based
 *   limit         number    default 50
 *
 * Response (200) — the FE consumes exactly this shape:
 *   {
 *     "items": [
 *       {
 *         "id": "<audit_logs.id>",
 *         "entity_type": "complaint",
 *         "entity_label": "Complaint CMP-1042",   // BE-RESOLVED, NEVER a UUID
 *         "entity_href": "/complaint-management/complaints/CMP-1042" | null,
 *         "action": "updated",                     // created|updated|deleted
 *         "actor_name": "Jane Tan" | "System" | null,
 *         "actor_avatar_url": null,
 *         "changed_at": "2026-06-30T09:12:00Z",
 *         "summary": "status: pending → resolved" | null,
 *         "changes": [                             // derived from old/new_values
 *           { "field": "Status", "from": "Pending", "to": "Resolved" }
 *         ],
 *         "trace_id": "<uuid>" | null
 *       }
 *     ],
 *     "actors": [ { "id": "<users.id>", "name": "Jane Tan" } ],
 *     "pagination": { "page": 1, "limit": 50, "total": 128 }
 *   }
 *
 * BACKEND RESPONSIBILITIES (flagged for Phase-2):
 *   1. entity_id → entity_label resolution PER entity_type. The FE must never
 *      show UUIDs. The backend joins each audit row to its source table
 *      (complaint→complaint_no, order→order_no, user→name, product→sku, etc.)
 *      and returns a display label + best-effort detail-page href. Rows whose
 *      source is gone (hard-deleted) fall back to a stable label like
 *      "Order SO-5560 (deleted)".
 *   2. old_values/new_values → `changes[]` diffing with human field labels and
 *      value formatting (dates, money, enum → Title Case). `summary` is the
 *      single most salient change, used when the row is collapsed.
 *   3. trace_id grouping metadata so the FE can badge multi-row actions.
 *   4. `actors` = distinct actor set within the current (pre-filter) window,
 *      to populate the user filter without a second round-trip.
 *
 * AUTH: same as the Audit Logs page — authenticated staff, no extra permission
 * slug (siblings Audit Logs / System Health / Import Logs are auth-only).
 * ---------------------------------------------------------------------------
 */

import {
  MOCK_ACTIVITY_ITEMS,
  MOCK_ACTORS,
} from '../__mocks__/activityTimeline';
import type {
  ActivityFeedResponse,
  ActivityFilters,
  ActivityItem,
  ActivityMockState,
} from '../types/activity.types';

export interface GetActivityFeedParams extends ActivityFilters {
  page?: number;
  limit?: number;
  /** PHASE-1 ONLY: forces a UI state. Remove when wiring the real endpoint. */
  mockState?: ActivityMockState;
}

/** Simulated network latency so the loading skeleton is visible in the demo. */
const MOCK_LATENCY_MS = 550;

function matchesFilters(item: ActivityItem, filters: ActivityFilters): boolean {
  if (
    filters.entity_types.length > 0 &&
    !filters.entity_types.includes(item.entity_type)
  ) {
    return false;
  }
  if (filters.action && item.action !== filters.action) {
    return false;
  }
  if (filters.user_id) {
    const actor = MOCK_ACTORS.find((a) => a.id === filters.user_id);
    if (!actor || (item.actor_name ?? '') !== actor.name) {
      return false;
    }
  }
  if (filters.date_from) {
    if (dayKey(item.changed_at) < filters.date_from) return false;
  }
  if (filters.date_to) {
    if (dayKey(item.changed_at) > filters.date_to) return false;
  }
  if (filters.q) {
    const haystack = [item.entity_label, item.summary, item.actor_name]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    if (!haystack.includes(filters.q.trim().toLowerCase())) return false;
  }
  return true;
}

/** Local yyyy-MM-dd key for date-range comparison (matches the day grouping). */
function dayKey(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = `${d.getMonth() + 1}`.padStart(2, '0');
  const day = `${d.getDate()}`.padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * PHASE-1 mock resolver. Mirrors the proposed `GET /api/v1/audit/activity`
 * response shape so swapping to `apiFetch` in Phase-2 is a drop-in change.
 */
export async function getActivityFeed(
  params: GetActivityFeedParams,
): Promise<ActivityFeedResponse> {
  const { mockState = 'success', page = 1, limit = 50, ...filters } = params;

  await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY_MS));

  if (mockState === 'error') {
    throw new Error('Failed to load activity timeline (mock error state).');
  }

  const source = mockState === 'empty' ? [] : MOCK_ACTIVITY_ITEMS;
  const filtered = source.filter((item) => matchesFilters(item, filters));

  return {
    items: filtered,
    actors: MOCK_ACTORS,
    pagination: { page, limit, total: filtered.length },
  };
}
