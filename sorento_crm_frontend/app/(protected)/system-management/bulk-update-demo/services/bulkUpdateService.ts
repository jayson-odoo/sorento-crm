/**
 * Bulk Update — Phase-1 MOCK service.
 *
 * =========================================================================
 * PROPOSED PHASE-2 REAL CONTRACT (not yet implemented — awaiting sign-off)
 * =========================================================================
 *
 *   POST /api/v1/<resource>/bulk-update
 *   body: { ids: string[]; field: string; value: any }
 *   resp: {
 *     updated: number;
 *     skipped: { id: string; label: string; reason: string }[];
 *   }
 *
 * KEY BACKEND CONSTRAINTS (these are the whole point of the reframe):
 *  - The backend MUST maintain a per-resource WHITELIST of editable fields (and,
 *    for enum fields, allowed values). Any field/value not on the whitelist is a
 *    422 — never a raw column write.
 *  - Each `id` MUST be run through the resource's NORMAL update path so that
 *    validation, business rules, and side effects fire (e.g. a status transition
 *    that spawns an SLA row, sends a notification, or is disallowed by state).
 *    Rows the normal path rejects come back in `skipped` with a human reason —
 *    the operation is partial-success, not all-or-nothing.
 *  - The whole operation MUST be audit-trailed (ties into the audit_logs work):
 *    one audit entry per updated row, attributed to the acting user.
 *  - No generic "update any column on any table" endpoint. That bypasses the
 *    above and is a data-integrity footgun; this contract intentionally forbids it.
 *
 * Phase-2 FE wiring (replacing this mock):
 *   - real service calls `apiFetch(...)` + `extractApiError(response, fallback)`
 *     (never a hand-rolled `.catch(() => ({}))`).
 *   - `field` is one of the caller's whitelisted `BulkEditableField.key`s.
 * =========================================================================
 */

import type { BulkUpdateResult } from '@/components/common/BulkUpdateDialog';

export interface MockTask {
  id: string;
  name: string;
  status: string;
  priority: string;
  assignee: string;
}

/**
 * Mock apply: resolves after a short delay with a realistic PARTIAL result.
 * Some rows are "skipped" to exercise the partial-result UI (e.g. an invalid
 * status transition that the real backend's update path would reject).
 */
export async function mockBulkUpdate(
  rows: MockTask[],
  field: string,
  value: string,
): Promise<BulkUpdateResult> {
  await new Promise((resolve) => setTimeout(resolve, 900));

  const skipped: BulkUpdateResult['skipped'] = [];
  let updated = 0;

  for (const row of rows) {
    // Simulate a business rule: you cannot move an already-resolved task's status.
    if (field === 'status' && row.status === 'resolved' && value !== 'resolved') {
      skipped.push({
        id: row.id,
        label: row.name,
        reason: 'Status transition not allowed — task is already resolved.',
      });
      continue;
    }
    updated += 1;
  }

  return { updated, skipped };
}
